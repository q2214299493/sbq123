"""One raw-bound, stricter stopping revision; historical paper bytes stay frozen.

This is planning authority only. Execution still needs separate resource,
candidate, exact-input gate, native completion and scientific label checks.
"""
from __future__ import annotations

import base64
import binascii
import copy
import json
from typing import Any

from scripts.artifact_io import require_sha256, sha256_bytes, sha256_json
from scripts.scientific_validation import finite_number


def _document(raw: bytes, digest: str) -> dict[str, Any]:
    if not isinstance(raw, bytes) or sha256_bytes(raw) != require_sha256(digest, label="stopping source"):
        raise ValueError("stopping source original bytes hash mismatch")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("stopping source must be an object")
    return value


def _reference(raw: bytes, digest: str) -> dict[str, str]:
    _document(raw, digest)
    return {"artifact_sha256": digest, "raw_base64": base64.b64encode(raw).decode("ascii")}


def _read(reference: dict[str, str]) -> dict[str, Any]:
    if not isinstance(reference, dict) or set(reference) != {"artifact_sha256", "raw_base64"}:
        raise ValueError("incomplete stopping source binding")
    try:
        raw = base64.b64decode(reference["raw_base64"], validate=True)
    except (binascii.Error, TypeError, ValueError) as error:
        raise ValueError("invalid stopping source bytes") from error
    return _document(raw, reference["artifact_sha256"])


def validate_authorization(origin: dict[str, Any], authorization: dict[str, Any], origin_digest: str) -> float:
    """Check the exact user instruction and already accepted label boundary."""
    expected = {
        "schema_version": 1, "document_kind": "paper_sequential_continuation_authorization",
        "decision": "approved_until_raw_DFT_force_target", "reviewer": "user",
        "protocol_sha256": origin["protocol_sha256"], "comparison": "strictly_less_than",
        "force_metric": "raw_DFT_movable_atom_vector_norm", "training_epochs": 100,
        "reset_original_base_and_optimizer_each_round": True, "latest_label_only": True,
        "automatic_retries": 0, "separate_candidate_review_and_execution_gate_required": True,
        "no_new_round_after_threshold": True, "final_TS_or_barrier_acceptance_authorized": False,
        "first_evaluation_index": origin["reserved_dft_slots"] + 1,
        "maximum_total_dft_evaluations": origin["protocol"]["maximum_dft_evaluations"],
        "maximum_additional_dft_evaluations": origin["protocol"]["maximum_dft_evaluations"] - origin["reserved_dft_slots"],
    }
    if any(sha256_json(authorization.get(key)) != sha256_json(value) for key, value in expected.items()):
        raise ValueError("stopping revision lacks the exact continuation authorization")
    if authorization.get("origin_state", {}).get("sha256") != origin_digest:
        raise ValueError("stopping authorization refers to another origin state")
    previous = origin["protocol"]["stopping"]["DFT_movable_atom_fmax_eV_per_A_strictly_less_than"]
    if authorization.get("previous_force_target_eV_per_A") != previous:
        raise ValueError("stopping authorization changed the historical target")
    target = finite_number(authorization.get("force_target_eV_per_A"), "approved force target")
    if not 0 < target < previous:
        raise ValueError("stopping revision must strictly tighten the original target")
    try:
        raw_instruction = base64.b64decode(authorization["raw_user_instruction_base64"], validate=True)
        source = authorization["source"]
        valid = 0 < len(raw_instruction) < 10000 and sha256_bytes(raw_instruction) == source["sha256"]
    except (KeyError, TypeError, ValueError, binascii.Error) as error:
        raise ValueError("missing raw user stopping instruction") from error
    if not valid or not isinstance(source.get("path"), str) or not source["path"]:
        raise ValueError("raw user stopping instruction hash mismatch")
    return target


def validate_stopping_revision(state: dict[str, Any]) -> None:
    revision = state.get("stopping_revision")
    if revision is None:
        return
    if not isinstance(revision, dict) or set(revision) != {"origin_state", "reviewed_authorization"}:
        raise ValueError("incomplete stopping revision")
    origin = _read(revision["origin_state"])
    if "stopping_revision" in origin:
        raise ValueError("nested stopping revisions are unsupported")
    from scripts.ts_strategy_engine.paper_sequential import validate_state

    validate_state(origin)
    count = _accepted_boundary(origin)
    authorization = _read(revision["reviewed_authorization"])
    validate_authorization(origin, authorization, revision["origin_state"]["artifact_sha256"])
    if (state["protocol_sha256"] != origin["protocol_sha256"]
            or sha256_json(state["protocol"]) != sha256_json(origin["protocol"])
            or len(state["evaluations"]) < count):
        raise ValueError("stopping revision changed the frozen protocol or removed history")
    for index, old_row in enumerate(origin["evaluations"]):
        current = state["evaluations"][index]
        # Only the last accepted row may subsequently acquire its training result.
        if index == count - 1:
            current = {key: value for key, value in current.items() if key != "training_result"}
            if "training_result" in old_row:
                current["training_result"] = old_row["training_result"]
        if sha256_json(current) != sha256_json(old_row):
            raise ValueError("stopping revision rewrote its accepted evaluation history")


def _accepted_boundary(origin: dict[str, Any]) -> int:
    count = origin["reserved_dft_slots"]
    if (count <= 0 or origin["completed_label_count"] != count
            or origin["status"] not in {"awaiting_training_request", "force_converged_candidate_only"}
            or origin["evaluations"][-1].get("training_result") is not None):
        raise ValueError("stopping revision requires an accepted label before its training")
    return count


def effective_force_target(state: dict[str, Any], evaluation_index: int | None = None) -> float:
    """Return the reviewed active target; callers validate the owner state first."""
    revision = state.get("stopping_revision")
    if revision is not None:
        authorization = _read(revision["reviewed_authorization"])
        # Include the label from which the newly authorized training resumes.
        if evaluation_index is None or evaluation_index >= authorization["first_evaluation_index"] - 1:
            return authorization["force_target_eV_per_A"]
    return state["protocol"]["stopping"]["DFT_movable_atom_fmax_eV_per_A_strictly_less_than"]


def revise_stopping_target(
    raw_state: bytes, *, expected_state_sha256: str,
    raw_authorization: bytes, expected_authorization_sha256: str,
) -> dict[str, Any]:
    """Attach one explicit tightening without editing any old input or label."""
    from scripts.ts_strategy_engine import paper_sequential as paper

    origin = _document(raw_state, expected_state_sha256)
    paper.validate_state(origin)
    if "stopping_revision" in origin:
        raise ValueError("a stopping revision already exists")
    _accepted_boundary(origin)
    authorization = _document(raw_authorization, expected_authorization_sha256)
    target = validate_authorization(origin, authorization, expected_state_sha256)
    updated = copy.deepcopy(origin)
    updated["stopping_revision"] = {
        "origin_state": _reference(raw_state, expected_state_sha256),
        "reviewed_authorization": _reference(raw_authorization, expected_authorization_sha256),
    }
    maximum = updated["DFT_movable_fmax_eV_per_A"]
    updated["force_converged_candidate"] = maximum < target
    updated["status"] = paper._label_phase(maximum, updated["reserved_dft_slots"],
                                            updated["protocol"]["maximum_dft_evaluations"], target)
    updated["state_sha256"] = sha256_json({key: value for key, value in updated.items() if key != "state_sha256"})
    paper.validate_state(updated)
    return updated
