from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.aqcat25_ts_schema import load_document
from scripts.artifact_io import sha256_file

from .active_learning_common import (
    current_round,
    load_policy,
    load_state,
    utc_now,
    write_json,
)


def register_ts_domain_calibration(state_path: Path, review_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    if state["status"] != "awaiting_ts_domain_calibration_review":
        raise ValueError("workflow is not awaiting TS-domain calibration review")
    current = current_round(state)
    assessment_ref = current.get("ts_domain_assessment") or {}
    assessment_path = Path(str(assessment_ref.get("path", "")))
    if (
        not assessment_path.is_file()
        or sha256_file(assessment_path) != assessment_ref.get("sha256")
    ):
        raise ValueError("bootstrap TS-domain assessment is missing or hash-mismatched")
    assessment = load_document(
        assessment_path, expected_kind="aqcat25_ts_domain_assessment"
    )
    if assessment["status"] != "bootstrap_passed":
        raise ValueError("TS-domain calibration requires a passed bootstrap assessment")
    review = load_document(
        review_path, expected_kind="aqcat25_ts_domain_calibration_review"
    )
    if (
        review["assessment_sha256"] != assessment_ref["sha256"]
        or review["checkpoint_sha256"] != assessment["checkpoint_sha256"]
        or review["compatibility_sha256"] != state["compatibility_sha256"]
    ):
        raise ValueError("TS-domain calibration review is not bound to the active assessment")
    metric_keys = {
        "component_mae_eV_per_A_max": "component_mae_eV_per_A",
        "vector_rmse_eV_per_A_max": "vector_rmse_eV_per_A",
        "vector_p95_eV_per_A_max": "vector_p95_eV_per_A",
        "vector_max_eV_per_A_max": "vector_max_eV_per_A",
    }
    thresholds = review["force_acceptance"]
    if any(
        float(thresholds[threshold]) < float(assessment["metrics"][metric])
        for threshold, metric in metric_keys.items()
    ):
        raise ValueError("reviewed TS force thresholds are tighter than the measured bootstrap errors")
    policy = load_policy(Path(state["policy_path"]))
    screen = policy["local_force_screen"]
    safety_ceilings = {
        "component_mae_eV_per_A_max": float(screen["component_mae_eV_per_A_max"]),
        "vector_rmse_eV_per_A_max": float(screen["vector_rmse_eV_per_A_max"]),
        "vector_p95_eV_per_A_max": float(screen["vector_max_eV_per_A_max"]),
        "vector_max_eV_per_A_max": float(screen["vector_max_eV_per_A_max"]),
    }
    if any(float(thresholds[key]) > ceiling for key, ceiling in safety_ceilings.items()):
        raise ValueError("reviewed TS force thresholds exceed the configured safety ceilings")
    calibration = {
        "calibration_id": assessment["calibration_id"],
        "checkpoint_sha256": assessment["checkpoint_sha256"],
        "compatibility_sha256": state["compatibility_sha256"],
        "reaction_domain": review["reaction_domain"],
        "force_acceptance": thresholds,
        "assessment_path": str(assessment_path.resolve()),
        "assessment_sha256": assessment_ref["sha256"],
        "review_path": str(review_path.resolve()),
        "review_sha256": sha256_file(review_path),
        "reviewer": review["reviewer"],
        "reviewed_at": review["reviewed_at"],
    }
    state["ts_domain_calibration"] = calibration
    current["status"] = "independent_ts_domain_validation_passed"
    state["status"] = "ml_acceleration_ready_for_vasp_refinement"
    state["next_action"] = "work_review_then_VASP_NEB_CI_NEB_or_DIMER"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return calibration


def decide_ts_domain_reuse(state_path: Path, context_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    if state["status"] != "awaiting_ts_domain_reuse_decision":
        raise ValueError("workflow is not awaiting a TS-domain reuse decision")
    calibration = state.get("ts_domain_calibration") or {}
    context = load_document(
        context_path, expected_kind="aqcat25_ts_domain_reuse_context"
    )
    policy = load_policy(Path(state["policy_path"]))
    schedule = policy["ts_domain_validation"]["schedule"]
    current = current_round(state)
    checks = {
        "not_every_path": not schedule["every_reviewed_neb_path_requires_new_validation"],
        "checkpoint": context["checkpoint_sha256"]
        == calibration.get("checkpoint_sha256")
        == current["candidate"]["checkpoint_sha256"],
        "compatibility": context["compatibility_sha256"]
        == calibration.get("compatibility_sha256")
        == state["compatibility_sha256"],
        "reaction_domain": context["reaction_domain"]
        == calibration.get("reaction_domain")
        and context["reaction_domain_in_scope"],
        "novelty_or_uncertainty": context["novelty_or_uncertainty_gate_passed"],
        "periodic_audit": not context["periodic_audit_due"],
    }
    reused = all(checks.values())
    current["ts_domain_reuse_decision"] = {
        "context_path": str(context_path.resolve()),
        "context_sha256": sha256_file(context_path),
        "checks": checks,
        "reused": reused,
    }
    if reused:
        current["status"] = "independent_ts_domain_validation_reused"
        state["status"] = "ml_acceleration_ready_for_vasp_refinement"
        state["next_action"] = "work_review_then_VASP_NEB_CI_NEB_or_DIMER"
    else:
        current["status"] = "awaiting_independent_ts_domain_validation"
        state["status"] = current["status"]
        state["next_action"] = "prepare_new_independent_TS_domain_validation_set"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return current["ts_domain_reuse_decision"]
