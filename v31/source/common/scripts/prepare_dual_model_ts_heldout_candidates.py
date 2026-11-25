#!/usr/bin/env python3
"""Prepare label-disjoint held-out structures for dual-model TS validation."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.matris_training_exclusions import geometry_fingerprint
from scripts.neb_agent.utils_structure import (
    Poscar,
    compatible,
    copy_with_frac,
    minimum_image_delta,
    pbc_distance,
    read_poscar,
    write_poscar,
)


PRIMARY_ROLES = {"rising_path", "near_saddle", "falling_path"}
ALL_ROLES = PRIMARY_ROLES | {"failure_boundary_diagnostic"}


def _parse_exact(value: str) -> dict[str, Any]:
    fields = value.split(":")
    if len(fields) != 3 or fields[1] not in ALL_ROLES:
        raise ValueError("exact sample must be OUTPUT_ID:ROLE:SOURCE_SAMPLE")
    return {"sample_id": fields[0], "role": fields[1], "source_sample": fields[2]}


def _parse_interpolation(value: str) -> dict[str, Any]:
    fields = value.split(":")
    if len(fields) != 5 or fields[1] not in ALL_ROLES:
        raise ValueError("interpolation must be OUTPUT_ID:ROLE:LEFT_SAMPLE:RIGHT_SAMPLE:FRACTION")
    fraction = float(fields[4])
    if not 0.0 < fraction < 1.0:
        raise ValueError("interpolation fraction must be strictly between zero and one")
    return {
        "sample_id": fields[0],
        "role": fields[1],
        "left_sample": fields[2],
        "right_sample": fields[3],
        "fraction": fraction,
    }


def _fixed_indices(structure: Poscar) -> list[int]:
    return [
        index
        for index, flags in enumerate(structure.flags)
        if structure.selective and tuple(value.upper() for value in flags) == ("F", "F", "F")
    ]


def _nearest_fe(structure: Poscar, atom_index: int) -> dict[str, Any]:
    distances = sorted(
        (pbc_distance(structure, atom_index, index), index)
        for index, label in enumerate(structure.labels)
        if label == "Fe"
    )
    return {
        "fe_index_zero_based": distances[0][1],
        "fe_index_one_based": distances[0][1] + 1,
        "distance_A": distances[0][0],
        "coordination_within_2p4_A": sum(distance <= 2.4 for distance, _ in distances),
    }


def _minimum_nonbonded_contact(
    structure: Poscar, excluded_pairs: set[tuple[int, int]]
) -> tuple[float, tuple[int, int]]:
    best = (math.inf, (-1, -1))
    for left in range(structure.atom_count):
        for right in range(left + 1, structure.atom_count):
            if (left, right) in excluded_pairs:
                continue
            distance = pbc_distance(structure, left, right)
            if distance < best[0]:
                best = distance, (left, right)
    return best


def _render(
    records: list[dict[str, Any]], structures: list[Poscar], output: Path
) -> None:
    figure, axes = plt.subplots(
        2,
        len(records),
        figsize=(3.7 * len(records), 7.0),
        constrained_layout=True,
    )
    colors = {"Fe_fixed": "#64748b", "Fe_free": "#cbd5e1", "C": "#111827", "O": "#dc2626", "H": "#f59e0b"}
    sizes = {"Fe": 32, "C": 88, "O": 88, "H": 66}
    for column, (record, structure) in enumerate(zip(records, structures, strict=True)):
        fixed = set(_fixed_indices(structure))
        cart = (structure.frac % 1.0) @ structure.cell
        anchor = 47
        for index in range(45, 50):
            cart[index] = cart[anchor] + minimum_image_delta(
                structure.frac[anchor], structure.frac[index]
            ) @ structure.cell
        for row, dimensions in enumerate(((0, 1), (1, 2))):
            axis = axes[row, column]
            for index, label in enumerate(structure.labels):
                color = (
                    colors["Fe_fixed" if index in fixed else "Fe_free"]
                    if label == "Fe"
                    else colors[label]
                )
                axis.scatter(
                    cart[index, dimensions[0]],
                    cart[index, dimensions[1]],
                    s=sizes[label],
                    c=color,
                    edgecolors="white",
                    linewidths=0.35,
                    zorder=4 if label != "Fe" else 2,
                )
            for left, right, color in ((45, 46, "#111827"), (46, 47, "#dc2626"), (45, 48, "#f59e0b"), (47, 49, "#f59e0b")):
                axis.plot(
                    [cart[left, dimensions[0]], cart[right, dimensions[0]]],
                    [cart[left, dimensions[1]], cart[right, dimensions[1]]],
                    color=color,
                    linewidth=1.5,
                    alpha=0.85,
                )
            axis.set_aspect("equal", adjustable="box")
            axis.grid(alpha=0.15)
        axes[0, column].set_title(
            f"{record['sample_id']}\n{record['role']}\nO-H={record['geometry']['O_H_A']:.3f} A",
            fontsize=8.5,
        )
        axes[0, column].set_xlabel("x (A)")
        axes[0, column].set_ylabel("y (A)")
        axes[1, column].set_xlabel("y (A)")
        axes[1, column].set_ylabel("z (A)")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=220, facecolor="white")
    plt.close(figure)


def prepare(  # noqa: C901 - preparation is a linear scientific evidence gate.
    prediction_batch_path: Path,
    predictions_path: Path,
    state_path: Path,
    label_set_path: Path,
    policy_path: Path,
    output: Path,
    exact_samples: list[dict[str, Any]],
    interpolations: list[dict[str, Any]],
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    batch = load_json_object(prediction_batch_path)
    predictions = load_json_object(predictions_path)
    state = load_json_object(state_path)
    labels = load_json_object(label_set_path)
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if batch.get("document_kind") != "dual_model_ts_path_force_prediction_batch_request":
        raise ValueError("invalid dual-model prediction batch")
    if predictions.get("document_kind") != "dual_model_ts_path_force_prediction_set":
        raise ValueError("invalid dual-model prediction result")
    if state.get("document_kind") != "dual_model_ts_active_learning_state":
        raise ValueError("invalid dual-model active-learning state")
    if labels.get("document_kind") != "dual_model_ts_vasp_force_label_set":
        raise ValueError("invalid VASP force-label set")
    if state.get("vasp_error_assessment", {}).get("decision") != "retain_MatRIS_checkpoint_then_run_disjoint_heldout_TS_validation":
        raise ValueError("active-learning state is not routed to held-out validation")
    if batch.get("reaction_id") != state.get("reaction_id") or labels.get("reaction_id") != state.get("reaction_id"):
        raise ValueError("reaction binding mismatch")

    root = prediction_batch_path.parent
    source_rows = {row["sample_id"]: row for row in batch["structures"]}
    source_paths = {sample_id: root / row["path"] for sample_id, row in source_rows.items()}
    source_structures = {sample_id: read_poscar(path) for sample_id, path in source_paths.items()}
    first = source_structures["pre_00"]
    for sample_id, structure in source_structures.items():
        errors = compatible(first, structure)
        if errors:
            raise ValueError(f"incompatible source structure {sample_id}: {errors}")
    if first.labels[45:50] != ["C", "C", "O", "H", "H"]:
        raise ValueError("unexpected Fe-C-C-O-H-H atom order")
    fixed = _fixed_indices(first)
    selected_ids = {row["sample_id"] for row in labels["labels"]}
    selected_hashes = {row["structure_sha256"] for row in labels["labels"]}
    selected_geometries = {
        geometry_fingerprint(source_structures[sample_id]) for sample_id in selected_ids
    }
    prediction_by_id = {row["sample_id"]: row for row in predictions["predictions"]}
    excluded_pairs = {(45, 46), (46, 47), (45, 48), (47, 49)}

    output.mkdir(parents=True, exist_ok=True)
    candidate_records: list[dict[str, Any]] = []
    candidate_structures: list[Poscar] = []
    seen_hashes: set[str] = set()
    seen_geometries: set[str] = set()
    specifications = [({"construction": "exact_unlabeled_path_member"} | row) for row in exact_samples]
    specifications += [({"construction": "minimum_image_interpolation"} | row) for row in interpolations]
    for specification in specifications:
        sample_id = specification["sample_id"]
        role = specification["role"]
        if role not in ALL_ROLES:
            raise ValueError(f"unsupported role: {role}")
        if specification["construction"] == "exact_unlabeled_path_member":
            source_id = specification["source_sample"]
            if source_id not in source_structures or source_id in selected_ids:
                raise ValueError(f"exact candidate is missing or already VASP labeled: {source_id}")
            structure = source_structures[source_id]
            source = {"source_sample": source_id}
        else:
            left_id = specification["left_sample"]
            right_id = specification["right_sample"]
            if left_id not in source_structures or right_id not in source_structures:
                raise ValueError(f"missing interpolation source for {sample_id}")
            left = source_structures[left_id]
            right = source_structures[right_id]
            fraction = specification["fraction"]
            frac = left.frac + fraction * minimum_image_delta(left.frac, right.frac)
            if fixed:
                frac[fixed] = first.frac[fixed]
            structure = copy_with_frac(
                left,
                frac,
                f"Dual-model held-out {sample_id} from {left_id}-{right_id}",
            )
            source = {"left_sample": left_id, "right_sample": right_id, "fraction": fraction}
        candidate_dir = output / "candidates" / sample_id
        candidate_dir.mkdir(parents=True)
        poscar_path = candidate_dir / "POSCAR"
        if specification["construction"] == "exact_unlabeled_path_member":
            shutil.copy2(source_paths[source["source_sample"]], poscar_path)
        else:
            write_poscar(poscar_path, structure)
        structure_hash = sha256_file(poscar_path)
        geometry_hash = geometry_fingerprint(structure)
        if structure_hash in selected_hashes or geometry_hash in selected_geometries:
            raise ValueError(f"candidate overlaps a current VASP label: {sample_id}")
        if structure_hash in seen_hashes or geometry_hash in seen_geometries:
            raise ValueError(f"duplicate held-out candidate: {sample_id}")
        seen_hashes.add(structure_hash)
        seen_geometries.add(geometry_hash)

        min_nonbonded, min_pair = _minimum_nonbonded_contact(structure, excluded_pairs)
        c_c = pbc_distance(structure, 45, 46)
        c_o = pbc_distance(structure, 46, 47)
        c_h = pbc_distance(structure, 45, 48)
        o_h = pbc_distance(structure, 47, 49)
        fixed_preserved = not fixed or np.array_equal(structure.frac[fixed], first.frac[fixed])
        checks = {
            "exact_structure_hash_disjoint_from_seven_labels": True,
            "rounded_geometry_hash_disjoint_from_seven_labels": True,
            "atom_order_cell_and_flags_compatible": not compatible(first, structure),
            "fixed_layer_preserved": bool(fixed_preserved),
            "minimum_nonbonded_contact_pass": min_nonbonded >= 0.90,
            "C_C_preserved": 1.20 <= c_c <= 1.70,
            "C_O_preserved": 1.10 <= c_o <= 1.65,
            "spectator_C_H_preserved": 0.90 <= c_h <= 1.30,
            "forming_O_H_physically_bounded": 0.85 <= o_h <= 3.50,
        }
        if not all(checks.values()):
            failed = [name for name, passed in checks.items() if not passed]
            raise ValueError(f"geometry gate failed for {sample_id}: {', '.join(failed)}")
        prediction = prediction_by_id.get(source.get("source_sample", ""))
        candidate_records.append(
            {
                "sample_id": sample_id,
                "role": role,
                "primary_heldout_metric_eligible": role in PRIMARY_ROLES,
                "construction": specification["construction"],
                "source": source,
                "structure_path": str(poscar_path.relative_to(output).as_posix()),
                "structure_sha256": structure_hash,
                "geometry_sha256": geometry_hash,
                "atom_count": structure.atom_count,
                "fixed_atom_count": len(fixed),
                "geometry": {
                    "C1_C2_A": c_c,
                    "C2_O_A": c_o,
                    "C1_H_spectator_A": c_h,
                    "O_H_A": o_h,
                    "minimum_nonbonded_contact_A": min_nonbonded,
                    "minimum_nonbonded_pair_zero_based": list(min_pair),
                    "C1_nearest_Fe": _nearest_fe(structure, 45),
                    "C2_nearest_Fe": _nearest_fe(structure, 46),
                    "O_nearest_Fe": _nearest_fe(structure, 47),
                    "forming_H_nearest_Fe": _nearest_fe(structure, 49),
                },
                "checks": checks,
                "frozen_checkpoint_prediction": (
                    {
                        "available": True,
                        "primary_energy_eV": prediction["primary_energy_eV"],
                        "secondary_energy_eV": prediction["secondary_energy_eV"],
                        "model_disagreement": prediction["movable_force_difference"],
                        "interpretation": "preexisting_inference_only_not_training_or_VASP_label",
                    }
                    if prediction
                    else {
                        "available": False,
                        "required_before_VASP": True,
                        "interpretation": "new_boundary_interpolation_requires_exact_dual_model_prediction",
                    }
                ),
            }
        )
        candidate_structures.append(structure)

    primary = [row for row in candidate_records if row["primary_heldout_metric_eligible"]]
    primary_roles = {row["role"] for row in primary}
    if len(primary) < int(policy["held_out_validation"]["minimum_samples"]):
        raise ValueError("too few primary held-out candidates")
    if primary_roles != PRIMARY_ROLES:
        raise ValueError("primary held-out roles are incomplete")
    if not any(row["role"] == "failure_boundary_diagnostic" for row in candidate_records):
        raise ValueError("failure-boundary diagnostic is missing")

    montage_path = output / "heldout_candidate_montage.png"
    _render(candidate_records, candidate_structures, montage_path)
    csv_path = output / "geometry_review.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "sample_id",
                "role",
                "primary_metric",
                "construction",
                "O-H_A",
                "C1-C2_A",
                "C2-O_A",
                "C1-H_A",
                "min_nonbonded_A",
                "O-nearest-Fe_A",
                "H-nearest-Fe_A",
                "verdict",
            ]
        )
        for row in candidate_records:
            geometry = row["geometry"]
            writer.writerow(
                [
                    row["sample_id"],
                    row["role"],
                    row["primary_heldout_metric_eligible"],
                    row["construction"],
                    geometry["O_H_A"],
                    geometry["C1_C2_A"],
                    geometry["C2_O_A"],
                    geometry["C1_H_spectator_A"],
                    geometry["minimum_nonbonded_contact_A"],
                    geometry["O_nearest_Fe"]["distance_A"],
                    geometry["forming_H_nearest_Fe"]["distance_A"],
                    "PASS_GEOMETRY_ONLY",
                ]
            )

    plan = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_heldout_validation_candidate_plan",
        "status": "prepared_for_user_geometry_review_not_submitted",
        "reaction_id": state["reaction_id"],
        "round_index": state["round_index"],
        "heldout_definition": "disjoint_from_round0_seven_VASP_screening_labels_and_not_used_for_training",
        "source_bindings": {
            "prediction_batch": {"path": str(prediction_batch_path.resolve()), "sha256": sha256_file(prediction_batch_path)},
            "predictions": {"path": str(predictions_path.resolve()), "sha256": sha256_file(predictions_path)},
            "active_learning_state": {"path": str(state_path.resolve()), "sha256": sha256_file(state_path)},
            "round0_label_set": {"path": str(label_set_path.resolve()), "sha256": sha256_file(label_set_path)},
            "policy": {"path": str(policy_path.resolve()), "sha256": sha256_file(policy_path)},
        },
        "frozen_models": predictions["models"],
        "selection": {
            "candidate_count": len(candidate_records),
            "primary_metric_candidate_count": len(primary),
            "primary_roles": sorted(primary_roles),
            "failure_boundary_diagnostic_count": sum(
                row["role"] == "failure_boundary_diagnostic" for row in candidate_records
            ),
            "all_exact_and_geometry_hashes_disjoint_from_seven_labels": True,
            "boundary_interpolation_excluded_from_primary_aggregate_metrics": True,
        },
        "candidates": candidate_records,
        "validation_plan": {
            "step_1": "freeze candidate hashes and user geometry review",
            "step_2": "run exact MatRIS and AQCat25 prediction only where missing",
            "step_3": "prepare compatible SIGMA=0.20_eV NSW=0 VASP static labels for separate authorization",
            "step_4": "compute MatRIS-VASP and AQCat25-VASP metrics separately on six primary candidates",
            "screening_safety_ceilings": policy["screening_safety_ceilings"],
            "matris_pass_route": "heldout_screened_for_this_TS_domain_then_review_complete_path_rerun",
            "matris_fail_route": "prepare_replay_finetune_package_then_require_new_checkpoint_full_path_rerun",
            "aqcat25_role": "external_auditor_only_its_failure_does_not_replace_the_MatRIS_primary_decision",
            "uncertainty_boundary": "without_a_real_calibrated_MatRIS_committee_do_not_claim_quantitative_uncertainty",
        },
        "review_artifacts": [
            {"path": montage_path.name, "sha256": sha256_file(montage_path)},
            {"path": csv_path.name, "sha256": sha256_file(csv_path)},
        ],
        "authorization": {
            "gpu_submission_authorized": False,
            "vasp_submission_authorized": False,
            "fine_tuning_authorized": False,
            "path_rerun_authorized": False,
        },
        "scientific_scope": {
            "geometry_candidates_only": True,
            "heldout_VASP_validation_complete": False,
            "active_learning_calibrated": False,
            "accepted_TS_or_barrier": False,
        },
    }
    plan_path = output / "heldout_validation_candidate_plan.json"
    write_json_atomic(plan_path, plan, ensure_ascii=True)
    summary = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_heldout_validation_preparation_summary",
        "status": plan["status"],
        "plan_path": str(plan_path.resolve()),
        "plan_sha256": sha256_file(plan_path),
        "candidate_count": len(candidate_records),
        "primary_metric_candidate_count": len(primary),
        "all_geometry_gates_passed": True,
        "all_disjoint_from_seven_labels": True,
        "jobs_submitted": 0,
    }
    write_json_atomic(output / "preparation_summary.json", summary, ensure_ascii=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prediction-batch", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--label-set", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exact", action="append", default=[])
    parser.add_argument("--interpolate", action="append", default=[])
    args = parser.parse_args()
    result = prepare(
        args.prediction_batch,
        args.predictions,
        args.state,
        args.label_set,
        args.policy,
        args.output,
        [_parse_exact(value) for value in args.exact],
        [_parse_interpolation(value) for value in args.interpolate],
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
