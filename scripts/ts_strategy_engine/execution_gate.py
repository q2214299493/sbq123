from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_json

from .execution_decision import ACTIONS, GATE_NAME
from .execution_path_rules import INITIAL_SUBMISSIONS, blocking_decision, progress_decision
from .execution_submission_rules import (
    connectivity_submission_decision,
    user_requested_stop,
    vfa_submission_decision,
)

__all__ = [
    "ACTIONS",
    "GATE_NAME",
    "INITIAL_SUBMISSIONS",
    "decide_execution",
    "require_action",
    "validate_decision",
]


def decide_execution(
    geometry: dict[str, Any],
    analysis: dict[str, Any],
    thresholds: dict[str, Any],
    *,
    climb: bool,
    path_reviewed: bool,
    path_quality: dict[str, Any] | None = None,
    preflight: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    scheduler: dict[str, Any] | None = None,
    authorization: dict[str, Any] | None = None,
    source_bindings: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    quality = path_quality or {}
    preflight = preflight or {}
    validation = validation or {}
    evidence = {
        "geometry": geometry,
        "analysis": analysis,
        "thresholds": thresholds,
        "path_quality": quality,
        "preflight": preflight,
        "validation": validation,
        "scheduler": scheduler or {},
        "authorization": authorization or {},
        "source_bindings": source_bindings or {},
        "climb": climb,
        "path_reviewed": path_reviewed,
    }
    requested_stop = user_requested_stop(evidence)
    if requested_stop:
        return requested_stop
    vfa = vfa_submission_decision(evidence)
    if vfa:
        return vfa
    connectivity = connectivity_submission_decision(evidence)
    if connectivity:
        return connectivity
    blocked = blocking_decision(geometry, analysis, quality, evidence)
    if blocked:
        return blocked
    return progress_decision(
        analysis,
        quality,
        preflight,
        validation,
        evidence,
        climb,
        path_reviewed,
    )


def require_action(
    decision_path: Path,
    action: str,
    current_state_sha256: str,
) -> dict[str, Any]:
    decision = load_json_object(decision_path)
    validate_decision(decision)
    if decision.get("state_sha256") != current_state_sha256:
        raise ValueError("execution decision is stale for the current calculation state")
    if action not in ACTIONS:
        raise ValueError(f"unknown NEB action: {action}")
    if action not in decision.get("ALLOWED_ACTIONS", []):
        raise PermissionError(f"{action} is not authorized by {decision.get('DECISION')}")
    return decision


def validate_decision(decision: dict[str, Any]) -> None:
    required = {
        "DECISION",
        "REASON_CODES",
        "EVIDENCE",
        "CRITICAL_IMAGES",
        "ALLOWED_ACTIONS",
        "FORBIDDEN_ACTIONS",
        "NEXT_REQUIRED_CHECK",
        "SUBMISSION_ALLOWED",
        "CI_NEB_ALLOWED",
        "DIMER_ALLOWED",
        "VFA_ALLOWED",
        "TS_CLAIM_ALLOWED",
    }
    if (
        decision.get("schema_version") != 2
        or decision.get("gate") != GATE_NAME
        or not required.issubset(decision)
    ):
        raise ValueError(
            "execution decision is not a complete authoritative NEB gate decision"
        )
    evidence = decision["EVIDENCE"]
    if not isinstance(evidence, dict) or "thresholds" not in evidence:
        raise ValueError("execution decision does not bind its thresholds")
    if decision.get("state_sha256") != sha256_json(evidence):
        raise ValueError("execution decision evidence hash mismatch")
    expected = decide_execution(
        evidence.get("geometry", {}),
        evidence.get("analysis", {}),
        evidence["thresholds"],
        climb=bool(evidence.get("climb")),
        path_reviewed=bool(evidence.get("path_reviewed")),
        path_quality=evidence.get("path_quality"),
        preflight=evidence.get("preflight"),
        validation=evidence.get("validation"),
        scheduler=evidence.get("scheduler"),
        authorization=evidence.get("authorization"),
        source_bindings=evidence.get("source_bindings"),
    )
    authority_fields = required - {"EVIDENCE"}
    if any(
        decision.get(field) != expected.get(field)
        for field in authority_fields
    ):
        raise ValueError(
            "execution decision authority fields do not match its evidence"
        )
