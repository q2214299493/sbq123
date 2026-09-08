from __future__ import annotations

from typing import Any

from .execution_decision import make_decision as _make_decision
from .execution_evidence import authorized_actions, source_bindings_valid


def vfa_submission_decision(evidence: dict[str, Any]) -> dict[str, Any] | None:
    preflight = evidence.get("preflight", {})
    if preflight.get("kind") != "vfa":
        return None
    if preflight.get("passed") and preflight.get("vfa_hard_gate_passed"):
        return _make_decision(
            "READY_FOR_DIAGNOSTIC_VFA",
            [],
            evidence,
            ("START_VFA",),
            "SUBMIT_DIAGNOSTIC_PARTIAL_HESSIAN_FREQUENCY",
        )
    return _make_decision(
        "VFA_HARD_GATE_FAILED",
        preflight.get("errors") or ["VFA_PREFLIGHT_EVIDENCE_MISSING"],
        evidence,
        (),
        "CORRECT_VFA_HANDOFF_SCOPE_OR_INPUT",
    )


def connectivity_submission_decision(evidence: dict[str, Any]) -> dict[str, Any] | None:
    preflight = evidence.get("preflight", {})
    if preflight.get("kind") != "connectivity_relax":
        return None
    authorization = evidence.get("authorization", {})
    authorization_valid = bool(
        authorization.get("schema_version") == 1
        and authorization.get("document_kind") == "user_execution_authorization"
        and authorization.get("action") == "SUBMIT_VASP"
        and authorization.get("calculation_kind") == "connectivity_relax"
        and authorization.get("authorized_at")
        and authorization.get("source")
        and source_bindings_valid(evidence, ("authorization", "preflight"))
    )
    if (
        preflight.get("passed")
        and preflight.get("connectivity_hard_gate_passed")
        and authorization_valid
    ):
        return _make_decision(
            "READY_FOR_TS_CONNECTIVITY_RELAXATION",
            [],
            evidence,
            ("SUBMIT_VASP",),
            "SUBMIT_BIDIRECTIONAL_DOWNHILL_RELAXATION_BRANCH",
        )
    reasons = list(preflight.get("errors") or [])
    if not authorization_valid:
        reasons.append("CONNECTIVITY_SUBMISSION_AUTHORIZATION_INVALID_OR_UNBOUND")
    return _make_decision(
        "CONNECTIVITY_HARD_GATE_FAILED",
        reasons,
        evidence,
        (),
        "CORRECT_CONNECTIVITY_DISPLACEMENT_INPUT_OR_AUTHORIZATION",
    )


def user_requested_stop(evidence: dict[str, Any]) -> dict[str, Any] | None:
    authorization = evidence.get("authorization", {})
    if authorization.get("action") != "STOP_JOB":
        return None
    scheduler = evidence.get("scheduler", {})
    valid = bool(
        authorization.get("schema_version") == 1
        and authorization.get("document_kind") == "user_execution_authorization"
        and str(authorization.get("job_id")) == str(scheduler.get("job_id"))
        and scheduler.get("status") in {"PEND", "RUN"}
        and scheduler.get("status")
        in set(authorization.get("allowed_scheduler_statuses", []))
        and authorization.get("authorized_at")
        and authorization.get("source")
    )
    if not valid:
        return _make_decision(
            "INVALID_USER_STOP_REQUEST",
            ["USER_STOP_AUTHORIZATION_INVALID"],
            evidence,
            (),
            "RECORD_EXPLICIT_JOB_BOUND_STOP_AUTHORIZATION",
        )
    allowed = authorized_actions(
        evidence,
        stop_eligible=True,
        required_sources=("scheduler", "authorization"),
    )
    if "STOP_JOB" not in allowed:
        return _make_decision(
            "UNBOUND_USER_STOP_REQUEST",
            ["USER_STOP_AUTHORIZATION_NOT_FILE_BOUND"],
            evidence,
            (),
            "BIND_STOP_AUTHORIZATION_AND_CURRENT_SCHEDULER_EVIDENCE",
        )
    return _make_decision(
        "STOP_USER_REQUESTED",
        ["EXPLICIT_USER_STOP_REQUEST"],
        evidence,
        allowed,
        "CONFIRM_LSF_EXIT",
    )
