#!/usr/bin/env python3
"""Preflight and prepare a non-executable, hash-bound MatRIS fine-tune request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.matris_training_exclusions import load_heldout_exclusions


FINE_TUNE_DECISION = (
    "fine_tune_MatRIS_then_require_new_checkpoint_and_complete_path_rerun"
)
FINE_TUNE_STATUS = "awaiting_energy_force_aware_MatRIS_fine_tuning"


def _load_bound_json(reference: dict[str, Any], *, name: str) -> tuple[Path, dict[str, Any]]:
    path = Path(str(reference.get("path", "")))
    expected = str(reference.get("sha256", ""))
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"{name} binding failed")
    return path.resolve(), load_json_object(path)


def _inspect_bound_json(
    reference: dict[str, Any],
    *,
    path_field: str = "path",
    hash_field: str = "sha256",
    blocker: str,
) -> tuple[Path, dict[str, Any], str | None, list[str]]:
    path = Path(str(reference.get(path_field, "")))
    expected = str(reference.get(hash_field, ""))
    actual = sha256_file(path) if path.is_file() else None
    if actual != expected:
        return path.resolve(), {}, actual, [blocker]
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("bound YAML root must be an object")
        else:
            payload = load_json_object(path)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError):
        return path.resolve(), {}, actual, [blocker]
    return path.resolve(), payload, actual, []


def _route_blockers(
    state: dict[str, Any],
    exclusions: dict[str, Any],
    assessment_ref: dict[str, Any],
    assessment: dict[str, Any],
    labels: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[str], str, dict[str, Any] | None]:
    blockers: list[str] = []
    for payload, prefix in (
        (exclusions, "EXCLUSION"),
        (assessment, "ASSESSMENT"),
        (labels, "LABEL_SET"),
    ):
        if payload and payload.get("reaction_id") != state.get("reaction_id"):
            blockers.append(f"{prefix}_REACTION_MISMATCH")
        if payload and payload.get("round_index") != state.get("round_index"):
            blockers.append(f"{prefix}_ROUND_MISMATCH")
    if state.get("status") != FINE_TUNE_STATUS:
        blockers.append("MATRIS_FINE_TUNE_STATUS_NOT_REACHED")
    if assessment_ref.get("decision") != FINE_TUNE_DECISION:
        blockers.append("MATRIS_FINE_TUNE_DECISION_NOT_REACHED")
    if assessment and assessment.get("decision") != assessment_ref.get("decision"):
        blockers.append("STATE_ASSESSMENT_DECISION_MISMATCH")

    primary_checkpoint = exclusions["frozen_model_checkpoint_sha256"]["primary"]
    assessed_checkpoint = (
        assessment.get("models", {})
        .get("matris_primary", {})
        .get("checkpoint_sha256")
    )
    if assessment and assessed_checkpoint != primary_checkpoint:
        blockers.append("MATRIS_CHECKPOINT_MISMATCH")

    fine_tuning_policy = policy.get("matris_fine_tuning")
    if policy and not isinstance(fine_tuning_policy, dict):
        blockers.append("MATRIS_FINE_TUNING_POLICY_MISSING")
        fine_tuning_policy = None
    heldout_policy = policy.get("held_out_validation")
    if policy and (
        not isinstance(heldout_policy, dict)
        or heldout_policy.get(
            "exclusion_manifest_required_for_all_matris_training"
        )
        is not True
    ):
        blockers.append("HELDOUT_EXCLUSION_POLICY_NOT_ENFORCED")
    return blockers, primary_checkpoint, fine_tuning_policy


def _load_preflight_context(
    state_path: Path, exclusion_path: Path, expected_exclusion_sha256: str
) -> dict[str, Any]:
    state_path = state_path.resolve()
    exclusion_path = exclusion_path.resolve()
    state = load_json_object(state_path)
    if state.get("document_kind") != "dual_model_ts_active_learning_state":
        raise ValueError("invalid dual-model active-learning state")
    exclusions = load_heldout_exclusions(
        exclusion_path, expected_sha256=expected_exclusion_sha256
    )

    source_plan_path, source_plan = _load_bound_json(
        exclusions["source_heldout_plan"], name="held-out source plan"
    )
    policy_ref = state.get("source_bindings", {}).get("policy", {})
    policy_path, policy, policy_hash, integrity_blockers = _inspect_bound_json(
        policy_ref,
        blocker="ACTIVE_LEARNING_POLICY_BINDING_FAILED",
    )
    assessment_ref = state.get("vasp_error_assessment") or {}
    assessment_path, assessment, assessment_hash, assessment_blockers = (
        _inspect_bound_json(
            assessment_ref,
            blocker="VASP_ERROR_ASSESSMENT_BINDING_FAILED",
        )
    )
    integrity_blockers.extend(assessment_blockers)
    label_ref = state.get("vasp_label_batch") or {}
    label_path, labels, label_sha256, label_blockers = _inspect_bound_json(
        label_ref,
        path_field="completed_label_set_path",
        hash_field="completed_label_set_sha256",
        blocker="VASP_TRAINING_LABEL_BINDING_FAILED",
    )
    integrity_blockers.extend(label_blockers)
    if source_plan.get("document_kind") != (
        "dual_model_ts_heldout_validation_candidate_plan"
    ):
        raise ValueError("invalid held-out source plan")
    if assessment.get("document_kind") != "dual_model_ts_vasp_error_assessment":
        integrity_blockers.append("INVALID_VASP_ERROR_ASSESSMENT")
    if labels.get("document_kind") != "dual_model_ts_vasp_force_label_set":
        integrity_blockers.append("INVALID_VASP_TRAINING_LABEL_SET")
    if assessment and assessment.get("source_vasp_label_set_sha256") != label_sha256:
        integrity_blockers.append("ASSESSMENT_LABEL_SET_BINDING_MISMATCH")

    blockers, primary_checkpoint, fine_tuning_policy = _route_blockers(
        state, exclusions, assessment_ref, assessment, labels, policy
    )
    return {
        "state_path": state_path,
        "exclusion_path": exclusion_path,
        "state": state,
        "exclusions": exclusions,
        "source_plan_path": source_plan_path,
        "policy_ref": policy_ref,
        "policy_path": policy_path,
        "policy_hash": policy_hash,
        "assessment_ref": assessment_ref,
        "assessment_path": assessment_path,
        "assessment_hash": assessment_hash,
        "label_ref": label_ref,
        "label_path": label_path,
        "label_sha256": label_sha256,
        "blockers": integrity_blockers + blockers,
        "primary_checkpoint": primary_checkpoint,
        "fine_tuning_policy": fine_tuning_policy,
    }


def _build_preflight_report(
    context: dict[str, Any], request_output: Path
) -> dict[str, Any]:
    blockers = context["blockers"]
    passed = not blockers
    state_path = context["state_path"]
    exclusion_path = context["exclusion_path"]
    assessment_ref = context["assessment_ref"]
    label_ref = context["label_ref"]
    policy_ref = context["policy_ref"]

    return {
        "schema_version": 1,
        "document_kind": "matris_finetune_request_preflight",
        "passed": passed,
        "request_generated": passed,
        "request_path": str(request_output.resolve()) if passed else None,
        "blockers": blockers,
        "bindings": {
            "active_learning_state": {
                "path": str(state_path),
                "sha256": sha256_file(state_path),
            },
            "trigger_assessment": {
                "path": str(context["assessment_path"]),
                "sha256": context["assessment_hash"],
                "expected_sha256": assessment_ref.get("sha256"),
            },
            "training_label_set": {
                "path": str(context["label_path"]),
                "sha256": context["label_sha256"],
                "expected_sha256": label_ref.get("completed_label_set_sha256"),
            },
            "heldout_exclusion_manifest": {
                "path": str(exclusion_path),
                "sha256": sha256_file(exclusion_path),
                "source_plan_path": str(context["source_plan_path"]),
                "excluded_structure_count": len(
                    context["exclusions"]["excluded_structures"]
                ),
            },
            "active_learning_policy": {
                "path": str(context["policy_path"]),
                "sha256": context["policy_hash"],
                "expected_sha256": policy_ref.get("sha256"),
            },
        },
        "execution_authorized": False,
        "automatic_submission": False,
    }


def _build_request(
    context: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    fine_tuning_policy = context["fine_tuning_policy"]
    if fine_tuning_policy is None:  # pragma: no cover - paired with a blocker
        raise RuntimeError("fine-tuning policy unexpectedly missing after preflight")
    state = context["state"]
    return {
        "schema_version": 1,
        "document_kind": "matris_energy_force_finetune_request",
        "status": "prepared_awaiting_separate_finetune_authorization",
        "reaction_id": state["reaction_id"],
        "round_index": state["round_index"],
        "base_checkpoint_sha256": context["primary_checkpoint"],
        "source_active_learning_state": report["bindings"]["active_learning_state"],
        "trigger_assessment": report["bindings"]["trigger_assessment"],
        "training_label_set": report["bindings"]["training_label_set"],
        "heldout_exclusion_manifest": report["bindings"][
            "heldout_exclusion_manifest"
        ],
        "active_learning_policy": report["bindings"]["active_learning_policy"],
        "training_targets": fine_tuning_policy["training_targets"],
        "replay_required": fine_tuning_policy["replay_required"],
        "acceptance_requires": fine_tuning_policy["acceptance_requires"],
        "force_only_checkpoint_production_promotion": fine_tuning_policy[
            "force_only_checkpoint_production_promotion"
        ],
        "execution_authorized": False,
        "automatic_submission": False,
        "next_required_action": "request_separate_MatRIS_finetune_authorization",
    }


def preflight_and_prepare(
    state_path: Path,
    exclusion_path: Path,
    *,
    expected_exclusion_sha256: str,
    request_output: Path,
    preflight_output: Path,
) -> dict[str, Any]:
    """Write a request only when the local scientific and integrity gates pass."""

    context = _load_preflight_context(
        state_path, exclusion_path, expected_exclusion_sha256
    )
    report = _build_preflight_report(context, request_output)
    write_json_atomic(preflight_output, report, ensure_ascii=True)
    if not report["passed"]:
        return report

    request = _build_request(context, report)
    write_json_atomic(request_output, request, ensure_ascii=True)
    report["request_sha256"] = sha256_file(request_output)
    write_json_atomic(preflight_output, report, ensure_ascii=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--exclusions-sha256", required=True)
    parser.add_argument("--request-output", type=Path, required=True)
    parser.add_argument("--preflight-output", type=Path, required=True)
    args = parser.parse_args()
    report = preflight_and_prepare(
        args.state,
        args.exclusions,
        expected_exclusion_sha256=args.exclusions_sha256,
        request_output=args.request_output,
        preflight_output=args.preflight_output,
    )
    print(json.dumps(report, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
