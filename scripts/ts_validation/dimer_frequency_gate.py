from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file


REVIEW_DECISIONS = {"allow_frequency_handoff", "accept_for_ts_validation"}


def evaluate_dimer_frequency_gate(
    analysis: dict[str, Any],
    analysis_path: Path,
    source_structure: Path,
    review_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate the Dimer-to-frequency gate without promoting a TS claim."""

    warnings = sorted(set(analysis.get("dimer_soft_warnings", [])))
    hard_gate_passed = bool(
        analysis.get("technically_converged")
        and analysis.get("vasp_force_converged")
        and analysis.get("negative_curvature")
        and analysis.get("contract_bound")
        and analysis.get("mode_reviewed")
        and analysis.get("final_mode_reviewed")
        and analysis.get("normal_completion")
        and not analysis.get("fatal_keywords")
    )
    soft_gate_passed = bool(
        analysis.get("dimer_soft_gate_passed")
        or (
            analysis.get("dimer_force_converged", analysis.get("force_converged"))
            and analysis.get("torque_converged")
        )
    )
    review = _validated_review(
        review_path,
        analysis_path=analysis_path,
        source_structure=source_structure,
        warning_codes=warnings,
    )
    decision = review.get("decision")
    review_accepted = bool(review)
    return {
        "hard_gate_passed": hard_gate_passed,
        "soft_gate_passed": soft_gate_passed,
        "soft_warning_codes": warnings,
        "manual_review_accepted": review_accepted,
        "manual_review_decision": decision,
        "manual_review_path": str(review_path.resolve()) if review_accepted and review_path else None,
        "manual_review_sha256": sha256_file(review_path) if review_accepted and review_path else None,
        "frequency_handoff_allowed": bool(
            hard_gate_passed and (soft_gate_passed or review_accepted)
        ),
        "ts_validation_eligible": bool(
            hard_gate_passed
            and (soft_gate_passed or decision == "accept_for_ts_validation")
        ),
    }


def _validated_review(
    review_path: Path | None,
    *,
    analysis_path: Path,
    source_structure: Path,
    warning_codes: list[str],
) -> dict[str, Any]:
    if review_path is None or not review_path.is_file():
        return {}
    review = load_json_object(review_path)
    valid = bool(
        review.get("status") == "accepted"
        and review.get("decision") in REVIEW_DECISIONS
        and review.get("reviewer")
        and review.get("reviewed_at")
        and review.get("saddle_analysis_sha256") == sha256_file(analysis_path)
        and review.get("source_structure_sha256") == sha256_file(source_structure)
        and sorted(set(review.get("acknowledged_warning_codes", []))) == warning_codes
    )
    return review if valid else {}
