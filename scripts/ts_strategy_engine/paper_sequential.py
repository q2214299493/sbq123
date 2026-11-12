"""Pure, review-only planning for the paper's single-label sequential protocol.

No function submits work, reads calculation files, validates scheduler terminal
states, or accepts a TS. Callers must use the owning scientific validators and
the exact-input execution gate before recording execution or a completed label.
Raw label bytes are hashed before parsing; training retains every atomic force.
"""
from __future__ import annotations

import base64
import binascii
import copy
import json
import math
from pathlib import PurePosixPath
from typing import Any

from scripts.artifact_io import require_sha256, sha256_bytes, sha256_json
from scripts.scientific_validation import finite_array, integer_number, validate_finite_tree


PAPER_SOURCE = "https://arxiv.org/abs/2603.24482"
PAPER_DFT_CEILING = 250
FORCE_TARGET_EV_PER_A = 0.05
_RESTRICTIONS = {
    "submission_allowed": False,
    "automatic_submission": False,
    "scientifically_validated_ts": False,
    "reportable_barrier": False,
    "production_checkpoint_promotion": False,
}


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _checkpoint(path: str, digest: str) -> dict[str, str]:
    path = _text(path, "checkpoint path")
    if not PurePosixPath(path).is_absolute():
        raise ValueError("checkpoint path must be absolute on the execution host")
    return {"path": path, "sha256": require_sha256(digest, label="checkpoint")}


def _digest_list(values: list[str] | tuple[str, ...], label: str) -> list[str]:
    result = [require_sha256(value, label=label) for value in values]
    if len(set(result)) != len(result):
        raise ValueError(f"{label} contains duplicates")
    return result


def create_protocol(
    *,
    initial_checkpoint_path: str,
    initial_checkpoint_sha256: str,
    contract_sha256: str,
    compatibility_sha256: str,
    atom_count: int,
    movable_atom_indices: list[int],
    formed_bonds_1based: list[list[int]],
    broken_bonds_1based: list[list[int]],
    maximum_dft_evaluations: int,
    model_adaptation: str,
    dft_adaptation: str,
    model_recipe_adaptation: dict[str, Any] | None = None,
    held_out_structure_sha256: tuple[str, ...] = (),
    held_out_geometry_sha256: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Describe the paper protocol and explicit model/DFT substitutions.

    ``model_recipe_adaptation`` records the existing model's ancillary recipe;
    it does not override the fixed paper training fields or authorize training.
    Cosine eta_min and optimizer details are deliberately not invented here.
    """
    count = integer_number(atom_count, "atom count", positive=True)
    movable = [integer_number(index, "movable index", nonnegative=True) for index in movable_atom_indices]
    if not movable or len(set(movable)) != len(movable) or max(movable) >= count:
        raise ValueError("movable atom indices must be unique, non-empty, and in range")
    maximum = integer_number(maximum_dft_evaluations, "DFT budget", positive=True)
    if maximum > PAPER_DFT_CEILING:
        raise ValueError("DFT budget exceeds the paper's 250-evaluation ceiling")
    bonds: dict[str, list[list[int]]] = {}
    for name, pairs in (("formed", formed_bonds_1based), ("broken", broken_bonds_1based)):
        checked = []
        for pair in pairs:
            if len(pair) != 2:
                raise ValueError("each bond must contain two one-based atom indices")
            a, b = [integer_number(index, "bond index", positive=True) for index in pair]
            if a == b or max(a, b) > count:
                raise ValueError("bond indices must be distinct and in range")
            checked.append(sorted((a, b)))
        if len({tuple(pair) for pair in checked}) != len(checked):
            raise ValueError("bond changes contain duplicates")
        bonds[name] = checked
    if not bonds["formed"] and not bonds["broken"]:
        raise ValueError("BA-Sella requires an explicit intended bond change")
    if set(map(tuple, bonds["formed"])) & set(map(tuple, bonds["broken"])):
        raise ValueError("a bond cannot be both formed and broken")
    recipe = copy.deepcopy(model_recipe_adaptation or {})
    validate_finite_tree(recipe, "model recipe adaptation")
    protocol = {
        "document_kind": "paper_sequential_protocol",
        "paper_source": PAPER_SOURCE,
        "initial_checkpoint": _checkpoint(initial_checkpoint_path, initial_checkpoint_sha256),
        "contract_sha256": require_sha256(contract_sha256, label="reaction contract"),
        "compatibility_sha256": require_sha256(compatibility_sha256, label="DFT compatibility"),
        "atom_count": count,
        "movable_atom_indices_zero_based": sorted(movable),
        "bond_changes_1based": bonds,
        "maximum_dft_evaluations": maximum,
        "held_out_structure_sha256": _digest_list(held_out_structure_sha256, "held-out structure"),
        "held_out_geometry_sha256": _digest_list(held_out_geometry_sha256, "held-out geometry"),
        "adaptations": {
            "model": _text(model_adaptation, "model adaptation"),
            "dft": _text(dft_adaptation, "DFT adaptation"),
            "model_recipe": recipe,
            "unmodified_paper_reproduction": False,
        },
        "idpp": {"total_images": 10, "internal_images": 8, "optimizer": "LBFGS", "fmax_eV_per_A": 0.01,
                 "maximum_steps": 1000, "candidate_selection": "highest_ML_energy_internal_image"},
        "ba_sella": {"eta": 0.01, "gamma": 0.05, "delta0": 0.05, "nsteps_per_diag": 1,
                     "dot_prod_thr": 0.50, "fmax_eV_per_A": 0.01, "minimum_steps": 10, "maximum_steps": 1000},
        "training": {"epochs": 100, "initial_learning_rate": 1e-4, "scheduler": "cosine",
                     "cosine_eta_min": None, "target": "forces_only", "energy_loss_coefficient": 0.0,
                     "train_on_all": False, "train_finetuned": False, "replay": False,
                     "validation_epoch_selection": False, "training_force_mask": "movable_atoms_model_adaptation"},
        "stopping": {"DFT_movable_atom_fmax_eV_per_A_strictly_less_than": FORCE_TARGET_EV_PER_A,
                     "force_metric": "raw_DFT_force_vector_norm_not_ML_DFT_error",
                     "passed_result_class": "force_converged_candidate_only"},
        "restrictions": copy.deepcopy(_RESTRICTIONS),
    }
    return protocol


def _seal(state: dict[str, Any]) -> dict[str, Any]:
    state.pop("state_sha256", None)
    state["state_sha256"] = sha256_json(state)
    return state


def _validate_protocol(protocol: dict[str, Any]) -> None:
    try:
        expected = create_protocol(
            initial_checkpoint_path=protocol["initial_checkpoint"]["path"],
            initial_checkpoint_sha256=protocol["initial_checkpoint"]["sha256"],
            contract_sha256=protocol["contract_sha256"], compatibility_sha256=protocol["compatibility_sha256"],
            atom_count=protocol["atom_count"], movable_atom_indices=protocol["movable_atom_indices_zero_based"],
            formed_bonds_1based=protocol["bond_changes_1based"]["formed"],
            broken_bonds_1based=protocol["bond_changes_1based"]["broken"],
            maximum_dft_evaluations=protocol["maximum_dft_evaluations"],
            model_adaptation=protocol["adaptations"]["model"], dft_adaptation=protocol["adaptations"]["dft"],
            model_recipe_adaptation=protocol["adaptations"]["model_recipe"],
            held_out_structure_sha256=protocol["held_out_structure_sha256"],
            held_out_geometry_sha256=protocol["held_out_geometry_sha256"],
        )
    except (KeyError, TypeError) as error:
        raise ValueError("incomplete paper sequential protocol") from error
    if sha256_json(protocol) != sha256_json(expected):
        raise ValueError("paper protocol fields changed or contain unrecognized settings")


def _dft_request(
    protocol: dict[str, Any], protocol_sha256: str, index: int, structure: str, checkpoint: str,
) -> dict[str, Any]:
    return {
        "document_kind": "paper_sequential_DFT_request", "protocol_sha256": protocol_sha256,
        "evaluation_index": index, "candidate_structure_sha256": require_sha256(structure, label="candidate structure"),
        "search_checkpoint_sha256": require_sha256(checkpoint, label="search checkpoint"),
        "contract_sha256": protocol["contract_sha256"], "compatibility_sha256": protocol["compatibility_sha256"],
        "calculation": "exact_structure_static_single_point", "requires_exact_structure_hash_gate": True,
        "requires_authoritative_execution_gate": True, "restrictions": copy.deepcopy(_RESTRICTIONS),
    }


def _training_document(
    protocol: dict[str, Any], protocol_sha256: str, index: int, accepted: dict[str, Any],
) -> dict[str, Any]:
    return {
        "document_kind": "paper_sequential_training_request", "protocol_sha256": protocol_sha256,
        "evaluation_index": index, "base_checkpoint": copy.deepcopy(protocol["initial_checkpoint"]),
        "reset_model_weights": True, "reset_optimizer_state": True, "reset_scheduler_state": True,
        "reset_amp_state": True, "reset_ema_state": True,
        "training_samples": [copy.deepcopy(accepted)], "training": copy.deepcopy(protocol["training"]),
        "movable_atom_indices_zero_based": copy.deepcopy(protocol["movable_atom_indices_zero_based"]),
        "adaptations": copy.deepcopy(protocol["adaptations"]), "checkpoint_selection": "final_epoch_only",
        "requires_checkpoint_hash_verification": True, "requires_separate_training_authorization": True,
        "restrictions": copy.deepcopy(_RESTRICTIONS),
    }


def _validate_evaluation_request(
    row: dict[str, Any], protocol: dict[str, Any], protocol_sha256: str, index: int, search: dict[str, str],
) -> None:
    request = row.get("request")
    if not isinstance(request, dict):
        raise ValueError("evaluation lacks its exact-input request")
    expected = _dft_request(protocol, protocol_sha256, index, request.get("candidate_structure_sha256"), search["sha256"])
    if request != expected or row.get("request_sha256") != sha256_json(expected):
        raise ValueError("evaluation request hash, protocol, index, or checkpoint chain mismatch")
    if request["candidate_structure_sha256"] in protocol["held_out_structure_sha256"]:
        raise ValueError("held-out structure cannot enter sequential training")


def _validate_execution_receipt(execution: dict[str, Any], jobs: set[str]) -> None:
    if not isinstance(execution, dict) or set(execution) != {"job_id", "bundle_sha256", "gate_sha256"}:
        raise ValueError("incomplete recorded execution receipt")
    job = _text(execution["job_id"], "recorded job ID")
    if job in jobs:
        raise ValueError("DFT job receipt was already recorded")
    jobs.add(job)
    require_sha256(execution["bundle_sha256"], label="recorded DFT bundle")
    require_sha256(execution["gate_sha256"], label="recorded authoritative gate")


def _recovery_document(raw: bytes, digest: str, name: str) -> tuple[dict[str, str], dict[str, Any]]:
    digest = require_sha256(digest, label=name)
    if not isinstance(raw, bytes) or sha256_bytes(raw) != digest:
        raise ValueError(f"{name} original bytes hash mismatch")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    validate_finite_tree(value, name)
    return {"artifact_sha256": digest, "raw_base64": base64.b64encode(raw).decode("ascii")}, value


def _read_recovery_document(reference: dict[str, str], name: str) -> dict[str, Any]:
    if not isinstance(reference, dict) or set(reference) != {"artifact_sha256", "raw_base64"}:
        raise ValueError(f"incomplete {name} binding")
    try:
        raw = base64.b64decode(reference["raw_base64"], validate=True)
    except (binascii.Error, TypeError, ValueError) as error:
        raise ValueError(f"invalid {name} original bytes") from error
    return _recovery_document(raw, reference["artifact_sha256"], name)[1]


def _validate_prelaunch_recovery(state: dict[str, Any], row: dict[str, Any], index: int) -> dict[str, Any]:
    event = row.get("prelaunch_recovery")
    if index != 1 or not isinstance(event, dict) or set(event) != {
        "failed_state", "failure_evidence", "reviewed_authorization",
    }:
        raise ValueError("only one first-evaluation prelaunch recovery is supported")
    failed = _read_recovery_document(event["failed_state"], "failed state")
    rows = failed.get("evaluations")
    if not isinstance(rows, list) or len(rows) != 1 or any(
        not isinstance(item, dict) or "prelaunch_recovery" in item or "execution_history" in item for item in rows
    ):
        raise ValueError("a recovered execution cannot be recovered a second time")
    validate_state(failed)
    if (failed["status"] != "failed_needs_review_no_automatic_retry" or failed.get("failure_stage") != "mpi_prelaunch"
            or failed["executed_dft_jobs"] != 1 or failed["completed_label_count"] != 0
            or failed["protocol_sha256"] != state["protocol_sha256"]):
        raise ValueError("recovery requires the original typed prelaunch failure with zero labels")
    previous = rows[0]
    if row["request"] != previous["request"] or row["request_sha256"] != previous["request_sha256"]:
        raise ValueError("prelaunch recovery changed the original evaluation or candidate")
    if previous.get("execution") is None or previous.get("accepted_label") is not None or previous.get("training_result") is not None:
        raise ValueError("prelaunch recovery cannot follow a label or training")
    evidence = _read_recovery_document(event["failure_evidence"], "prelaunch failure evidence")
    authorization = _read_recovery_document(event["reviewed_authorization"], "reviewed recovery authorization")
    common = {"protocol_sha256": state["protocol_sha256"], "evaluation_index": index,
              "candidate_structure_sha256": row["request"]["candidate_structure_sha256"],
              "search_checkpoint_sha256": row["request"]["search_checkpoint_sha256"],
              "failed_execution": previous["execution"], "failure_stage": "mpi_prelaunch",
              "failed_state_artifact_sha256": event["failed_state"]["artifact_sha256"]}
    if any(evidence.get(key) != value or authorization.get(key) != value for key, value in common.items()):
        raise ValueError("prelaunch recovery documents do not bind the same failed execution and candidate")
    if (evidence.get("document_kind") != "paper_prelaunch_failure_evidence"
            or evidence.get("vasp_started") is not False or evidence.get("dft_label_created") is not False):
        raise ValueError("recovery evidence must confirm failure before VASP with no DFT label")
    for key in ("scheduler_evidence_sha256", "launcher_log_sha256"):
        require_sha256(evidence.get(key), label=key)
    if (authorization.get("document_kind") != "paper_prelaunch_recovery_authorization"
            or authorization.get("decision") != "approved_one_prelaunch_recovery"
            or authorization.get("automatic_retry") is not False
            or type(authorization.get("maximum_recoveries")) is not int or authorization["maximum_recoveries"] != 1
            or authorization.get("failure_evidence_artifact_sha256") != event["failure_evidence"]["artifact_sha256"]):
        raise ValueError("one explicit reviewed prelaunch recovery authorization is required")
    _text(authorization.get("reviewer"), "recovery reviewer")
    _text(authorization.get("reviewed_at"), "recovery review time")
    for key in ("recovery_bundle_sha256", "recovery_gate_sha256"):
        require_sha256(authorization.get(key), label=key)
    if not isinstance(row.get("execution_history"), list) or row["execution_history"][:1] != [previous["execution"]]:
        raise ValueError("the previous actual submission must remain in execution history")
    return authorization


def _execution_count(state: dict[str, Any], row: dict[str, Any], index: int, jobs: set[str]) -> int:
    if "prelaunch_recovery" not in row and "execution_history" not in row:
        if row.get("execution") is None:
            return 0
        _validate_execution_receipt(row["execution"], jobs)
        return 1
    authorization = _validate_prelaunch_recovery(state, row, index)
    history = row["execution_history"]
    expected_count = 1 if row.get("execution") is None else 2
    if len(history) != expected_count or (expected_count == 2 and row["execution"] != history[-1]):
        raise ValueError("prelaunch recovery history must append one actual submission only")
    for execution in history:
        _validate_execution_receipt(execution, jobs)
    if expected_count == 2 and any(history[-1][field] != authorization[key] for field, key in (
        ("bundle_sha256", "recovery_bundle_sha256"), ("gate_sha256", "recovery_gate_sha256"),
    )):
        raise ValueError("recovery submission differs from its reviewed bundle or gate")
    return len(history)


def _validate_accepted_record(protocol: dict[str, Any], row: dict[str, Any]) -> tuple[dict[str, Any], float]:
    accepted = row.get("accepted_label")
    if not isinstance(accepted, dict):
        raise ValueError("completed evaluation lacks its bound accepted label")
    try:
        raw = base64.b64decode(accepted["raw_label_base64"], validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error) as error:
        raise ValueError("accepted label lacks its original source bytes") from error
    if row.get("label_sha256") != accepted.get("artifact_sha256"):
        raise ValueError("evaluation and accepted label SHA mismatch")
    label, forces = _validated_label(protocol, row, raw, accepted["artifact_sha256"])
    if sha256_json(accepted.get("label")) != sha256_json(label):
        raise ValueError("stored accepted label does not match its original source bytes")
    stored = finite_array(accepted.get("raw_forces_eV_per_A"), "stored raw DFT forces", shape=(protocol["atom_count"], 3))
    if stored != forces:
        raise ValueError("stored raw DFT forces do not match the accepted label")
    maximum = max(math.hypot(*forces[index]) for index in protocol["movable_atom_indices_zero_based"])
    return accepted, maximum


def _validate_training_result(
    row: dict[str, Any], protocol: dict[str, Any], protocol_sha256: str, index: int, search: dict[str, str],
) -> dict[str, str]:
    result = row["training_result"]
    if not isinstance(result, dict) or set(result) != {"checkpoint", "training_request_sha256", "base_checkpoint_sha256"}:
        raise ValueError("incomplete recorded training result")
    expected = _training_document(protocol, protocol_sha256, index, row["accepted_label"])
    if result["training_request_sha256"] != sha256_json(expected):
        raise ValueError("recorded training result request hash mismatch")
    base = protocol["initial_checkpoint"]["sha256"]
    if result["base_checkpoint_sha256"] != base:
        raise ValueError("recorded training did not reset to the frozen initial checkpoint")
    checkpoint = result.get("checkpoint")
    if not isinstance(checkpoint, dict) or set(checkpoint) != {"path", "sha256"}:
        raise ValueError("recorded training result lacks a checkpoint identity")
    checked = _checkpoint(checkpoint["path"], checkpoint["sha256"])
    if checked != checkpoint or checkpoint["sha256"] in {base, search["sha256"]}:
        raise ValueError("recorded training must return a new checkpoint candidate")
    return checked


def _evaluation_chain(state: dict[str, Any]) -> dict[str, Any]:
    protocol, rows = state["protocol"], state["evaluations"]
    search = protocol["initial_checkpoint"]
    latest, maximum = None, None
    phase, executed, completed = "awaiting_candidate", 0, 0
    jobs: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if phase != "awaiting_candidate" or not isinstance(row, dict):
            raise ValueError("next evaluation precedes completion of the previous round")
        _validate_evaluation_request(row, protocol, state["protocol_sha256"], index, search)
        phase = "awaiting_execution_receipt"
        executed += _execution_count(state, row, index, jobs)
        if row.get("execution") is None:
            if any(row.get(key) is not None for key in ("accepted_label", "label_sha256", "training_result")):
                raise ValueError("an unexecuted evaluation cannot contain a label or training result")
            continue
        phase = "awaiting_accepted_label"
        if row.get("label_sha256") is None:
            if any(row.get(key) is not None for key in ("accepted_label", "training_result")):
                raise ValueError("training or accepted data precedes its completed label")
            continue
        latest, maximum = _validate_accepted_record(protocol, row)
        completed += 1
        phase = _label_phase(maximum, index, protocol["maximum_dft_evaluations"])
        if row.get("training_result") is not None:
            if phase != "awaiting_training_request":
                raise ValueError("training follows convergence or budget exhaustion")
            search = _validate_training_result(row, protocol, state["protocol_sha256"], index, search)
            phase = "awaiting_candidate"
    return {"phase": phase, "search_checkpoint": search, "latest_label": latest, "maximum": maximum,
            "executed": executed, "completed": completed}


def _label_phase(maximum: float, used: int, budget: int) -> str:
    if maximum < FORCE_TARGET_EV_PER_A:
        return "force_converged_candidate_only"
    if used >= budget:
        return "budget_exhausted_not_converged"
    return "awaiting_training_request"


def _validate_failure_stage(state: dict[str, Any], chain: dict[str, Any]) -> None:
    if "failure_stage" in state and (
        state["status"] != "failed_needs_review_no_automatic_retry" or state["failure_stage"] != "mpi_prelaunch"
        or chain["phase"] != "awaiting_accepted_label" or chain["completed"] != 0
    ):
        raise ValueError("typed prelaunch failure must precede any accepted DFT label")


def validate_state(state: dict[str, Any]) -> None:
    payload = {key: value for key, value in state.items() if key != "state_sha256"}
    if state.get("state_sha256") != sha256_json(payload):
        raise ValueError("paper sequential state hash mismatch")
    if state.get("protocol_sha256") != sha256_json(state["protocol"]):
        raise ValueError("frozen protocol hash mismatch")
    _validate_protocol(state["protocol"])
    if state.get("restrictions") != _RESTRICTIONS or state["protocol"].get("restrictions") != _RESTRICTIONS:
        raise ValueError("a planning state cannot grant execution or scientific authority")
    rows = state["evaluations"]
    if not isinstance(rows, list):
        raise ValueError("evaluation history must be a list")
    for key in ("reserved_dft_slots", "executed_dft_jobs", "completed_label_count"):
        if type(state[key]) is not int or integer_number(state[key], key, nonnegative=True) != state[key]:
            raise ValueError("DFT counters must be nonnegative integers")
    if state["reserved_dft_slots"] != len(rows):
        raise ValueError("reserved DFT slot count mismatch")
    if len(rows) > state["protocol"]["maximum_dft_evaluations"]:
        raise ValueError("DFT budget exceeded")
    chain = _evaluation_chain(state)
    if (state["executed_dft_jobs"], state["completed_label_count"]) != (chain["executed"], chain["completed"]):
        raise ValueError("DFT counters do not match the validated evaluation chain")
    if (state["search_checkpoint"] != chain["search_checkpoint"]
            or sha256_json(state["latest_label"]) != sha256_json(chain["latest_label"])):
        raise ValueError("search checkpoint or latest label is not the end of the validated chain")
    failed = state["status"] == "failed_needs_review_no_automatic_retry"
    _validate_failure_stage(state, chain)
    if failed:
        _text(state.get("failure_reason"), "failure reason")
    elif state["status"] != chain["phase"]:
        raise ValueError("state status does not match its evaluation phase")
    converged = not failed and chain["phase"] == "force_converged_candidate_only"
    if state["force_converged_candidate"] is not converged:
        raise ValueError("candidate convergence flag does not match the evaluated raw DFT forces")
    if sha256_json(state.get("DFT_movable_fmax_eV_per_A")) != sha256_json(chain["maximum"]):
        raise ValueError("stored DFT residual does not match the latest accepted label")


def initialize_state(protocol: dict[str, Any]) -> dict[str, Any]:
    """Freeze a reviewed protocol; this does not verify remote checkpoint bytes."""
    if protocol.get("document_kind") != "paper_sequential_protocol" or protocol.get("restrictions") != _RESTRICTIONS:
        raise ValueError("invalid paper sequential protocol")
    _validate_protocol(protocol)
    frozen = copy.deepcopy(protocol)
    return _seal({
        "document_kind": "paper_sequential_state", "protocol": frozen, "protocol_sha256": sha256_json(frozen),
        "status": "awaiting_candidate", "reserved_dft_slots": 0, "executed_dft_jobs": 0,
        "completed_label_count": 0, "evaluations": [], "latest_label": None,
        "search_checkpoint": copy.deepcopy(frozen["initial_checkpoint"]),
        "force_converged_candidate": False, "restrictions": copy.deepcopy(_RESTRICTIONS),
    })


def prepare_dft_evaluation(
    state: dict[str, Any], *, candidate_structure_sha256: str, search_checkpoint_sha256: str,
) -> dict[str, Any]:
    """Reserve one reviewable single-point slot, without claiming execution."""
    validate_state(state)
    if state["status"] != "awaiting_candidate":
        raise ValueError("a candidate cannot be prepared in the current state")
    protocol = state["protocol"]
    if state["reserved_dft_slots"] >= protocol["maximum_dft_evaluations"]:
        raise ValueError("DFT budget exhausted; no additional evaluation is permitted")
    structure = require_sha256(candidate_structure_sha256, label="candidate structure")
    checkpoint = require_sha256(search_checkpoint_sha256, label="search checkpoint")
    if checkpoint != state["search_checkpoint"]["sha256"]:
        raise ValueError("candidate search checkpoint mismatch")
    if structure in protocol["held_out_structure_sha256"]:
        raise ValueError("held-out structure cannot enter sequential training")
    updated = copy.deepcopy(state)
    request = _dft_request(protocol, state["protocol_sha256"], len(state["evaluations"]) + 1, structure, checkpoint)
    updated["evaluations"].append({"request": request, "request_sha256": sha256_json(request), "execution": None})
    updated["reserved_dft_slots"] += 1
    updated["status"] = "awaiting_execution_receipt"
    return _seal(updated)


def record_execution(
    state: dict[str, Any], *, job_id: str, bundle_sha256: str, gate_sha256: str,
) -> dict[str, Any]:
    """Record a caller-verified actual job receipt; never construct a permit."""
    validate_state(state)
    if state["status"] != "awaiting_execution_receipt":
        raise ValueError("no prepared DFT evaluation is awaiting execution")
    job = _text(job_id, "job ID")
    if any((row.get("execution") or {}).get("job_id") == job for row in state["evaluations"]):
        raise ValueError("DFT job receipt was already recorded")
    updated = copy.deepcopy(state)
    updated["evaluations"][-1]["execution"] = {
        "job_id": job, "bundle_sha256": require_sha256(bundle_sha256, label="DFT input bundle"),
        "gate_sha256": require_sha256(gate_sha256, label="authoritative gate"),
    }
    if "execution_history" in updated["evaluations"][-1]:
        updated["evaluations"][-1]["execution_history"].append(copy.deepcopy(updated["evaluations"][-1]["execution"]))
    updated["executed_dft_jobs"] += 1
    updated["status"] = "awaiting_accepted_label"
    updated = _seal(updated)
    validate_state(updated)
    return updated


def _validate_geometry_exclusion(protocol: dict[str, Any], label: dict[str, Any]) -> None:
    geometry = label.get("geometry_sha256")
    if protocol["held_out_geometry_sha256"] and geometry is None:
        raise ValueError("geometry hash is required to exclude held-out contamination")
    if geometry is not None:
        geometry = require_sha256(geometry, label="label geometry")
        if geometry in protocol["held_out_geometry_sha256"]:
            raise ValueError("held-out geometry cannot enter sequential training")


def _validated_label(
    protocol: dict[str, Any], current: dict[str, Any], raw_label: bytes, expected_sha256: str,
) -> tuple[dict[str, Any], list[list[float]]]:
    if not isinstance(raw_label, bytes):
        raise ValueError("accepted label must retain its original bytes")
    if sha256_bytes(raw_label) != require_sha256(expected_sha256, label="accepted label artifact"):
        raise ValueError("raw label artifact hash mismatch")
    label = json.loads(raw_label)
    if not isinstance(label, dict):
        raise ValueError("accepted label must be an object")
    if (label.get("document_kind") != "vasp_ts_force_label"
            or label.get("result_class") != "vasp_completed_electronic_converged_force_label_only"
            or label.get("reportable_final_energy") is not False):
        raise ValueError("sequential training requires a non-reportable, accepted VASP force label")
    for key in ("normal_completion", "electronically_converged", "eligible_for_force_only_training"):
        if label.get(key) is not True:
            raise ValueError(f"force label failed {key}")
    for key in ("contract_sha256", "compatibility_sha256"):
        if label.get(key) != protocol[key]:
            raise ValueError(f"force label {key} mismatch")
    if label.get("paper_sequential_request_sha256") != current["request_sha256"]:
        raise ValueError("force label exact-input request hash mismatch")
    if label.get("structure", {}).get("sha256") != current["request"]["candidate_structure_sha256"]:
        raise ValueError("force label structure hash mismatch")
    if label.get("scheduler_evidence", {}).get("job_id") != current["execution"]["job_id"]:
        raise ValueError("force label execution identity mismatch")
    _validate_geometry_exclusion(protocol, label)
    fixed = sorted(set(range(protocol["atom_count"])) - set(protocol["movable_atom_indices_zero_based"]))
    if label.get("fixed_atom_indices_zero_based") != fixed:
        raise ValueError("force label fixed-atom mask mismatch")
    forces = finite_array(label.get("forces_eV_per_A"), "raw DFT forces", shape=(protocol["atom_count"], 3))
    return label, forces


def accept_force_label(state: dict[str, Any], raw_label: bytes, *, expected_sha256: str) -> dict[str, Any]:
    """Consume an owning-module-accepted label; no Slurm/LSF state is invented."""
    validate_state(state)
    if state["status"] != "awaiting_accepted_label":
        raise ValueError("no executed DFT evaluation is awaiting a label")
    protocol = state["protocol"]
    current = state["evaluations"][-1]
    label, forces = _validated_label(protocol, current, raw_label, expected_sha256)
    maximum = max(math.hypot(*forces[index]) for index in protocol["movable_atom_indices_zero_based"])
    updated = copy.deepcopy(state)
    accepted = {
        "artifact_sha256": require_sha256(expected_sha256, label="accepted label artifact"), "label": label,
        "raw_label_base64": base64.b64encode(raw_label).decode("ascii"), "raw_forces_eV_per_A": forces,
    }
    updated["latest_label"] = accepted
    updated["evaluations"][-1]["accepted_label"] = copy.deepcopy(accepted)
    updated["evaluations"][-1]["label_sha256"] = accepted["artifact_sha256"]
    updated["completed_label_count"] += 1
    updated["DFT_movable_fmax_eV_per_A"] = maximum
    updated["force_converged_candidate"] = maximum < FORCE_TARGET_EV_PER_A
    updated["status"] = _label_phase(maximum, updated["reserved_dft_slots"], protocol["maximum_dft_evaluations"])
    return _seal(updated)


def training_request(state: dict[str, Any]) -> dict[str, Any]:
    """Plan one fresh 100-epoch fit using only the latest accepted structure."""
    validate_state(state)
    if state["status"] != "awaiting_training_request":
        raise ValueError("no training is required or permitted in the current state")
    return _training_document(state["protocol"], state["protocol_sha256"], state["reserved_dft_slots"], state["latest_label"])


def register_training_result(
    state: dict[str, Any], *, checkpoint_path: str, checkpoint_sha256: str,
    training_request_sha256: str, base_checkpoint_sha256: str,
) -> dict[str, Any]:
    """Record a separately validated candidate checkpoint, without promotion."""
    request = training_request(state)
    if training_request_sha256 != sha256_json(request):
        raise ValueError("training result request hash mismatch")
    if base_checkpoint_sha256 != state["protocol"]["initial_checkpoint"]["sha256"]:
        raise ValueError("training did not reset to the frozen initial checkpoint")
    checkpoint = _checkpoint(checkpoint_path, checkpoint_sha256)
    if checkpoint["sha256"] in {base_checkpoint_sha256, state["search_checkpoint"]["sha256"]}:
        raise ValueError("training must return a new checkpoint candidate")
    updated = copy.deepcopy(state)
    updated["search_checkpoint"] = checkpoint
    updated["evaluations"][-1]["training_result"] = {
        "checkpoint": copy.deepcopy(checkpoint), "training_request_sha256": training_request_sha256,
        "base_checkpoint_sha256": base_checkpoint_sha256,
    }
    updated["status"] = "awaiting_candidate"
    return _seal(updated)


def record_failure(state: dict[str, Any], reason: str, *, stage: str | None = None) -> dict[str, Any]:
    """Stop after a failed stage; preserve counters and require external review."""
    validate_state(state)
    if stage is not None and (stage != "mpi_prelaunch" or state["status"] != "awaiting_accepted_label"
                              or state["completed_label_count"] != 0):
        raise ValueError("typed prelaunch failure requires a submitted job and zero accepted labels")
    updated = copy.deepcopy(state)
    updated["status"] = "failed_needs_review_no_automatic_retry"
    updated["failure_reason"] = _text(reason, "failure reason")
    updated["force_converged_candidate"] = False
    if stage is not None:
        updated["failure_stage"] = stage
    return _seal(updated)


def recover_prelaunch_failure(
    raw_failed_state: bytes, *, expected_failed_state_sha256: str, raw_failure_evidence: bytes,
    expected_failure_evidence_sha256: str, raw_reviewed_authorization: bytes,
    expected_reviewed_authorization_sha256: str,
) -> dict[str, Any]:
    """Append one reviewed infrastructure recovery, never a general DFT retry.

    Original state/evidence/approval bytes remain embedded and hash-bound. The
    returned plan has no execution authority; a new independent gate is required.
    """
    failed_reference, failed = _recovery_document(raw_failed_state, expected_failed_state_sha256, "failed state")
    failure_reference, _ = _recovery_document(
        raw_failure_evidence, expected_failure_evidence_sha256, "prelaunch failure evidence",
    )
    review_reference, _ = _recovery_document(
        raw_reviewed_authorization, expected_reviewed_authorization_sha256, "reviewed recovery authorization",
    )
    # Reject nested recovery snapshots before invoking recursive state validation.
    rows = failed.get("evaluations")
    if not isinstance(rows, list) or len(rows) != 1 or any(
        not isinstance(row, dict) or "prelaunch_recovery" in row or "execution_history" in row for row in rows
    ):
        raise ValueError("only one original first-evaluation prelaunch recovery is permitted")
    validate_state(failed)
    updated = copy.deepcopy(failed)
    row = updated["evaluations"][-1]
    row["prelaunch_recovery"] = {"failed_state": failed_reference, "failure_evidence": failure_reference,
                                "reviewed_authorization": review_reference}
    row["execution_history"] = [copy.deepcopy(row.get("execution"))]
    row["execution"] = None
    updated["status"] = "awaiting_execution_receipt"
    updated.pop("failure_reason", None)
    updated.pop("failure_stage", None)
    updated = _seal(updated)
    validate_state(updated)
    return updated
