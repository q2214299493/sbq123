from __future__ import annotations

from pathlib import Path

from typing import Any

from scripts.artifact_io import sha256_file

from .active_learning_common import (
    STATE_NAME,
    contract_for_state,
    current_round,
    load_policy,
    load_state,
    utc_now,
    write_json,
)

from .contract import load_contract

from .active_learning_path_selection import _path_candidate_record

from .active_learning_path_labels import prepare_path_vasp_force_labels as prepare_path_vasp_force_labels

from .active_learning_path_labels import ingest_path_vasp_force_labels as ingest_path_vasp_force_labels

from .active_learning_path_predictions import prepare_path_force_predictions as prepare_path_force_predictions

from .active_learning_path_predictions import assess_path_force_predictions as assess_path_force_predictions

from .active_learning_path_rerun import prepare_ml_neb_path_rerun as prepare_ml_neb_path_rerun

ROOT = Path(__file__).resolve().parents[2]

def initialize_path_workflow(
    path_manifest_path: Path,
    contract_path: Path,
    policy_path: Path,
    destination: Path,
    *,
    committee_assessment_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    policy = load_policy(policy_path)
    candidate, selected, committee = _path_candidate_record(
        path_manifest_path, contract, policy, committee_assessment_path
    )
    now = utc_now()
    round_record = {
        "round_index": 0,
        "status": "awaiting_path_vasp_label_preparation",
        "candidate": candidate,
        "path_selection": {
            "source_path_manifest_sha256": candidate["manifest_sha256"],
            "committee_assessment_path": str(committee_assessment_path.resolve())
            if committee_assessment_path
            else None,
            "committee_assessment_sha256": sha256_file(committee_assessment_path)
            if committee_assessment_path
            else None,
            "committee_status": "available" if committee else "single_checkpoint_no_committee",
            "selected_images": selected,
        },
        "path_vasp_force_labels": [],
        "path_force_predictions": [],
        "force_agreement": None,
        "fine_tuning": None,
        "ts_domain_assessment": None,
        "job_evidence": {},
    }
    state = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_active_learning_state",
        "workflow_kind": policy["workflow_kind"],
        "reaction_id": contract["reaction_id"],
        "contract_sha256": contract["contract_sha256"],
        "atom_map_sha256": contract["atom_map_sha256"],
        "compatibility_sha256": contract["compatibility_sha256"],
        "policy_path": str(policy_path.resolve()),
        "policy_sha256": sha256_file(policy_path),
        "status": round_record["status"],
        "next_action": "prepare_hash_bound_path_vasp_label_batch",
        "rounds": [round_record],
        "data_policy": policy["data_policy"],
        "created_at": now,
        "updated_at": now,
    }
    if not dry_run:
        if destination.exists() and any(destination.iterdir()):
            raise FileExistsError(f"active-learning destination is not empty: {destination}")
        write_json(destination / STATE_NAME, state)
    return state

def register_next_path(
    state_path: Path,
    path_manifest_path: Path,
    contract_path: Path,
    *,
    committee_assessment_path: Path | None = None,
) -> dict[str, Any]:
    state = load_state(state_path)
    current = current_round(state)
    if current["status"] != "awaiting_ml_neb_path_rerun_result":
        raise ValueError("current round is not awaiting an ML-NEB path rerun")
    policy = load_policy(Path(state["policy_path"]))
    next_index = int(current["round_index"]) + 1
    if next_index >= int(policy["round_control"]["max_rounds"]):
        state["status"] = "blocked_maximum_active_learning_rounds_reached"
        state["next_action"] = "human_review_required"
        state["updated_at"] = utc_now()
        write_json(state_path, state)
        raise ValueError("maximum active-learning rounds reached")
    contract = contract_for_state(contract_path, state)
    candidate, selected, committee = _path_candidate_record(
        path_manifest_path, contract, policy, committee_assessment_path
    )
    expected_checkpoint = state["latest_finetuned_checkpoint"]["sha256"]
    if candidate["checkpoint_sha256"] != expected_checkpoint:
        raise ValueError("ML-NEB path rerun did not use the registered fine-tuned checkpoint")
    state["rounds"].append(
        {
            "round_index": next_index,
            "status": "awaiting_path_vasp_label_preparation",
            "candidate": candidate,
            "path_selection": {
                "source_path_manifest_sha256": candidate["manifest_sha256"],
                "committee_assessment_path": str(committee_assessment_path.resolve())
                if committee_assessment_path
                else None,
                "committee_assessment_sha256": sha256_file(committee_assessment_path)
                if committee_assessment_path
                else None,
                "committee_status": "available" if committee else "single_checkpoint_no_committee",
                "selected_images": selected,
            },
            "path_vasp_force_labels": [],
            "path_force_predictions": [],
            "force_agreement": None,
            "fine_tuning": None,
            "ts_domain_assessment": None,
            "job_evidence": {},
        }
    )
    state["status"] = "awaiting_path_vasp_label_preparation"
    state["next_action"] = "prepare_hash_bound_path_vasp_label_batch"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return state
