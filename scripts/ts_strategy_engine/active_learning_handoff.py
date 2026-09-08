from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

from scripts.aqcat25_calibration import parse_poscar_symbols
from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.aqcat25_ts_schema import load_document
from scripts.artifact_io import sha256_file
from scripts.execution_backends import load_execution_backends

from .active_learning_common import current_round, load_policy, load_state, read_json, utc_now, write_json
from .active_learning_common import _checkpoint_for_current


def _empty_destination(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)




def prepare_force_prediction_request(state_path: Path, destination: Path) -> dict[str, Any]:
    gpu_backend = load_execution_backends().gpu
    state = load_state(state_path)
    current = current_round(state)
    if current["status"] != "awaiting_ml_force_prediction_preparation":
        raise ValueError("current round is not ready for force-prediction handoff")
    policy = load_policy(Path(state["policy_path"]))
    _empty_destination(destination)
    source = Path(current["candidate"]["structure_path"])
    target = destination / "POSCAR"
    shutil.copy2(source, target)
    if sha256_file(target) != current["candidate"]["structure_sha256"]:
        raise ValueError("force-prediction structure hash mismatch")
    symbols = parse_poscar_symbols(target)
    adsorbate_indices = [index for index, symbol in enumerate(symbols, start=1) if symbol != "Fe"]
    if not adsorbate_indices:
        raise ValueError("force-prediction request has no non-Fe adsorbate atoms")
    request = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_force_prediction_request",
        "reaction_id": state["reaction_id"],
        "round_index": current["round_index"],
        "structure": {
            "path": "POSCAR",
            "sha256": sha256_file(target),
            "atom_order_sha256": atom_order_sha256(symbols),
        },
        "checkpoint": _checkpoint_for_current(state, policy),
        "indexed_bond_changes": current["candidate"]["indexed_bond_changes"],
        "adsorbate_indices_1based": adsorbate_indices,
        "result_class": "predicted_transition_state_candidate_only",
        "restrictions": {
            "backend": gpu_backend.hostname,
            "reportable_dft": False,
            "automatic_submission": False,
        },
    }
    request_path = write_json(destination / "prediction_request.json", request)
    current["force_prediction"] = {
        "status": "prepared_not_submitted",
        "request_path": str(request_path.resolve()),
        "request_sha256": sha256_file(request_path),
    }
    current["status"] = "awaiting_ml_force_prediction_on_exact_label_structure"
    state["status"] = current["status"]
    state["next_action"] = (
        f"review_then_run_hash_bound_force_prediction_on_{gpu_backend.hostname}"
    )
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return request


def _copy_ref(ref: dict[str, Any], source_root: Path, destination: Path, name: str) -> dict[str, Any]:
    source = source_root / ref["path"]
    target = destination / "structures" / f"{name}.vasp"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied = dict(ref)
    copied["path"] = target.relative_to(destination).as_posix()
    if sha256_file(target) != ref["sha256"]:
        raise ValueError(f"rerun handoff structure hash mismatch: {name}")
    return copied


def prepare_ba_sella_rerun(state_path: Path, destination: Path) -> dict[str, Any]:
    gpu_backend = load_execution_backends().gpu
    state = load_state(state_path)
    current = current_round(state)
    if current["status"] != "awaiting_ba_sella_rerun":
        raise ValueError("current round is not ready for a BA-Sella rerun handoff")
    _empty_destination(destination)
    candidate_manifest = read_json(Path(current["candidate"]["manifest_path"]))
    source_root = Path(current["candidate"]["handoff_root"])
    source_handoff_path = source_root / candidate_manifest["source_handoff"]["path"]
    source_handoff = validate_handoff(source_handoff_path, root=source_root)
    handoff = copy.deepcopy(source_handoff)
    next_index = int(current["round_index"]) + 1
    handoff["handoff_id"] = f"{source_handoff['handoff_id']}_active_learning_round_{next_index:03d}"
    checkpoint = state["latest_finetuned_checkpoint"]
    handoff["model"]["checkpoint_sha256"] = checkpoint["sha256"]
    handoff["candidate_structure"] = _copy_ref(handoff["candidate_structure"], source_root, destination, "candidate")
    transition = handoff["transition_state"]
    transition["initial_structure"] = _copy_ref(transition["initial_structure"], source_root, destination, "initial")
    transition["final_structure"] = _copy_ref(transition["final_structure"], source_root, destination, "final")
    transition["waypoint_structures"] = [
        _copy_ref(ref, source_root, destination, f"waypoint_{index:02d}")
        for index, ref in enumerate(transition["waypoint_structures"], start=1)
    ]
    handoff_path = write_json(destination / "handoff.json", handoff)
    validate_handoff(handoff_path, root=destination)
    request = {
        "schema_version": 1,
        "document_kind": "aqcat25_ba_sella_rerun_request",
        "reaction_id": state["reaction_id"],
        "round_index": next_index,
        "handoff": {"path": "handoff.json", "sha256": sha256_file(handoff_path)},
        "checkpoint": checkpoint,
        "required_return_result_class": "predicted_transition_state_candidate_only",
        "automatic_submission": False,
    }
    request_path = write_json(destination / "rerun_request.json", request)
    current["ba_sella_rerun"] = {
        "status": "prepared_not_submitted",
        "request_path": str(request_path.resolve()),
        "request_sha256": sha256_file(request_path),
        "handoff_sha256": sha256_file(handoff_path),
    }
    current["status"] = "awaiting_ba_sella_rerun_result"
    state["status"] = current["status"]
    state["next_action"] = (
        f"review_then_run_BA_Sella_on_{gpu_backend.hostname}_and_return_through_work"
    )
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return request


def register_job_evidence(state_path: Path, evidence_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    current = current_round(state)
    evidence = load_document(evidence_path, expected_kind="scheduler_job_evidence")
    stage = str(evidence.get("stage", ""))
    backends = load_execution_backends()
    expected = {
        "vasp_force_label": (backends.vasp.name, backends.vasp.server_alias),
        "force_prediction": (backends.gpu.scheduler, backends.gpu.hostname),
        "force_only_finetuning": (backends.gpu.scheduler, backends.gpu.hostname),
        "ba_sella_rerun": (backends.gpu.scheduler, backends.gpu.hostname),
    }
    if stage not in expected or (evidence.get("scheduler"), evidence.get("server_alias")) != expected[stage]:
        raise ValueError("scheduler job evidence has the wrong stage/backend")
    if not evidence.get("job_id") or not evidence.get("source_command") or not evidence.get("checked_at"):
        raise ValueError("scheduler job evidence is incomplete")
    allowed = {"SUBMITTED", "PEND", "RUN", "DONE", "EXIT", "FAILED", "COMPLETED"}
    if evidence.get("status") not in allowed:
        raise ValueError("unsupported scheduler job status")
    current.setdefault("job_evidence", {}).setdefault(stage, []).append(
        {"path": str(evidence_path.resolve()), "sha256": sha256_file(evidence_path), **evidence}
    )
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return evidence


def record_stage_failure(state_path: Path, evidence_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    current = current_round(state)
    evidence = read_json(evidence_path)
    required = ("stage", "backend", "status", "error", "retryable")
    if evidence.get("document_kind") != "active_learning_stage_failure" or any(key not in evidence for key in required):
        raise ValueError("active-learning failure evidence is incomplete")
    previous = state["status"]
    state.setdefault("failures", []).append(
        {"path": str(evidence_path.resolve()), "sha256": sha256_file(evidence_path), **evidence}
    )
    current["status"] = f"blocked_{evidence['stage']}_failed"
    state["status"] = current["status"]
    state["resume_status"] = previous if evidence["retryable"] else None
    state["next_action"] = "review_failure_then_resume" if evidence["retryable"] else "human_method_review_required"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return evidence


def resume_retryable_failure(state_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    resume_status = state.get("resume_status")
    if not resume_status or not str(state.get("status", "")).startswith("blocked_"):
        raise ValueError("workflow has no retryable recorded failure")
    current = current_round(state)
    current["status"] = resume_status
    state["status"] = resume_status
    state["resume_status"] = None
    state["next_action"] = "retry_recorded_stage_after_review"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return state
