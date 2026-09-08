from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from scripts.artifact_io import sha256_file, source_file_manifest, write_json
from scripts.matris_training_exclusions import geometry_fingerprint
from scripts.neb_agent.utils_structure import (
    Poscar,
    compatible,
    copy_with_frac,
    minimum_image_delta,
    minimum_pair_distance,
    pbc_distance,
    read_poscar,
    write_poscar,
)
from scripts.ts_strategy_engine.active_learning_common import load_policy, load_state
from scripts.ts_strategy_engine.active_learning_domain import _training_structure_evidence


ROLE_VALUES = {"rising_path", "near_saddle", "falling_path"}


def _parse_sample(value: str) -> dict[str, Any]:
    fields = value.split(":")
    if len(fields) != 5:
        raise ValueError("sample must be SAMPLE_ID:ROLE:LEFT_IMAGE:RIGHT_IMAGE:FRACTION")
    sample_id, role, left, right, raw_fraction = fields
    if role not in ROLE_VALUES:
        raise ValueError(f"unsupported role: {role}")
    fraction = float(raw_fraction)
    if not 0.0 < fraction < 1.0:
        raise ValueError("sample fraction must be strictly between zero and one")
    return {
        "sample_id": sample_id,
        "role": role,
        "left_image": left.zfill(2),
        "right_image": right.zfill(2),
        "fraction": fraction,
    }


def _rmsd(reference: Poscar, candidate: Poscar, indices: list[int]) -> float:
    delta = minimum_image_delta(reference.frac, candidate.frac) @ reference.cell
    chosen = delta[indices]
    return float(np.sqrt(np.mean(np.sum(chosen * chosen, axis=1))))


def _nearest_fe(structure: Poscar, atom_index: int, cutoff_a: float) -> dict[str, Any]:
    distances = sorted(
        (pbc_distance(structure, atom_index, index), index)
        for index, label in enumerate(structure.labels)
        if label == "Fe"
    )
    return {
        "diagnostic_cutoff_A": cutoff_a,
        "coordination_count_within_cutoff": sum(distance <= cutoff_a for distance, _ in distances),
        "three_nearest": [
            {"fe_index_zero_based": index, "fe_index_one_based": index + 1, "distance_A": distance}
            for distance, index in distances[:3]
        ],
    }


def _render(candidates: list[tuple[dict[str, Any], Poscar]], output: Path, c_index: int, h_index: int) -> None:
    figure, axes = plt.subplots(2, len(candidates), figsize=(4.2 * len(candidates), 7.2), constrained_layout=True)
    if len(candidates) == 1:
        axes = np.asarray(axes).reshape(2, 1)
    colors = {"fixed": "#64748b", "free": "#cbd5e1", "C": "#111827", "H": "#f97316"}
    for column, (record, structure) in enumerate(candidates):
        cart = (structure.frac % 1.0) @ structure.cell
        cart[h_index] = cart[c_index] + (
            minimum_image_delta(structure.frac[c_index], structure.frac[h_index]) @ structure.cell
        )
        fe_indices = [index for index, label in enumerate(structure.labels) if label == "Fe"]
        fixed = {
            index
            for index, flags in enumerate(structure.flags)
            if structure.selective and tuple(value.upper() for value in flags) == ("F", "F", "F")
        }
        for row, dimensions in enumerate(((0, 1), (1, 2))):
            axis = axes[row, column]
            for index in fe_indices:
                axis.scatter(
                    cart[index, dimensions[0]],
                    cart[index, dimensions[1]],
                    s=28 if index in fixed else 48,
                    c=colors["fixed" if index in fixed else "free"],
                    edgecolors="white",
                    linewidths=0.4,
                )
            axis.scatter(
                cart[c_index, dimensions[0]], cart[c_index, dimensions[1]],
                s=90, c=colors["C"], edgecolors="white", zorder=5,
            )
            axis.scatter(
                cart[h_index, dimensions[0]], cart[h_index, dimensions[1]],
                s=75, c=colors["H"], edgecolors="white", zorder=5,
            )
            axis.plot(
                [cart[c_index, dimensions[0]], cart[h_index, dimensions[0]]],
                [cart[c_index, dimensions[1]], cart[h_index, dimensions[1]]],
                color=colors["H"], linewidth=1.8,
            )
            axis.set_aspect("equal", adjustable="box")
            axis.grid(alpha=0.15)
        axes[0, column].set_title(
            f"{record['sample_id']}\n{record['role']}  C-H={record['c_h_distance_A']:.3f} A",
            fontsize=9,
        )
        axes[0, column].set_xlabel("x (A)")
        axes[0, column].set_ylabel("y (A)")
        axes[1, column].set_xlabel("y (A)")
        axes[1, column].set_ylabel("z (A)")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=220, facecolor="white")
    plt.close(figure)


def prepare(
    path_manifest_path: Path,
    state_path: Path,
    output: Path,
    samples: list[dict[str, Any]],
    c_index: int,
    h_index: int,
) -> dict[str, Any]:
    if len(samples) < 5:
        raise ValueError("at least five held-out candidates are required")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    manifest = json.loads(path_manifest_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    validated_state = load_state(state_path)
    policy_path = Path(validated_state["policy_path"])
    policy = load_policy(policy_path)
    training_hashes, training_geometries = _training_structure_evidence(
        policy_path, policy, validated_state
    )
    manifest_root = path_manifest_path.parent
    image_rows = {str(row["image"]).zfill(2): row for row in manifest["images"]}
    structures: dict[str, Poscar] = {}
    paths: dict[str, Path] = {}
    for image, row in image_rows.items():
        path = manifest_root / row["structure_path"]
        paths[image] = path
        structures[image] = read_poscar(path)

    first = structures[min(structures)]
    if not (0 <= c_index < first.atom_count and 0 <= h_index < first.atom_count):
        raise ValueError("reaction atom index is outside the structure")
    fixed = [
        index
        for index, flags in enumerate(first.flags)
        if first.selective and tuple(value.upper() for value in flags) == ("F", "F", "F")
    ]
    movable = [index for index in range(first.atom_count) if index not in fixed]
    reaction = [c_index, h_index]
    excluded = [
        {
            "image": image,
            "structure_path": str(paths[image].resolve()),
            "structure_sha256": row["structure_sha256"],
            "geometry_sha256": geometry_fingerprint(structures[image]),
            "reason": "source_gpu_ml_neb_path_or_current_screening_pool",
        }
        for image, row in sorted(image_rows.items())
    ]
    excluded_structure_hashes = {row["structure_sha256"] for row in excluded}
    excluded_geometry_hashes = {row["geometry_sha256"] for row in excluded}

    candidate_records: list[dict[str, Any]] = []
    candidate_structures: list[tuple[dict[str, Any], Poscar]] = []
    candidate_structure_hashes: set[str] = set()
    candidate_geometry_hashes: set[str] = set()
    source_paths = [path_manifest_path, state_path, *paths.values()]
    for specification in samples:
        left_name = specification["left_image"]
        right_name = specification["right_image"]
        if left_name not in structures or right_name not in structures:
            raise ValueError(f"sample references a missing source image: {specification}")
        left = structures[left_name]
        right = structures[right_name]
        errors = compatible(left, right)
        if errors:
            raise ValueError(f"incompatible source pair {left_name}-{right_name}: {errors}")
        fraction = specification["fraction"]
        frac = left.frac + fraction * minimum_image_delta(left.frac, right.frac)
        if fixed:
            frac[fixed] = first.frac[fixed]
        candidate = copy_with_frac(
            left,
            frac,
            f"Held-out TS validation candidate {specification['sample_id']} from {left_name}-{right_name}",
        )
        sample_dir = output / "candidates" / specification["sample_id"]
        poscar_path = sample_dir / "POSCAR"
        write_poscar(poscar_path, candidate)
        structure_sha = sha256_file(poscar_path)
        geometry_sha = geometry_fingerprint(candidate)
        if structure_sha in excluded_structure_hashes or geometry_sha in excluded_geometry_hashes:
            raise ValueError(f"candidate overlaps excluded path structure: {specification['sample_id']}")
        if structure_sha in training_hashes or geometry_sha in training_geometries:
            raise ValueError(f"candidate overlaps active training or replay evidence: {specification['sample_id']}")
        if structure_sha in candidate_structure_hashes or geometry_sha in candidate_geometry_hashes:
            raise ValueError(f"duplicate held-out candidate: {specification['sample_id']}")
        candidate_structure_hashes.add(structure_sha)
        candidate_geometry_hashes.add(geometry_sha)
        comparisons = [
            {
                "image": image,
                "movable_rmsd_A": _rmsd(structures[image], candidate, movable),
                "reaction_atom_rmsd_A": _rmsd(structures[image], candidate, reaction),
            }
            for image in sorted(structures)
        ]
        nearest = min(comparisons, key=lambda row: row["movable_rmsd_A"])
        minimum_distance, minimum_pair = minimum_pair_distance(candidate)
        record = {
            **specification,
            "construction": "minimum_image_midpoint_resampling_without_AQCat_or_VASP_evaluation",
            "structure_path": str(poscar_path.relative_to(output).as_posix()),
            "structure_sha256": structure_sha,
            "geometry_sha256": geometry_sha,
            "atom_count": candidate.atom_count,
            "fixed_atom_count": len(fixed),
            "c_h_distance_A": pbc_distance(candidate, c_index, h_index),
            "minimum_pair_distance_A": minimum_distance,
            "minimum_pair_indices_zero_based": list(minimum_pair),
            "nearest_excluded_path_image": nearest,
            "c_nearest_fe": _nearest_fe(candidate, c_index, 2.30),
            "h_nearest_fe": _nearest_fe(candidate, h_index, 2.00),
            "checks": {
                "exact_structure_hash_disjoint": True,
                "rounded_geometry_hash_disjoint": True,
                "fixed_layer_preserved": bool(
                    not fixed or np.array_equal(candidate.frac[fixed], first.frac[fixed])
                ),
                "periodic_mapping": "minimum_image_between_adjacent_source_images",
                "not_evaluated_by_current_checkpoint": True,
                "not_vasp_labeled": True,
            },
        }
        candidate_records.append(record)
        candidate_structures.append((record, candidate))

    roles = {record["role"] for record in candidate_records}
    output.mkdir(parents=True, exist_ok=True)
    exclusions_path = write_json(
        output / "excluded_current_path_structures.json",
        {
            "schema_version": 1,
            "document_kind": "aqcat25_ts_heldout_exclusion_manifest",
            "source_path_manifest": str(path_manifest_path.resolve()),
            "source_path_manifest_sha256": sha256_file(path_manifest_path),
            "excluded_structures": excluded,
        },
    )
    training_exclusions_path = write_json(
        output / "excluded_training_and_replay_hashes.json",
        {
            "schema_version": 1,
            "document_kind": "aqcat25_ts_training_replay_exclusion_evidence",
            "active_learning_state": str(state_path.resolve()),
            "active_learning_state_sha256": sha256_file(state_path),
            "policy": str(policy_path.resolve()),
            "policy_sha256": sha256_file(policy_path),
            "training_and_replay_structure_hash_count": len(training_hashes),
            "training_and_replay_geometry_count": len(training_geometries),
            "training_and_replay_structure_hashes": sorted(training_hashes),
            "training_and_replay_geometry_hashes": sorted(training_geometries),
            "candidate_checks": [
                {
                    "sample_id": record["sample_id"],
                    "structure_hash_overlap": False,
                    "geometry_hash_overlap": False,
                }
                for record in candidate_records
            ],
        },
    )
    montage_path = output / "heldout_candidate_montage.png"
    _render(candidate_structures, montage_path, c_index, h_index)
    payload = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_independent_validation_candidate_plan",
        "status": "prepared_for_user_geometry_review_not_submitted",
        "checkpoint_sha256": state["rounds"][-1]["candidate"]["checkpoint_sha256"],
        "compatibility_sha256": state["compatibility_sha256"],
        "reaction_domain": "Fe110_C_plus_H_to_CH_hydrogen_transfer",
        "reaction_atom_indices_zero_based": [c_index, h_index],
        "reaction_atom_indices_one_based": [c_index + 1, h_index + 1],
        "source_path_manifest": str(path_manifest_path.resolve()),
        "source_path_manifest_sha256": sha256_file(path_manifest_path),
        "active_learning_state": str(state_path.resolve()),
        "active_learning_state_sha256": sha256_file(state_path),
        "exclusion_manifest": str(exclusions_path.relative_to(output).as_posix()),
        "exclusion_manifest_sha256": sha256_file(exclusions_path),
        "training_replay_exclusion_evidence": str(
            training_exclusions_path.relative_to(output).as_posix()
        ),
        "training_replay_exclusion_evidence_sha256": sha256_file(training_exclusions_path),
        "selection_policy": {
            "minimum_samples": 5,
            "required_roles": sorted(ROLE_VALUES),
            "candidate_count": len(candidate_records),
            "roles_present": sorted(roles),
            "freeze_before_vasp_labeling": True,
            "exclude_all_candidate_hashes_from_training_and_replay": True,
            "retain_at_least_five_after_user_geometry_review": True,
        },
        "candidates": candidate_records,
        "review_artifacts": [
            {"path": montage_path.name, "sha256": sha256_file(montage_path)},
            {"path": "geometry_review.csv"},
        ],
        "source_files": source_file_manifest(source_paths),
        "authorization": {
            "vasp_submission_authorized": False,
            "gpu_submission_authorized": False,
            "fine_tuning_authorized": False,
        },
        "scientific_scope": {
            "candidate_geometry_only": True,
            "ts_domain_validated": False,
            "scientifically_validated_ts": False,
            "reportable_final_energy": False,
        },
    }
    plan_path = write_json(output / "heldout_validation_candidate_plan.json", payload)
    csv_path = output / "geometry_review.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "sample_id", "role", "source_pair", "fraction", "C-H_A",
                "C-nearest-Fe_A", "H-nearest-Fe_A", "C-Fe_coord_le_2.30A",
                "H-Fe_coord_le_2.00A", "nearest_excluded_image",
                "movable_RMSD_A", "reaction_atom_RMSD_A", "structure_sha256",
            ]
        )
        for record in candidate_records:
            writer.writerow(
                [
                    record["sample_id"], record["role"],
                    f"{record['left_image']}-{record['right_image']}", record["fraction"],
                    f"{record['c_h_distance_A']:.6f}",
                    f"{record['c_nearest_fe']['three_nearest'][0]['distance_A']:.6f}",
                    f"{record['h_nearest_fe']['three_nearest'][0]['distance_A']:.6f}",
                    record["c_nearest_fe"]["coordination_count_within_cutoff"],
                    record["h_nearest_fe"]["coordination_count_within_cutoff"],
                    record["nearest_excluded_path_image"]["image"],
                    f"{record['nearest_excluded_path_image']['movable_rmsd_A']:.6f}",
                    f"{record['nearest_excluded_path_image']['reaction_atom_rmsd_A']:.6f}",
                    record["structure_sha256"],
                ]
            )
    payload["review_artifacts"][1]["sha256"] = sha256_file(csv_path)
    write_json(plan_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare disjoint geometry-only held-out TS validation candidates.")
    parser.add_argument("--path-manifest", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample", action="append", default=[])
    parser.add_argument("--c-index", type=int, default=45)
    parser.add_argument("--h-index", type=int, default=46)
    args = parser.parse_args()
    payload = prepare(
        args.path_manifest,
        args.state,
        args.output,
        [_parse_sample(value) for value in args.sample],
        args.c_index,
        args.h_index,
    )
    print(json.dumps({"status": payload["status"], "candidate_count": len(payload["candidates"])}))


if __name__ == "__main__":
    main()
