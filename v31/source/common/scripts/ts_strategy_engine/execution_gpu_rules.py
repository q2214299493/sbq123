"""Reviewed GPU candidate rules used by the canonical execution gate."""
from __future__ import annotations

from .execution_decision import make_decision
from .gpu_dimer_parent import PARENT_METHOD, validate_reviewed_gpu_parent


def reviewed_gpu_decision(analysis, quality, preflight, evidence, climb, path_reviewed, dimer_progress):
    if analysis.get("parent_neb_method") != PARENT_METHOD:
        return None
    reviewed = validate_reviewed_gpu_parent(analysis)
    if not reviewed["passed"] or not path_reviewed:
        return make_decision(
            "DIMER_HARD_GATE_FAILED", reviewed["errors"] or ["GPU_PATH_REVIEW_MISSING"],
            evidence, (), "REVIEW_GPU_PATH_AND_BIND_SOURCE",
        )
    if preflight.get("kind") == "dimer":
        return dimer_progress(analysis, quality, preflight, evidence, climb, path_reviewed)
    return make_decision(
        "READY_TO_PREPARE_DIMER_HANDOFF", ["GPU_PREDICTED_STARTING_CANDIDATE_ONLY"],
        evidence, ("PREPARE_DIMER_HANDOFF",), "BUILD_REVIEW_AND_PREFLIGHT_DIMER_INPUT",
    )
