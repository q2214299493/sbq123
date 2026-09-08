#!/usr/bin/env python3
"""Prepare frozen dual-model prediction and VASP held-out validation packages."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.matris_training_exclusions import write_heldout_exclusion_manifest
from scripts.vasp_inputs import build_fe110_active_learning_force_label


def prepare(
    plan_path: Path,
    state_path: Path,
    source_prediction_batch_path: Path,
    profile_path: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    plan = load_json_object(plan_path)
    state = load_json_object(state_path)
    source_prediction_batch = load_json_object(source_prediction_batch_path)
    if plan.get("document_kind") != "dual_model_ts_heldout_validation_candidate_plan":
        raise ValueError("invalid held-out candidate plan")
    if plan.get("status") != "prepared_for_user_geometry_review_not_submitted":
        raise ValueError("held-out candidate plan is not reviewable")
    if state.get("document_kind") != "dual_model_ts_active_learning_state":
        raise ValueError("invalid dual-model active-learning state")
    heldout_ref = state.get("heldout_validation_plan") or {}
    if heldout_ref.get("sha256") != sha256_file(plan_path):
        raise ValueError("active-learning state is not bound to the held-out plan")
    if state.get("status") != "awaiting_user_heldout_geometry_review":
        raise ValueError("active-learning state is not awaiting held-out review")
    if source_prediction_batch.get("document_kind") != (
        "dual_model_ts_path_force_prediction_batch_request"
    ):
        raise ValueError("invalid source prediction batch")
    if source_prediction_batch.get("reaction_id") != plan.get("reaction_id"):
        raise ValueError("source prediction batch reaction mismatch")

    output.mkdir(parents=True, exist_ok=True)
    gpu_root = output / "gpu_prediction"
    gpu_structures = gpu_root / "structures"
    vasp_root = output / "vasp_static_labels"
    gpu_structures.mkdir(parents=True)
    vasp_root.mkdir(parents=True)
    exclusion_manifest_path = output / "heldout_training_exclusions.json"
    write_heldout_exclusion_manifest(plan_path, exclusion_manifest_path)

    prediction_rows = []
    vasp_rows = []
    for index, candidate in enumerate(plan["candidates"]):
        sample_id = candidate["sample_id"]
        source = plan_path.parent / candidate["structure_path"]
        if not source.is_file() or sha256_file(source) != candidate["structure_sha256"]:
            raise ValueError(f"held-out structure binding failed: {sample_id}")

        gpu_target = gpu_structures / f"{sample_id}.vasp"
        shutil.copy2(source, gpu_target)
        if sha256_file(gpu_target) != candidate["structure_sha256"]:
            raise RuntimeError(f"GPU structure copy changed: {sample_id}")
        prediction_rows.append(
            {
                "sample_id": sample_id,
                "image": f"{index:02d}",
                "source_stage": "heldout_TS_validation",
                "selection_role": candidate["role"],
                "path": f"structures/{sample_id}.vasp",
                "sha256": candidate["structure_sha256"],
                "primary_metric_eligible": candidate["primary_heldout_metric_eligible"],
            }
        )

        sample_dir = vasp_root / sample_id
        sample_dir.mkdir()
        vasp_target = sample_dir / "POSCAR"
        shutil.copy2(source, vasp_target)
        if sha256_file(vasp_target) != candidate["structure_sha256"]:
            raise RuntimeError(f"VASP structure copy changed: {sample_id}")
        input_profile = build_fe110_active_learning_force_label(
            sample_dir, profile_path=profile_path
        )
        label_request = {
            "schema_version": 1,
            "document_kind": "dual_model_ts_heldout_vasp_force_label_request",
            "reaction_id": plan["reaction_id"],
            "round_index": plan["round_index"],
            "sample_id": sample_id,
            "role": candidate["role"],
            "primary_metric_eligible": candidate["primary_heldout_metric_eligible"],
            "structure_sha256": candidate["structure_sha256"],
            "geometry_sha256": candidate["geometry_sha256"],
            "heldout_plan_sha256": sha256_file(plan_path),
            "frozen_model_checkpoint_sha256": {
                role: source_prediction_batch["models"][role]["checkpoint_sha256"]
                for role in ("primary", "secondary")
            },
            "requested_backend": "sunboquan-codex",
            "input_profile": input_profile,
            "required_outputs": [
                "final_TOTEN_force_label_only",
                "complete_all_atom_force_block",
                "total_magnetic_moment",
                "atom_resolved_magnetic_moments",
            ],
            "reportable_final_energy": False,
            "automatic_submission": False,
        }
        label_request_path = sample_dir / "label_request.json"
        write_json_atomic(label_request_path, label_request, ensure_ascii=True)
        vasp_rows.append(
            {
                "sample_id": sample_id,
                "role": candidate["role"],
                "primary_metric_eligible": candidate["primary_heldout_metric_eligible"],
                "directory": sample_id,
                "structure_sha256": candidate["structure_sha256"],
                "geometry_sha256": candidate["geometry_sha256"],
                "label_request_sha256": sha256_file(label_request_path),
                "status": "prepared_not_submitted",
            }
        )

    prediction_request = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_path_force_prediction_batch_request",
        "reaction_id": plan["reaction_id"],
        "round_index": plan["round_index"],
        "source": {
            "heldout_plan_sha256": sha256_file(plan_path),
            "active_learning_state_sha256": sha256_file(state_path),
            "heldout_training_exclusion_manifest_sha256": sha256_file(
                exclusion_manifest_path
            ),
            "purpose": "frozen_checkpoint_disjoint_heldout_TS_validation",
        },
        "models": source_prediction_batch["models"],
        "indexed_bond_changes": source_prediction_batch["indexed_bond_changes"],
        "fixed_atom_indices_zero_based": source_prediction_batch[
            "fixed_atom_indices_zero_based"
        ],
        "structures": prediction_rows,
        "automatic_vasp_submission": False,
        "scientific_scope": {
            "prediction_only": True,
            "calibrated_uncertainty": False,
            "accepted_TS_or_barrier": False,
        },
    }
    prediction_request_path = gpu_root / "dual_model_prediction_batch_request.json"
    write_json_atomic(prediction_request_path, prediction_request, ensure_ascii=True)

    vasp_batch = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_heldout_vasp_force_label_batch_request",
        "reaction_id": plan["reaction_id"],
        "round_index": plan["round_index"],
        "heldout_plan_sha256": sha256_file(plan_path),
        "heldout_training_exclusion_manifest_sha256": sha256_file(
            exclusion_manifest_path
        ),
        "frozen_prediction_request_sha256": sha256_file(prediction_request_path),
        "labels": vasp_rows,
        "compatibility": {
            "profile_path": str(profile_path.resolve()),
            "profile_sha256": sha256_file(profile_path),
            "ISMEAR": 1,
            "SIGMA_eV": 0.2,
            "NSW": 0,
            "reportable_final_energy": False,
        },
        "submission_policy": {
            "automatic_submission": False,
            "direct_gpu_to_vasp_handoff": False,
            "requires_hash_bound_user_authorization": True,
        },
    }
    vasp_batch_path = vasp_root / "heldout_vasp_batch_request.json"
    write_json_atomic(vasp_batch_path, vasp_batch, ensure_ascii=True)

    summary = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_heldout_execution_preparation_summary",
        "status": "prepared_not_submitted",
        "heldout_plan_sha256": sha256_file(plan_path),
        "heldout_training_exclusion_manifest": {
            "path": str(exclusion_manifest_path.resolve()),
            "sha256": sha256_file(exclusion_manifest_path),
            "sample_count": len(plan["candidates"]),
        },
        "prediction_request": {
            "path": str(prediction_request_path.resolve()),
            "sha256": sha256_file(prediction_request_path),
            "sample_count": len(prediction_rows),
        },
        "vasp_batch_request": {
            "path": str(vasp_batch_path.resolve()),
            "sha256": sha256_file(vasp_batch_path),
            "sample_count": len(vasp_rows),
        },
        "jobs_submitted": {"gpu": 0, "vasp": 0},
    }
    write_json_atomic(output / "preparation_summary.json", summary, ensure_ascii=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--source-prediction-batch", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(
                args.plan,
                args.state,
                args.source_prediction_batch,
                args.profile,
                args.output,
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
