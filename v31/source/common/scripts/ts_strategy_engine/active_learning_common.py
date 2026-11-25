from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any

import yaml

from scripts.aqcat25_handoff import validate_handoff
from scripts.aqcat25_ts_schema import KNOWN_DOCUMENT_KINDS, load_document, validate_document
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, write_json_atomic
from scripts.execution_backends import load_execution_backends, require_gpu_write_path
from scripts.vasp_result_gate import validate_lsf_done_evidence

from .contract import load_contract


STATE_NAME = "active_learning_state.json"
PREDICTED_CLASS = "predicted_transition_state_candidate_only"
VASP_LABEL_CLASS = "vasp_completed_electronic_converged_force_label_only"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return load_json_object(path)


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    if payload.get("document_kind") in KNOWN_DOCUMENT_KINDS:
        validate_document(payload)
    return write_json_atomic(path, payload)


def load_policy(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("workflow_kind") != "aqcat25_ts_sequential_active_learning":
        raise ValueError("invalid AQCat25 TS active-learning policy")
    thresholds = payload["local_force_screen"]
    numeric_thresholds = {key: value for key, value in thresholds.items() if key.endswith("_max")}
    if any(float(value) <= 0 for value in numeric_thresholds.values()):
        raise ValueError("force-agreement thresholds must be positive")
    backends = load_execution_backends()
    vasp = payload.get("vasp_force_label", {})
    if (vasp.get("backend"), vasp.get("scheduler")) != (
        backends.vasp.server_alias,
        backends.vasp.name,
    ):
        raise ValueError("active-learning policy VASP backend conflicts with execution_backends.yaml")
    fine_tuning = payload.get("fine_tuning", {})
    if (
        fine_tuning.get("backend") != "aqcat_gpu"
        or fine_tuning.get("hostname") != backends.gpu.hostname
        or require_gpu_write_path(fine_tuning.get("remote_root", ""))
        != str(fine_tuning.get("remote_root", "")).rstrip("/")
    ):
        raise ValueError("active-learning policy GPU backend conflicts with execution_backends.yaml")
    return payload


def force_metrics(
    reference: list[list[float]], predicted: list[list[float]], movable_indices: list[int]
) -> tuple[dict[str, float], list[float], list[float]]:
    if len(reference) != len(predicted) or not reference:
        raise ValueError("reference/predicted force shapes do not match")
    if not movable_indices or any(index < 0 or index >= len(reference) for index in movable_indices):
        raise ValueError("movable force indices are invalid")
    component_errors: list[float] = []
    vector_errors: list[float] = []
    for index in movable_indices:
        expected, actual = reference[index], predicted[index]
        if len(expected) != 3 or len(actual) != 3:
            raise ValueError("force vectors must have three components")
        delta = [float(actual[i]) - float(expected[i]) for i in range(3)]
        if not all(math.isfinite(value) for value in delta):
            raise ValueError("force errors contain non-finite values")
        component_errors.extend(abs(value) for value in delta)
        vector_errors.append(math.sqrt(sum(value * value for value in delta)))
    metrics = {
        "component_mae_eV_per_A": fmean(component_errors),
        "vector_rmse_eV_per_A": math.sqrt(fmean(value * value for value in vector_errors)),
        "vector_max_eV_per_A": max(vector_errors),
    }
    return metrics, component_errors, vector_errors


def candidate_record(manifest_path: Path, handoff_root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    manifest = validate_handoff(manifest_path, root=handoff_root)
    if manifest["direction"] != "gpu_to_work" or manifest["workflow_kind"] != "transition_state":
        raise ValueError("active learning requires a returned transition-state candidate")
    if manifest["result"]["result_class"] != PREDICTED_CLASS:
        raise ValueError("AQCat25 candidate must remain prediction-only")
    if manifest["result"]["predicted_energy"]["reportable_dft"]:
        raise ValueError("AQCat25 energy cannot be marked reportable DFT")
    if manifest["result"]["predicted_force"]["reportable_dft"]:
        raise ValueError("AQCat25 forces cannot be marked reportable DFT")
    transition = manifest["transition_state"]
    if transition["normalized_reaction_contract_sha256"] != contract["contract_sha256"]:
        raise ValueError("candidate reaction-contract hash mismatch")
    if transition["atom_map_sha256"] != contract["atom_map_sha256"]:
        raise ValueError("candidate atom-map hash mismatch")
    candidate = handoff_root / manifest["candidate_structure"]["path"]
    return {
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "handoff_root": str(handoff_root.resolve()),
        "structure_path": str(candidate.resolve()),
        "structure_sha256": manifest["candidate_structure"]["sha256"],
        "atom_order_sha256": manifest["candidate_structure"]["atom_order_sha256"],
        "model_identifier": manifest["producer"]["model_identifier"],
        "checkpoint_sha256": manifest["producer"]["checkpoint_sha256"],
        "result_class": PREDICTED_CLASS,
        "reportable_final": False,
        "indexed_bond_changes": transition["indexed_bond_changes"],
    }


def load_state(path: Path) -> dict[str, Any]:
    state = read_json(path)
    validate_document(state, expected_kind="aqcat25_ts_active_learning_state")
    policy_path = Path(state["policy_path"])
    if not policy_path.is_file() or sha256_file(policy_path) != state["policy_sha256"]:
        raise ValueError("active-learning policy changed after workflow initialization")
    return state


def load_bound_vasp_label(
    path: Path,
    expected_sha256: str,
    *,
    contract_sha256: str,
    compatibility_sha256: str,
) -> dict[str, Any]:
    if sha256_file(path) != expected_sha256:
        raise ValueError("VASP force-label report hash changed after ingestion")
    report = load_document(path, expected_kind="vasp_ts_force_label")
    if (
        report["contract_sha256"] != contract_sha256
        or report["compatibility_sha256"] != compatibility_sha256
    ):
        raise ValueError("VASP force-label contract or compatibility mismatch")
    for name in ("label_request", "structure", "outcar", "oszicar"):
        reference = report[name]
        artifact = Path(reference["path"])
        if not artifact.is_absolute():
            artifact = path.parent / artifact
        if not artifact.is_file() or sha256_file(artifact) != reference["sha256"]:
            raise ValueError(f"VASP force-label {name} file is missing or hash-mismatched")
    scheduler_ref = report["scheduler_evidence"]
    scheduler_path = Path(str(scheduler_ref.get("path", "")))
    if not scheduler_path.is_absolute():
        scheduler_path = path.parent / scheduler_path
    if not scheduler_path.is_file() or sha256_file(scheduler_path) != scheduler_ref.get("sha256"):
        raise ValueError("VASP force-label scheduler evidence is missing or hash-mismatched")
    scheduler = load_document(scheduler_path, expected_kind="scheduler_job_evidence")
    validate_lsf_done_evidence(scheduler)
    query = scheduler["query"]
    if (
        sha256_text(query["stdout"]) != query["stdout_sha256"]
        or str(scheduler["job_id"]) not in query["stdout"]
        or "DONE" not in query["stdout"].split()
        or (scheduler_ref.get("live_recheck") or {}).get("status") != "DONE"
    ):
        raise ValueError("VASP force-label scheduler evidence is not bound to a live-rechecked DONE job")
    return report


def current_round(state: dict[str, Any]) -> dict[str, Any]:
    rounds = state.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        raise ValueError("active-learning state has no rounds")
    return rounds[-1]


def contract_for_state(path: Path, state: dict[str, Any]) -> dict[str, Any]:
    contract = load_contract(path)
    if contract["contract_sha256"] != state["contract_sha256"]:
        raise ValueError("reaction contract changed during active learning")
    return contract


def _checkpoint_for_current(state: dict[str, Any], policy: dict[str, Any]) -> dict[str, str]:
    current = current_round(state)
    latest = state.get("latest_finetuned_checkpoint")
    if latest and latest.get("sha256") == current["candidate"]["checkpoint_sha256"]:
        return latest
    return {
        "path": policy["fine_tuning"]["initial_checkpoint_path"],
        "sha256": current["candidate"]["checkpoint_sha256"],
    }
