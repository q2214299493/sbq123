from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from scripts.artifact_io import sha256_file, write_json
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import build_fe110_active_learning_force_label
from scripts.artifact_io import load_json_object as _load


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "configs" / "true_fe110_production.yaml"




def prepare(plan_path: Path, acceptance_path: Path, state_path: Path, destination: Path) -> dict[str, Any]:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"destination is not empty: {destination}")
    plan = _load(plan_path)
    acceptance = _load(acceptance_path)
    state = _load(state_path)
    if plan.get("status") != "prepared_for_user_geometry_review_not_submitted":
        raise ValueError("held-out candidate plan is not reviewable")
    if acceptance.get("status") != "accepted_all_six_and_frozen":
        raise ValueError("all-six frozen geometry acceptance is missing")
    if acceptance.get("source_plan_sha256") != sha256_file(plan_path):
        raise ValueError("geometry acceptance is not bound to the current candidate plan")
    if state.get("status") != "awaiting_independent_ts_domain_validation":
        raise ValueError("active-learning state is not awaiting independent TS-domain validation")
    if plan.get("checkpoint_sha256") != state["rounds"][-1]["candidate"]["checkpoint_sha256"]:
        raise ValueError("candidate plan checkpoint mismatch")
    if plan.get("compatibility_sha256") != state.get("compatibility_sha256"):
        raise ValueError("candidate plan compatibility mismatch")

    accepted = {row["sample_id"]: row for row in acceptance.get("accepted_samples", [])}
    candidates = plan.get("candidates") or []
    if len(candidates) != 6 or set(accepted) != {row["sample_id"] for row in candidates}:
        raise ValueError("acceptance must freeze exactly the six planned candidates")
    destination.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    for candidate in candidates:
        sample_id = candidate["sample_id"]
        frozen = accepted[sample_id]
        if frozen.get("structure_sha256") != candidate.get("structure_sha256"):
            raise ValueError(f"frozen structure hash mismatch: {sample_id}")
        if frozen.get("geometry_sha256") != candidate.get("geometry_sha256"):
            raise ValueError(f"frozen geometry hash mismatch: {sample_id}")
        source = plan_path.parent / candidate["structure_path"]
        if sha256_file(source) != candidate["structure_sha256"]:
            raise ValueError(f"source POSCAR hash mismatch: {sample_id}")
        sample_dir = destination / sample_id
        sample_dir.mkdir(parents=True, exist_ok=False)
        target = sample_dir / "POSCAR"
        shutil.copy2(source, target)
        inputs = build_fe110_active_learning_force_label(sample_dir, profile_path=PROFILE)
        request = {
            "schema_version": 1,
            "document_kind": "vasp_ts_heldout_force_label_request",
            "sample_id": sample_id,
            "role": candidate["role"],
            "reaction_id": state["reaction_id"],
            "contract_sha256": state["contract_sha256"],
            "compatibility_sha256": state["compatibility_sha256"],
            "checkpoint_sha256_for_later_exact_prediction": plan["checkpoint_sha256"],
            "candidate_structure_sha256": sha256_file(target),
            "candidate_geometry_sha256": candidate["geometry_sha256"],
            "frozen_acceptance": {
                "path": str(acceptance_path.resolve()),
                "sha256": sha256_file(acceptance_path),
            },
            "requested_backend": "sunboquan-codex",
            "scheduler": "LSF",
            "input_profile": {
                "path": inputs["profile_path"],
                "sha256": inputs["profile_sha256"],
                "stage": inputs["stage"],
                "base_profile": inputs["base_profile"],
                "compatibility_incar_source": inputs["compatibility_incar_source"],
                "compatibility_incar": inputs["compatibility_incar"],
                "final_energy_convention": inputs["final_energy_convention"],
                "gamma_mesh": inputs["gamma_mesh"],
                "cores": inputs["cores"],
            },
            "result_class_after_acceptance": "vasp_completed_electronic_converged_force_label_only",
            "reportable_final_energy": False,
            "eligible_for_training": False,
            "required_before_execution": [
                "frozen_hash_recheck",
                "approved_POTCAR",
                "diagnostic_static_preflight_pass",
                "explicit_user_batch_submission_authorization",
            ],
        }
        request_path = write_json(sample_dir / "label_request.json", request)
        preflight_result = preflight(sample_dir, "diagnostic_static")
        if not preflight_result["passed"]:
            raise ValueError(f"diagnostic-static preflight failed for {sample_id}: {preflight_result['errors']}")
        prepared.append(
            {
                "sample_id": sample_id,
                "role": candidate["role"],
                "directory": sample_id,
                "structure_sha256": sha256_file(target),
                "geometry_sha256": candidate["geometry_sha256"],
                "label_request_sha256": sha256_file(request_path),
                "preflight_sha256": sha256_file(sample_dir / "submission_preflight.json"),
                "preflight_bundle_sha256": preflight_result["bundle_sha256"],
                "status": "prepared_not_submitted",
            }
        )

    batch = {
        "schema_version": 1,
        "document_kind": "vasp_ts_heldout_force_label_batch_request",
        "status": "prepared_not_submitted",
        "reaction_id": state["reaction_id"],
        "contract_sha256": state["contract_sha256"],
        "compatibility_sha256": state["compatibility_sha256"],
        "checkpoint_sha256_for_later_exact_prediction": plan["checkpoint_sha256"],
        "source_candidate_plan": {
            "path": str(plan_path.resolve()),
            "sha256": sha256_file(plan_path),
        },
        "user_geometry_acceptance": {
            "path": str(acceptance_path.resolve()),
            "sha256": sha256_file(acceptance_path),
        },
        "samples": prepared,
        "input_contract": {
            "profile": str(PROFILE.resolve()),
            "profile_sha256": sha256_file(PROFILE),
            "stage": "transition_state.active_learning_force_label",
            "NSW": 0,
            "IBRION": -1,
            "ISMEAR": 1,
            "SIGMA_eV": 0.20,
            "gamma_mesh": [5, 5, 1],
            "cores_per_sample": 32,
            "result_scope": "exact_structure_static_force_label_only",
        },
        "submission_policy": {
            "automatic_submission": False,
            "remote_transfer_performed": False,
            "vasp_submission_authorized": False,
            "single_bounded_batch_authorization_required": True,
            "direct_gpu_to_vasp_handoff": False,
        },
        "data_policy": {
            "exclude_all_six_from_training_and_replay_for_this_checkpoint": True,
            "reportable_final_energy": False,
            "ts_domain_validated": False,
        },
    }
    batch_path = write_json(destination / "heldout_vasp_label_batch_request.json", batch)
    receipt = {
        "status": "prepared_not_submitted",
        "batch_request": batch_path.name,
        "batch_request_sha256": sha256_file(batch_path),
        "sample_count": len(prepared),
        "all_preflights_passed": True,
        "remote_transfer_performed": False,
        "jobs_submitted": 0,
    }
    write_json(destination / "PREPARED_NOT_SUBMITTED.json", receipt)
    return batch


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare frozen held-out VASP force-label inputs without submission.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    batch = prepare(args.plan, args.acceptance, args.state, args.destination)
    print(json.dumps({"status": batch["status"], "sample_count": len(batch["samples"])}))


if __name__ == "__main__":
    main()
