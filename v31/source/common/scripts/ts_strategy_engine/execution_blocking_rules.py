"""Priority blocking decisions consumed by the authoritative execution gate."""
from __future__ import annotations

from typing import Any

from .execution_decision import (
    decision_from_quality as _decision_from_quality,
    make_decision as _make_decision,
)
from .execution_evidence import authorized_actions, diagnostic_actions


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
