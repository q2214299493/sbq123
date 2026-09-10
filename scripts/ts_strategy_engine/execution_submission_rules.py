"""Existing gate decision rules for submission and progress; no transport."""
from __future__ import annotations

from typing import Any

from .dimer_gate import coarse_neb_peak_stall_evidence
from .execution_decision import (
    decision_from_quality as _decision_from_quality,
    make_decision as _make_decision,
)
from .execution_evidence import (
    authorized_actions, diagnostic_actions, source_bindings_valid, warning_reason_codes,
)
from .execution_path_rules import INITIAL_SUBMISSIONS
from .scientific_claims import scientific_claim_decision


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


def blocking_decision(
    geometry: dict[str, Any],
    analysis: dict[str, Any],
    quality: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any] | None:
    preflight = evidence.get("preflight", {})
    dimer_start_ready = bool(
        preflight.get("kind") == "dimer"
        and preflight.get("passed")
        and preflight.get("dimer_hard_gate_passed")
    )
    dimer_preparation_candidate = bool(
        not preflight
        and evidence.get("authorization", {}).get("action") == "PREPARE_DIMER_HANDOFF"
        and evidence.get("path_reviewed")
        and analysis.get("image_sequence_complete")
        and analysis.get("internal_maximum")
    )
    if geometry.get("status") == "STOP" and geometry.get("errors"):
        return _make_decision(
            "STOP_DATA_INTEGRITY",
            geometry.get("errors", []),
            evidence,
            authorized_actions(
                evidence,
                "REBUILD_PATH",
                stop_eligible=True,
                required_sources=("geometry", "thresholds", "scheduler"),
            ),
            "CORRECT_STRUCTURE_OR_MAPPING",
        )
    high_force_images = {
        str(row.get("image"))
        for row in analysis.get("high_force_observations", [])
        if row.get("force_eVA") is not None
    }
    persistent_high_force_images = [
        str(image)
        for image in analysis.get("persistent_high_force_failure_images", [])
    ]
    magnetic_high_force_pairs = [
        warning
        for warning in analysis.get("magnetic_continuity", {}).get("warnings", [])
        if str(warning.get("left")) in high_force_images
        or str(warning.get("right")) in high_force_images
    ]
    if persistent_high_force_images or magnetic_high_force_pairs:
        reasons = [
            *[
                f"PERSISTENT_HIGH_NEB_FORCE_NO_DECREASING_TREND:{image}"
                for image in persistent_high_force_images
            ],
            *[
                f"HIGH_NEB_FORCE_WITH_MAGNETIC_DISCONTINUITY:{row.get('left')}:{row.get('right')}"
                for row in magnetic_high_force_pairs
            ],
        ]
        return _make_decision(
            "STOP_PATH_FAILURE",
            reasons,
            evidence,
            authorized_actions(
                evidence,
                "REBUILD_PATH",
                stop_eligible=True,
                required_sources=("geometry", "analysis", "thresholds", "scheduler"),
            ),
            "DIAGNOSE_OR_REBUILD_PATH",
        )
    if analysis.get("path_binding_valid") is False:
        reasons = analysis.get("path_binding", {}).get(
            "errors", ["path_not_bound_to_contract"]
        )
        return _make_decision(
            "STOP_DATA_INTEGRITY",
            reasons,
            evidence,
            authorized_actions(
                evidence,
                stop_eligible=True,
                required_sources=("analysis", "thresholds", "scheduler"),
            ),
            "REGENERATE_CONTRACT_BOUND_PATH",
        )
    electronic_failure = bool(
        analysis.get("fatal_keywords")
        or analysis.get("scf_persistent_failure_images")
    )
    if (
        electronic_failure
        and not analysis.get("electronic_remediation_passed")
        and not dimer_start_ready
        and not dimer_preparation_candidate
    ):
        reasons = quality.get("REASON_CODES") or [
            "ELECTRONIC_CONVERGENCE_FAILURE",
            *analysis.get("scf_exhausted_images", []),
        ]
        allowed = diagnostic_actions(
            evidence,
            stop_eligible=True,
            required_sources=("analysis", "thresholds", "scheduler"),
        )
        next_check = (
            "TEST_FAILED_IMAGE_AS_SINGLE_POINT"
            if "SUBMIT_DIAGNOSTIC_VASP" in allowed
            else "PREFLIGHT_FAILED_IMAGE_SINGLE_POINT"
        )
        return _make_decision(
            "STOP_ELECTRONIC_FAILURE", reasons, evidence, allowed, next_check
        )
    if (
        quality.get("PATH_QUALITY_STATUS") == "UNDERRESOLVED_REACTION_COORDINATE"
        and not dimer_start_ready
        and not dimer_preparation_candidate
    ):
        return _decision_from_quality(
            quality,
            evidence,
            authorized_actions(
                evidence,
                "REBUILD_PATH",
                stop_eligible=True,
                required_sources=(
                    "geometry",
                    "analysis",
                    "path_quality",
                    "thresholds",
                    "scheduler",
                ),
            ),
            "REBUILD_DENSIFIED_FULL_IS_FS_PATH",
        )
    return None

def progress_decision(
    analysis: dict[str, Any],
    quality: dict[str, Any],
    preflight: dict[str, Any],
    validation: dict[str, Any],
    evidence: dict[str, Any],
    climb: bool,
    path_reviewed: bool,
) -> dict[str, Any]:
    if analysis.get("status") != "NO_OUTPUT" and "path_binding_valid" not in analysis:
        return _make_decision(
            "NEEDS_PATH_BINDING_EVIDENCE",
            ["PATH_BINDING_EVIDENCE_MISSING"],
            evidence,
            (),
            "VALIDATE_PATH_AGAINST_REACTION_CONTRACT",
        )
    if analysis.get("status") == "NO_OUTPUT":
        if not path_reviewed:
            return _make_decision(
                "NEEDS_PATH_REVIEW",
                ["PATH_REVIEW_MISSING"],
                evidence,
                (),
                "RUN_DIST_AND_NEBMOVIE_REVIEW",
            )
        if not preflight.get("passed"):
            return _make_decision(
                "NEEDS_SUBMISSION_PREFLIGHT",
                ["SUBMISSION_PREFLIGHT_MISSING"],
                evidence,
                (),
                "RUN_RESOURCE_AND_INPUT_PREFLIGHT",
            )
        ready = INITIAL_SUBMISSIONS.get(preflight.get("kind"))
        if ready:
            decision, action, next_check = ready
            return _make_decision(decision, [], evidence, (action,), next_check)
        return _make_decision(
            "NEEDS_PARENT_PATH_EVIDENCE",
            ["CI_OR_DIMER_PARENT_EVIDENCE_MISSING"],
            evidence,
            (),
            "BIND_REVIEWED_PARENT_NEB_STATE",
        )
    if not analysis.get("image_sequence_complete"):
        return _make_decision(
            "STOP_DATA_INTEGRITY",
            ["INCOMPLETE_IMAGE_SEQUENCE"],
            evidence,
            authorized_actions(evidence),
            "RESTORE_COMPLETE_PATH",
        )

    if validation:
        return scientific_claim_decision(evidence)
    dimer = dimer_progress_decision(
        analysis, quality, preflight, evidence, climb, path_reviewed
    )
    if dimer:
        return dimer
    scheduler = evidence.get("scheduler", {})
    running = scheduler.get("status") == "RUN" and bool(scheduler.get("job_id"))
    warning_reasons = warning_reason_codes(evidence["geometry"], analysis, quality)
    return _make_decision(
        "CONTINUE_NO_CLIMB_NEB" if running else "NEEDS_CURRENT_SCHEDULER_EVIDENCE",
        warning_reasons if running else ["CURRENT_RUN_STATE_NOT_PROVEN"],
        evidence,
        ("CONTINUE_JOB",) if running else (),
        "CONTINUE_MONITORING_CURRENT_ORDINARY_NEB"
        if running
        else "QUERY_CURRENT_JOB_STATE",
    )

def dimer_progress_decision(
    analysis: dict[str, Any],
    quality: dict[str, Any],
    preflight: dict[str, Any],
    evidence: dict[str, Any],
    climb: bool,
    path_reviewed: bool,
) -> dict[str, Any] | None:
    coarse_peak_stall = coarse_neb_peak_stall_evidence(analysis)
    if preflight.get("kind") == "dimer":
        if preflight.get("passed") and preflight.get("dimer_hard_gate_passed"):
            return _make_decision(
                "READY_FOR_DIMER",
                [],
                evidence,
                ("START_DIMER",),
                "SUBMIT_DIMER",
            )
        return _make_decision(
            "DIMER_HARD_GATE_FAILED",
            preflight.get("errors") or ["DIMER_HARD_GATE_EVIDENCE_MISSING"],
            evidence,
            (),
            "CORRECT_DIMER_TRIAD_MODECAR_OR_CHEMICAL_REVIEW",
        )
    explicit_dimer_request = (
        evidence.get("authorization", {}).get("action") == "PREPARE_DIMER_HANDOFF"
    )
    if (
        quality.get("PATH_QUALITY_STATUS") == "CI_NEB_READINESS_EVIDENCE"
        and analysis.get("internal_maximum")
        and path_reviewed
        and not climb
    ):
        if preflight.get("passed") and preflight.get("kind") == "ci_neb":
            return _make_decision(
                "READY_FOR_CI_NEB_OR_DIMER_HANDOFF",
                [],
                evidence,
                ("ENABLE_CI_NEB", "PREPARE_DIMER_HANDOFF"),
                "SELECT_CI_NEB_OR_BUILD_DIMER_HANDOFF",
            )
        return _make_decision(
            "READY_TO_SELECT_CI_NEB_OR_DIMER",
            ["CI_NEB_PREFLIGHT_MISSING", "DIMER_PREFLIGHT_MISSING"],
            evidence,
            ("PREPARE_DIMER_HANDOFF",),
            "SELECT_CI_NEB_PREFLIGHT_OR_BUILD_DIMER_HANDOFF",
        )
    if analysis.get("internal_maximum") and path_reviewed and (
        climb or explicit_dimer_request or coarse_peak_stall["passed"]
    ):
        recommended_reasons = []
        if not analysis.get("technically_converged"):
            recommended_reasons.append("PARENT_NEB_FULL_CONVERGENCE_RECOMMENDED")
        if quality.get("PATH_QUALITY_STATUS") != "CI_NEB_READINESS_EVIDENCE":
            recommended_reasons.append("PARENT_NEB_PEAK_REFINEMENT_RECOMMENDED")
        if coarse_peak_stall["passed"]:
            recommended_reasons.append("COARSE_NEB_PEAK_STALL_DIMER_RECOMMENDED")
        return _make_decision(
            "READY_TO_PREPARE_DIMER_HANDOFF",
            recommended_reasons or ["DIMER_PREFLIGHT_MISSING"],
            evidence,
            ("PREPARE_DIMER_HANDOFF",),
            "BUILD_REVIEW_AND_PREFLIGHT_DIMER_INPUT",
        )
    return None
