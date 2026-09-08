#!/usr/bin/env python3
"""Prepare round-0 exact dual-model predictions from a reviewed ML-path snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.dual_model_ts_force_prediction_batch import validate_request


def _empty_destination(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)


def _safe_snapshot_file(snapshot_root: Path, relative_value: str) -> Path:
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("snapshot image path is unsafe")
    resolved_root = snapshot_root.resolve()
    candidate = (resolved_root / relative).resolve()
    if resolved_root not in candidate.parents or not candidate.is_file():
        raise FileNotFoundError(f"snapshot image is missing: {relative_value}")
    return candidate


def prepare_round(  # noqa: C901 - preparation is a linear, fail-fast evidence gate.
    source_request_path: Path,
    snapshot_manifest_path: Path,
    failure_guard_path: Path,
    policy_path: Path,
    destination: Path,
    *,
    failure_restart_root: Path | None = None,
) -> dict[str, Any]:
    _empty_destination(destination)
    source_request = load_json_object(source_request_path)
    snapshot = load_json_object(snapshot_manifest_path)
    failure = load_json_object(failure_guard_path)
    policy = load_json_object(policy_path) if policy_path.suffix == ".json" else None
    if policy is not None:
        raise ValueError("dual-model policy must remain YAML and is bound by file hash only")
    if source_request.get("document_kind") != "dual_model_ml_neb_request":
        raise ValueError("invalid source dual-model request")
    if snapshot.get("document_kind") != "dual_model_ml_neb_stage_snapshot":
        raise ValueError("invalid stage snapshot manifest")
    if failure.get("document_kind") != "dual_model_ml_neb_geometry_guard_failure":
        raise ValueError("invalid release failure evidence")
    request_sha = sha256_file(source_request_path)
    if snapshot.get("source_request_sha256") != request_sha:
        raise ValueError("snapshot is not bound to the source request")
    if failure.get("source_request_sha256") != request_sha:
        raise ValueError("failure evidence is not bound to the source request")
    if snapshot.get("runner_sha256") != failure.get("runner_sha256"):
        raise ValueError("snapshot and failure evidence use different runners")
    if snapshot.get("scientific_status") != "restrained_path_snapshot_not_mep":
        raise ValueError("unexpected snapshot scientific status")
    if snapshot.get("converged") is not True or snapshot.get("geometry_guards", {}).get("passed") is not True:
        raise ValueError("source stage snapshot is not converged and geometry-valid")
    if failure.get("geometry_guards", {}).get("passed") is not False:
        raise ValueError("release evidence does not record a geometry-guard failure")

    snapshot_root = snapshot_manifest_path.parent
    structures_dir = destination / "structures"
    structures_dir.mkdir()
    structure_rows: list[dict[str, Any]] = []
    seen_images: set[str] = set()
    for row in snapshot.get("images", []):
        image = str(row.get("image", ""))
        if not image or image in seen_images:
            raise ValueError("snapshot image IDs must be non-empty and unique")
        seen_images.add(image)
        source = _safe_snapshot_file(snapshot_root, str(row.get("path", "")))
        if sha256_file(source) != row.get("sha256"):
            raise ValueError(f"snapshot image {image} hash mismatch")
        target = structures_dir / f"pre_{image}.vasp"
        shutil.copy2(source, target)
        if sha256_file(target) != row["sha256"]:
            raise RuntimeError(f"copied snapshot image {image} changed")
        structure_rows.append(
            {
                "sample_id": f"pre_{image}",
                "image": image,
                "source_stage": str(snapshot["stage"]),
                "selection_role": "complete_restrained_path_member",
                "path": target.relative_to(destination).as_posix(),
                "sha256": row["sha256"],
            }
        )
    if len(structure_rows) != int(snapshot.get("image_count", -1)):
        raise ValueError("snapshot image count mismatch")

    failure_bond = failure["geometry_guards"]["monitored_bonds"][0]
    snapshot_bond = snapshot["geometry_guards"]["monitored_bonds"][0]
    lost_interval_images = sorted(
        set(snapshot_bond["covered_internal_images"])
        - set(failure_bond["covered_internal_images"])
    )
    boundary_pairs: list[dict[str, Any]] = []
    if lost_interval_images and failure_restart_root is None:
        raise ValueError("failure restart root is required for a lost-coverage boundary")
    for image in lost_interval_images:
        image_index = int(image)
        source = failure_restart_root / image / "POSCAR"
        if not source.is_file():
            raise FileNotFoundError(f"failure-boundary structure is missing: {source}")
        atoms = read(source, format="vasp")
        first, second = (int(value) for value in failure_bond["atoms_zero_based"])
        observed_distance = float(atoms.get_distance(first, second, mic=True))
        expected_distance = float(failure_bond["distances_A"][image_index])
        if abs(observed_distance - expected_distance) > 1.0e-6:
            raise ValueError(f"failure-boundary distance mismatch for image {image}")
        target = structures_dir / f"fail_{image}.vasp"
        shutil.copy2(source, target)
        failure_sha = sha256_file(target)
        structure_rows.append(
            {
                "sample_id": f"fail_{image}",
                "image": image,
                "source_stage": str(failure["stage"]),
                "selection_role": "first_geometry_valid_failure_point",
                "path": target.relative_to(destination).as_posix(),
                "sha256": failure_sha,
            }
        )
        pre_row = next(row for row in structure_rows if row["sample_id"] == f"pre_{image}")
        pre_row["selection_role"] = "last_geometry_valid_point"
        boundary_pairs.append(
            {
                "image": image,
                "last_geometry_valid_sample": f"pre_{image}",
                "first_geometry_valid_failure_sample": f"fail_{image}",
                "last_valid_structure_sha256": pre_row["sha256"],
                "first_failure_structure_sha256": failure_sha,
                "reaction_coordinate_before_A": float(snapshot_bond["distances_A"][image_index]),
                "reaction_coordinate_after_A": observed_distance,
            }
        )

    models = source_request["models"]
    prediction_request = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_path_force_prediction_batch_request",
        "reaction_id": source_request["reaction"]["reaction_id"],
        "round_index": 0,
        "source": {
            "dual_model_path_request_sha256": request_sha,
            "stage_snapshot_manifest_sha256": sha256_file(snapshot_manifest_path),
            "release_failure_guard_sha256": sha256_file(failure_guard_path),
            "source_scientific_status": snapshot["scientific_status"],
            "active_learning_trigger": "first_restraint_release_lost_required_OH_interval_coverage",
        },
        "models": {
            role: {
                "backend": models[role]["backend"],
                "identifier": models[role].get("identifier"),
                "checkpoint_path": models[role]["remote_checkpoint_path"],
                "checkpoint_sha256": models[role]["checkpoint_sha256"],
            }
            for role in ("primary", "secondary")
        },
        "indexed_bond_changes": source_request["reaction"]["indexed_bond_changes"],
        "fixed_atom_indices_zero_based": source_request["fixed_atom_indices_zero_based"],
        "structures": structure_rows,
        "automatic_vasp_submission": False,
    }
    prediction_request_path = destination / "dual_model_prediction_batch_request.json"
    write_json_atomic(prediction_request_path, prediction_request, ensure_ascii=True)
    validate_request(prediction_request_path)

    state = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_active_learning_state",
        "workflow_kind": "matris_primary_aqcat25_secondary_ts_active_learning",
        "reaction_id": source_request["reaction"]["reaction_id"],
        "round_index": 0,
        "status": "awaiting_exact_dual_model_gpu_predictions",
        "source_bindings": {
            "source_request": {"path": str(source_request_path.resolve()), "sha256": request_sha},
            "snapshot_manifest": {
                "path": str(snapshot_manifest_path.resolve()),
                "sha256": sha256_file(snapshot_manifest_path),
            },
            "failure_guard": {
                "path": str(failure_guard_path.resolve()),
                "sha256": sha256_file(failure_guard_path),
            },
            "failure_restart_root": (
                str(failure_restart_root.resolve()) if failure_restart_root else None
            ),
            "policy": {"path": str(policy_path.resolve()), "sha256": sha256_file(policy_path)},
        },
        "round_trigger": {
            "stage": failure["stage"],
            "decision": "ACTIVE_LEARNING_ELIGIBLE_FROM_LAST_VALID_AND_FIRST_VALID_FAILURE_BOUNDARY",
            "model_error_assumed": False,
            "snapshot_covered_internal_images": snapshot_bond["covered_internal_images"],
            "failed_covered_internal_images": failure_bond["covered_internal_images"],
            "required_internal_images": failure_bond["minimum_internal_images"],
            "failure_boundary_pairs": boundary_pairs,
            "other_geometry_guards_passed": {
                "C_C_preserved": all(
                    row["passed"] for row in failure["geometry_guards"]["preserved_bonds"]
                ),
                "O_H_monotonic": failure_bond["monotonic_passed"],
                "adjacent_rmsd": failure["geometry_guards"]["adjacent_rmsd_passed"],
                "single_atom_step": failure["geometry_guards"][
                    "maximum_single_movable_atom_step_passed"
                ],
                "periodic_branch": failure["geometry_guards"]["periodic_branch_numeric_passed"],
            },
        },
        "prediction_batch": {
            "path": str(prediction_request_path.resolve()),
            "sha256": sha256_file(prediction_request_path),
            "sample_count": len(structure_rows),
            "status": "prepared_not_submitted",
        },
        "required_next_stages": [
            "run_exact_dual_model_predictions_on_MZ73",
            "score_cluster_and_select_path_plus_failure_boundary_candidates",
            "prepare_exact_structure_VASP_force_labels",
            "compare_each_model_against_VASP",
            "fine_tune_MatRIS_if_gate_fails",
            "rerun_complete_path_with_new_checkpoint",
            "pass_disjoint_heldout_VASP_validation",
        ],
        "automatic_local_actions": [
            "preserve_valid_boundary_structures",
            "prepare_prediction_and_committee_requests_when_checkpoints_exist",
            "score_cluster_and_select_after_predictions_return",
            "prepare_vasp_label_batch_after_selection",
            "assess_model_specific_errors_after_quality_passed_labels_return",
            "prepare_finetune_or_heldout_next_stage_from_the_error_decision",
        ],
        "automatic_submission": False,
        "scientific_status": "round_0_prepared_not_calibrated",
        "automatic_vasp_submission": False,
    }
    state_path = destination / "active_learning_state.json"
    write_json_atomic(state_path, state, ensure_ascii=True)
    receipt = {
        "status": state["status"],
        "active_learning_state_sha256": sha256_file(state_path),
        "prediction_batch_sha256": sha256_file(prediction_request_path),
        "gpu_jobs_submitted": 0,
        "vasp_jobs_submitted": 0,
    }
    write_json_atomic(destination / "PREPARED_NOT_SUBMITTED.json", receipt, ensure_ascii=True)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a hash-bound dual-model TS active-learning round without submission."
    )
    parser.add_argument("--source-request", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--failure-guard", type=Path, required=True)
    parser.add_argument("--failure-restart-root", type=Path)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    state = prepare_round(
        args.source_request,
        args.snapshot_manifest,
        args.failure_guard,
        args.policy,
        args.destination,
        failure_restart_root=args.failure_restart_root,
    )
    print(
        json.dumps(
            {
                "status": state["status"],
                "sample_count": state["prediction_batch"]["sample_count"],
                "gpu_jobs_submitted": 0,
                "vasp_jobs_submitted": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
