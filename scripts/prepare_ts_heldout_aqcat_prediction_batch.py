from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from scripts.aqcat25_calibration import parse_poscar_symbols
from scripts.aqcat25_handoff import atom_order_sha256
from scripts.aqcat25_ts_force_prediction_batch import validate_batch
from scripts.aqcat25_ts_schema import load_document
from scripts.artifact_io import sha256_file, write_json
from scripts.artifact_io import require_sha256 as _require_sha256
from scripts.artifact_io import load_json_object as _load


CHECKPOINT_PATH = "/home/sbq/sbq/aqcat25/demo_single/model.pt"






def _load_completed_plan(
    candidate_plan_path: Path, completion_summary_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = _load(candidate_plan_path)
    completion = _load(completion_summary_path)
    if plan.get("document_kind") != "aqcat25_ts_independent_validation_candidate_plan":
        raise ValueError("invalid held-out candidate plan")
    if completion.get("document_kind") != "heldout_vasp_force_label_completion_summary":
        raise ValueError("invalid held-out VASP completion summary")
    if completion.get("status") != "vasp_labels_ready_for_exact_checkpoint_prediction":
        raise ValueError("held-out VASP labels are not ready for exact checkpoint prediction")
    if not all(bool(value) for value in (completion.get("checks") or {}).values()):
        raise ValueError("held-out VASP completion checks did not all pass")
    return plan, completion


def prepare(
    candidate_plan_path: Path,
    vasp_label_root: Path,
    completion_summary_path: Path,
    destination: Path,
    *,
    observed_checkpoint_sha256: str,
) -> dict[str, Any]:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"destination is not empty: {destination}")
    plan, completion = _load_completed_plan(candidate_plan_path, completion_summary_path)

    checkpoint_sha256 = _require_sha256(plan.get("checkpoint_sha256", ""), label="checkpoint")
    observed_checkpoint_sha256 = _require_sha256(
        observed_checkpoint_sha256, label="observed checkpoint"
    )
    if completion.get("checkpoint_sha256_for_next_prediction") != checkpoint_sha256:
        raise ValueError("VASP completion checkpoint binding does not match candidate plan")
    if observed_checkpoint_sha256 != checkpoint_sha256:
        raise ValueError("MZ73 checkpoint hash does not match the frozen candidate plan")
    if completion.get("compatibility_sha256") != plan.get("compatibility_sha256"):
        raise ValueError("VASP completion compatibility does not match candidate plan")

    completion_samples = {
        str(row["sample_id"]): row for row in completion.get("samples", [])
    }
    candidates = plan.get("candidates") or []
    planned_ids = {str(row["sample_id"]) for row in candidates}
    if len(candidates) < 5 or set(completion_samples) != planned_ids:
        raise ValueError("candidate and completed VASP sample sets do not match")

    destination.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    common_atom_order_sha256: str | None = None
    for candidate in candidates:
        sample_id = str(candidate["sample_id"])
        completed = completion_samples[sample_id]
        if completed.get("role") != candidate.get("role"):
            raise ValueError(f"sample role mismatch: {sample_id}")
        if not (
            completed.get("structure_hash_match")
            and completed.get("normal_completion")
            and completed.get("electronically_converged")
            and int(completed.get("force_rows", 0)) == int(candidate.get("atom_count", 0))
        ):
            raise ValueError(f"completed VASP label is not acceptable: {sample_id}")

        source = vasp_label_root / sample_id / "POSCAR"
        if not source.is_file() or sha256_file(source) != candidate.get("structure_sha256"):
            raise ValueError(f"exact held-out POSCAR hash mismatch: {sample_id}")
        label_request = _load(vasp_label_root / sample_id / "label_request.json")
        if (
            label_request.get("candidate_structure_sha256") != candidate.get("structure_sha256")
            or label_request.get("checkpoint_sha256_for_later_exact_prediction")
            != checkpoint_sha256
        ):
            raise ValueError(f"VASP label request binding mismatch: {sample_id}")

        sample_dir = destination / sample_id
        sample_dir.mkdir(parents=True, exist_ok=False)
        target = sample_dir / "POSCAR"
        shutil.copy2(source, target)
        symbols = parse_poscar_symbols(target)
        order_sha256 = atom_order_sha256(symbols)
        if common_atom_order_sha256 is None:
            common_atom_order_sha256 = order_sha256
        elif order_sha256 != common_atom_order_sha256:
            raise ValueError("held-out prediction structures do not share one atom order")
        adsorbate_indices = [
            index for index, symbol in enumerate(symbols, start=1) if symbol != "Fe"
        ]
        if adsorbate_indices != [46, 47]:
            raise ValueError(f"unexpected adsorbate indices for {sample_id}: {adsorbate_indices}")

        request = {
            "schema_version": 1,
            "document_kind": "aqcat25_ts_force_prediction_request",
            "reaction_id": completion["reaction_id"],
            "round_index": 0,
            "structure": {
                "path": "POSCAR",
                "sha256": sha256_file(target),
                "atom_order_sha256": order_sha256,
            },
            "checkpoint": {
                "path": CHECKPOINT_PATH,
                "sha256": checkpoint_sha256,
            },
            "indexed_bond_changes": [
                {"atoms_1based": [46, 47], "change": "form"}
            ],
            "adsorbate_indices_1based": adsorbate_indices,
            "result_class": "predicted_transition_state_candidate_only",
            "restrictions": {
                "backend": "MZ73",
                "reportable_dft": False,
                "automatic_submission": False,
            },
        }
        request_path = write_json(sample_dir / "prediction_request.json", request)
        load_document(request_path, expected_kind="aqcat25_ts_force_prediction_request")
        prepared.append(
            {
                "sample_id": sample_id,
                "role": candidate["role"],
                "request": request_path.relative_to(destination).as_posix(),
                "request_sha256": sha256_file(request_path),
                "structure_sha256": sha256_file(target),
                "vasp_job_id": completed["job_id"],
                "vasp_outcar_sha256": completed["outcar_sha256"],
            }
        )

    batch = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_path_force_prediction_batch_request",
        "reaction_id": completion["reaction_id"],
        "round_index": 0,
        "checkpoint": {"path": CHECKPOINT_PATH, "sha256": checkpoint_sha256},
        "source_path_manifest_sha256": plan["source_path_manifest_sha256"],
        "source_heldout_candidate_plan_sha256": sha256_file(candidate_plan_path),
        "source_vasp_completion_summary_sha256": sha256_file(completion_summary_path),
        "prediction_scope": "independent_heldout_exact_structure_force_validation",
        "predictions": [
            {
                "image": row["sample_id"],
                "request": row["request"],
                "request_sha256": row["request_sha256"],
                "structure_sha256": row["structure_sha256"],
            }
            for row in prepared
        ],
        "automatic_submission": False,
    }
    batch_path = write_json(destination / "heldout_prediction_batch_request.json", batch)
    validate_batch(batch_path)

    review = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_heldout_force_prediction_batch_review",
        "status": "prepared_for_user_review_not_submitted",
        "batch_request": {
            "path": batch_path.name,
            "sha256": sha256_file(batch_path),
        },
        "reaction_id": completion["reaction_id"],
        "samples": prepared,
        "checkpoint": {
            "path_on_mz73": CHECKPOINT_PATH,
            "expected_sha256": checkpoint_sha256,
            "observed_sha256": observed_checkpoint_sha256,
            "read_only_remote_check_passed": True,
        },
        "checks": {
            "six_unique_samples": len(prepared) == 6
            and len({row["sample_id"] for row in prepared}) == 6,
            "all_vasp_labels_completed_and_electronically_converged": True,
            "all_request_schemas_valid": True,
            "all_poscar_hashes_match_frozen_vasp_labels": True,
            "all_request_hashes_match_batch_manifest": True,
            "atom_order_sha256": common_atom_order_sha256,
            "adsorbate_indices_1based": [46, 47],
            "indexed_bond_change": "form C46-H47",
            "portable_posix_relative_paths": True,
            "automatic_submission": False,
            "remote_transfer_performed": False,
            "gpu_job_submitted": False,
        },
        "scientific_scope": {
            "result_class": "predicted_transition_state_candidate_only",
            "reportable_dft": False,
            "force_comparison_role": "independent_current_path_neighborhood_checkpoint_calibration",
            "ts_or_barrier_claim": False,
        },
        "next_action": "await_explicit_user_authorization_before_upload_and_MZ73_execution",
    }
    review_path = write_json(destination / "heldout_prediction_batch_review.json", review)
    receipt = {
        "status": review["status"],
        "batch_request": batch_path.name,
        "batch_request_sha256": sha256_file(batch_path),
        "review": review_path.name,
        "review_sha256": sha256_file(review_path),
        "sample_count": len(prepared),
        "remote_transfer_performed": False,
        "gpu_jobs_submitted": 0,
    }
    write_json(destination / "PREPARED_NOT_SUBMITTED.json", receipt)
    return review


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare exact-structure held-out AQCat25 force predictions without transfer or execution."
    )
    parser.add_argument("--candidate-plan", type=Path, required=True)
    parser.add_argument("--vasp-label-root", type=Path, required=True)
    parser.add_argument("--completion-summary", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--observed-checkpoint-sha256", required=True)
    args = parser.parse_args()
    review = prepare(
        args.candidate_plan,
        args.vasp_label_root,
        args.completion_summary,
        args.destination,
        observed_checkpoint_sha256=args.observed_checkpoint_sha256,
    )
    print(
        json.dumps(
            {
                "status": review["status"],
                "sample_count": len(review["samples"]),
                "gpu_jobs_submitted": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
