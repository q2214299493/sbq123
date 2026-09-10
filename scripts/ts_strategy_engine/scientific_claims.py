"""Apply current scientific evidence to claim eligibility; never execute work."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object

from .execution_decision import make_decision
from .execution_evidence import source_bindings_valid


SCIENTIFIC_CLAIM_ACTIONS = frozenset({"APPROVE_TS_CANDIDATE", "REPORT_FINAL_BARRIER"})


def _verify_scientific_owner(validation: dict[str, Any], path: Path) -> None:
    from scripts.ts_validation.analyze_vfa import validate_neb_vfa_binding
    from scripts.ts_validation.validation_pipeline import evaluate_validation_pipeline

    if validation.get("source_method") == "dimer":
        handoff_path = Path(validation["vfa_handoff"])
        if not handoff_path.is_absolute():
            handoff_path = path.parent / handoff_path
        handoff = load_json_object(handoff_path)
        analysis_path = Path(handoff["saddle_analysis_source"])
        if not analysis_path.is_absolute():
            analysis_path = handoff_path.parent / analysis_path
        result = evaluate_validation_pipeline(
            dimer_analysis_path=analysis_path, vfa_analysis_path=path,
            vfa_workdir=Path(validation["workdir"]),
        )
        if not result["scientifically_validated_ts"]:
            raise ValueError("current DIMER/VFA is not accepted: " + result["status"])
    else:
        validate_neb_vfa_binding(validation, path)


def scientific_claim_decision(evidence: dict[str, Any]) -> dict[str, Any]:
    """Revalidate on creation and on every validate_decision/require_action call."""
    binding = evidence.get("source_bindings", {}).get("validation", {})
    reason = "CURRENT_TS_VALIDATION_EVIDENCE_MISSING"
    try:
        if binding and Path(binding.get("path", "")).is_file():
            reason = "CURRENT_TS_VALIDATION_EVIDENCE_STALE"
            if source_bindings_valid(evidence, ("validation",)):
                reason = "CURRENT_TS_VALIDATION_EVIDENCE_INVALID"
                _verify_scientific_owner(evidence["validation"], Path(binding["path"]))
                reason = "CURRENT_TS_VALIDATION_EVIDENCE_STALE"
                if not source_bindings_valid(evidence, ("validation",)):
                    raise ValueError("validation source changed during scientific verification")
                return make_decision(
                    "VALIDATED_TS", [], evidence, ("APPROVE_TS_CANDIDATE",),
                    "REGISTER_VALIDATED_TS_EVIDENCE",
                )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        detail = str(exc)
    else:
        detail = reason
    # A gate has no current database-backed final-energy evidence. Reporting a
    # barrier belongs to record_matched_static_barrier after its own checks.
    return make_decision(
        "NEEDS_CURRENT_TS_VALIDATION_EVIDENCE", [reason], evidence, (),
        "REVIEW_AND_REGENERATE_BOUND_TS_VALIDATION", interpretation=detail,
    )
