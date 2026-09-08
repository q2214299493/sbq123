from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from scripts.artifact_io import sha256_json


ACTIONS = (
    "CONTINUE_JOB",
    "STOP_JOB",
    "REBUILD_PATH",
    "SUBMIT_DIAGNOSTIC_VASP",
    "SUBMIT_VASP",
    "ENABLE_CI_NEB",
    "PREPARE_DIMER_HANDOFF",
    "START_DIMER",
    "START_VFA",
    "APPROVE_TS_CANDIDATE",
    "REPORT_FINAL_BARRIER",
)
GATE_NAME = "AUTHORITATIVE_NEB_EXECUTION_GATE"


def decision_from_quality(
    quality: dict[str, Any],
    evidence: dict[str, Any],
    allowed: tuple[str, ...],
    next_check: str,
    *,
    default_decision: str | None = None,
) -> dict[str, Any]:
    return make_decision(
        default_decision
        or {
            "UNDERRESOLVED_REACTION_COORDINATE": "STOP_UNDERRESOLVED_PATH",
        }.get(quality.get("PATH_QUALITY_STATUS"), "STOP_PATH_QUALITY"),
        quality.get("REASON_CODES", []),
        evidence,
        allowed,
        next_check,
        critical=quality.get("CRITICAL_IMAGES", []),
        interpretation=quality.get("CHEMICAL_INTERPRETATION"),
        files_saved=quality.get("FILES_SAVED", []),
        cost=quality.get("COMPUTE_COST_ASSESSMENT"),
    )


def make_decision(
    decision: str,
    reasons: list[Any],
    evidence: dict[str, Any],
    allowed: tuple[str, ...],
    next_check: str,
    *,
    critical: list[str] | None = None,
    interpretation: str | None = None,
    files_saved: list[str] | None = None,
    cost: str | None = None,
) -> dict[str, Any]:
    allowed_set = set(allowed)
    return {
        "schema_version": 2,
        "gate": GATE_NAME,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "state_sha256": sha256_json(evidence),
        "DECISION": decision,
        "REASON_CODES": [str(value) for value in reasons],
        "EVIDENCE": evidence,
        "CRITICAL_IMAGES": critical or [],
        "CHEMICAL_INTERPRETATION": interpretation,
        "FILES_SAVED": files_saved or [],
        "ALLOWED_ACTIONS": [action for action in ACTIONS if action in allowed_set],
        "FORBIDDEN_ACTIONS": [action for action in ACTIONS if action not in allowed_set],
        "NEXT_REQUIRED_CHECK": next_check,
        "SUBMISSION_ALLOWED": bool(
            {
                "SUBMIT_VASP",
                "SUBMIT_DIAGNOSTIC_VASP",
                "ENABLE_CI_NEB",
                "START_DIMER",
                "START_VFA",
            }
            & allowed_set
        ),
        "CI_NEB_ALLOWED": "ENABLE_CI_NEB" in allowed_set,
        "DIMER_ALLOWED": "START_DIMER" in allowed_set,
        "VFA_ALLOWED": "START_VFA" in allowed_set,
        "TS_CLAIM_ALLOWED": "APPROVE_TS_CANDIDATE" in allowed_set,
        "COMPUTE_COST_ASSESSMENT": cost,
    }
