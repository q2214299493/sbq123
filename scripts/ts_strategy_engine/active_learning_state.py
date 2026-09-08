from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from scripts.artifact_io import sha256_file
from scripts.vasp_inputs import build_fe110_active_learning_force_label

from .active_learning_common import (
    PREDICTED_CLASS,
    STATE_NAME,
    VASP_LABEL_CLASS,
    candidate_record,
    current_round,
    load_policy,
    load_state,
    utc_now,
    write_json,
)
from .contract import load_contract


ROOT = Path(__file__).resolve().parents[2]


def initialize_workflow(
    candidate_manifest: Path,
    handoff_root: Path,
    contract_path: Path,
    policy_path: Path,
    destination: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    policy = load_policy(policy_path)
    candidate = candidate_record(candidate_manifest, handoff_root, contract)
    now = utc_now()
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
        "status": "awaiting_vasp_force_label_preparation",
        "next_action": "prepare_vasp_force_label",
        "rounds": [
            {
                "round_index": 0,
                "status": "awaiting_vasp_force_label_preparation",
                "candidate": candidate,
                "vasp_force_label": None,
                "force_agreement": None,
                "force_prediction": None,
                "fine_tuning": None,
                "ts_domain_assessment": None,
                "job_evidence": {},
            }
        ],
        "data_policy": policy["data_policy"],
        "created_at": now,
        "updated_at": now,
    }
    if not dry_run:
        if destination.exists() and any(destination.iterdir()):
            raise FileExistsError(f"active-learning destination is not empty: {destination}")
        write_json(destination / STATE_NAME, state)
    return state


def prepare_vasp_force_label(state_path: Path, destination: Path) -> dict[str, Any]:
    state = load_state(state_path)
    policy = load_policy(Path(state["policy_path"]))
    round_record = current_round(state)
    if round_record["status"] != "awaiting_vasp_force_label_preparation":
        raise ValueError("current round is not ready for VASP label preparation")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"VASP label destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    candidate = Path(round_record["candidate"]["structure_path"])
    if sha256_file(candidate) != round_record["candidate"]["structure_sha256"]:
        raise ValueError("candidate structure hash changed before VASP labeling")
    poscar = destination / "POSCAR"
    shutil.copy2(candidate, poscar)
    label_policy = policy["vasp_force_label"]
    profile_path = Path(label_policy["input_profile"])
    if not profile_path.is_absolute():
        profile_path = ROOT / profile_path
    inputs = build_fe110_active_learning_force_label(destination, profile_path=profile_path)
    if inputs["stage"] != label_policy["input_stage"]:
        raise ValueError("active-learning VASP input stage does not match the production profile")
    request = {
        "schema_version": 1,
        "document_kind": "vasp_ts_force_label_request",
        "reaction_id": state["reaction_id"],
        "round_index": round_record["round_index"],
        "candidate_structure_sha256": sha256_file(poscar),
        "candidate_result_class": PREDICTED_CLASS,
        "requested_backend": label_policy["backend"],
        "scheduler": label_policy["scheduler"],
        "input_profile": {
            "path": inputs["profile_path"],
            "sha256": inputs["profile_sha256"],
            "stage": inputs["stage"],
            "base_profile": inputs["base_profile"],
            "compatibility_incar_source": inputs["compatibility_incar_source"],
            "compatibility_incar": inputs["compatibility_incar"],
            "final_energy_convention": inputs["final_energy_convention"],
        },
        "result_class_after_acceptance": VASP_LABEL_CLASS,
        "reportable_final_energy": False,
        "required_before_execution": ["structure_gate_pass", "approved_POTCAR", "vasp_preflight_pass"],
    }
    request_path = write_json(destination / "label_request.json", request)
    round_record["vasp_force_label"] = {
        "directory": str(destination.resolve()),
        "request_sha256": sha256_file(request_path),
        "status": "prepared_not_submitted",
        "reportable_final": False,
    }
    round_record["status"] = "awaiting_vasp_force_label_execution"
    state["status"] = round_record["status"]
    state["next_action"] = "copy_approved_POTCAR_run_preflight_then_submit_on_sunboquan_codex_with_user_authority"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return request
