from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import (
    load_json_object,
    sha256_file,
    source_file_manifest,
    write_json,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "configs" / "ts_validation_pipeline.yaml"


def evaluate_validation_pipeline(
    *,
    dimer_analysis_path: Path,
    path_topology_path: Path | None = None,
    branch_plan_path: Path | None = None,
    segment_id: str | None = None,
    dimer_soft_review_path: Path | None = None,
    vfa_workdir: Path | None = None,
    vfa_analysis_path: Path | None = None,
    connectivity_review_path: Path | None = None,
    positive_run: Path | None = None,
    negative_run: Path | None = None,
    connectivity_report_path: Path | None = None,
    policy_path: Path = DEFAULT_POLICY,
    output: Path | None = None,
) -> dict[str, Any]:
    """Evaluate the next resumable Dimer -> VFA validation action.

    Connectivity arguments remain accepted for CLI compatibility but are not
    part of Dimer validation.
    """

    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    dimer = load_json_object(dimer_analysis_path)
    source_paths = [policy_path, dimer_analysis_path]
    reasons: list[str] = []

    branch_gate = _multi_ts_branch_gate(
        policy,
        path_topology_path,
        branch_plan_path,
        segment_id,
        source_paths,
    )
    if branch_gate:
        status, next_action, branch_reasons = branch_gate
        return _result(
            status, next_action, branch_reasons, source_paths, output
        )
    if segment_id:
        reasons.append(f"MULTI_TS_SEGMENT:{segment_id}")

    dimer_review = _load_optional(dimer_soft_review_path, source_paths)
    dimer_gate, dimer_warnings = _dimer_gate(policy, dimer, dimer_review)
    if dimer_gate:
        status, next_action, gate_reasons = dimer_gate
        return _result(status, next_action, gate_reasons, source_paths, output)
    reasons.extend(dimer_warnings)

    if not vfa_analysis_path or not vfa_analysis_path.is_file():
        submitted = bool(vfa_workdir and (vfa_workdir / "submission_record.json").is_file())
        if submitted:
            source_paths.append(vfa_workdir / "submission_record.json")
        return _result(
            "VFA_RUNNING_OR_AWAITING_ANALYSIS" if submitted else "READY_FOR_VFA",
            "MONITOR_OR_ANALYZE_VFA" if submitted else "PREPARE_AND_GATE_VFA",
            reasons,
            source_paths,
            output,
        )

    vfa = load_json_object(vfa_analysis_path)
    source_paths.append(vfa_analysis_path)
    vfa_gate, thresholds_configured = _vfa_gate(policy, vfa)
    if vfa_gate:
        status, next_action, gate_reasons = vfa_gate
        return _result(
            status, next_action, [*reasons, *gate_reasons], source_paths, output
        )
    if not thresholds_configured:
        reasons.append("FREQUENCY_THRESHOLDS_UNSET_OPTIONAL_CLASSIFICATION_NOT_RUN")
    if not _dimer_final_validation_eligible(dimer, dimer_review):
        return _result(
            "DIMER_FREQUENCY_COMPLETE_SOFT_REVIEW_REQUIRED",
            "REVIEW_DIMER_FORCE_AND_TORQUE_FOR_TS_VALIDATION",
            [*reasons, "DIMER_SOFT_WARNING_ACCEPTED_FOR_FREQUENCY_ONLY"],
            source_paths,
            output,
        )
    # Retain the old arguments without loading them so historical callers do
    # not break and stale connectivity evidence cannot affect Dimer grading.
    _ = (
        connectivity_review_path,
        positive_run,
        negative_run,
        connectivity_report_path,
    )
    return _result(
        "TS_ACCEPTED",
        "RECORD_TS_RESULT",
        reasons,
        source_paths,
        output,
        scientifically_validated_ts=True,
        frequency_validation_passed=True,
    )


def _load_optional(path: Path | None, source_paths: list[Path]) -> dict[str, Any]:
    if not path or not path.is_file():
        return {}
    source_paths.append(path)
    return load_json_object(path)


def _dimer_gate(
    policy: dict[str, Any], dimer: dict[str, Any], review: dict[str, Any]
) -> tuple[tuple[str, str, list[str]] | None, list[str]]:
    missing = [
        key for key in policy["dimer_hard_requirements"] if dimer.get(key) is not True
    ]
    if missing:
        return (
            (
                "BLOCKED_DIMER_HARD_GATE",
                "CORRECT_OR_RESTART_DIMER",
                [f"DIMER_HARD_GATE_FAILED:{key}" for key in missing],
            ),
            [],
        )
    if dimer.get("dimer_soft_gate_passed", False):
        return None, []
    if review.get("decision") not in set(policy["dimer_soft_review_decisions"]):
        return (
            (
                "NEEDS_DIMER_SOFT_GATE_REVIEW",
                "REVIEW_DIMER_FORCE_AND_TORQUE",
                ["DIMER_FORCE_OR_TORQUE_SOFT_WARNING"],
            ),
            [],
        )
    warning = (
        "DIMER_SOFT_WARNING_ACCEPTED_FOR_TS_VALIDATION"
        if review.get("decision") == "accept_for_ts_validation"
        else "DIMER_SOFT_WARNING_ACCEPTED_FOR_FREQUENCY_HANDOFF"
    )
    return None, [warning]


def _dimer_final_validation_eligible(
    dimer: dict[str, Any], review: dict[str, Any]
) -> bool:
    return bool(
        dimer.get("dimer_soft_gate_passed", False)
        or review.get("decision") == "accept_for_ts_validation"
    )


def _vfa_gate(
    policy: dict[str, Any], vfa: dict[str, Any]
) -> tuple[tuple[str, str, list[str]] | None, bool]:
    configured = vfa.get("frequency_threshold_status") == "configured"
    if vfa.get("normal_completion") is not True:
        return (
            (
                "BLOCKED_VFA_INCOMPLETE",
                "DIAGNOSE_OR_RESTART_VFA",
                ["VFA_NORMAL_COMPLETION_MISSING"],
            ),
            configured,
        )
    raw_count = int(vfa.get("imaginary_frequency_count", -1))
    if raw_count != int(policy["vfa"]["required_raw_imaginary_count"]):
        return (
            (
                "BLOCKED_HIGHER_ORDER_SADDLE_OR_SOFT_MODE_REVIEW",
                "CLASSIFY_ADDITIONAL_IMAGINARY_MODE",
                [f"RAW_IMAGINARY_FREQUENCY_COUNT:{raw_count}"],
            ),
            configured,
        )
    mode_valid = bool(
        vfa.get("principal_mode_index") is not None
        and vfa.get("principal_mode_assignment")
        in set(policy["vfa"]["accepted_mode_assignments"])
        and vfa.get("principal_mode_reaction_atom_overlap")
    )
    if not mode_valid:
        assignment = str(vfa.get("principal_mode_assignment", ""))
        expansion_triggers = set(
            policy["vfa"].get("expand_local_active_set_for_mode_assignments", [])
        )
        expand_local_scope = assignment in expansion_triggers
        return (
            (
                "NEEDS_PRINCIPAL_MODE_ASSIGNMENT",
                (
                    "EXPAND_LOCAL_ACTIVE_SET_AND_REPEAT_FREQUENCY"
                    if expand_local_scope
                    else "REVIEW_IMAGINARY_MODE_AGAINST_REACTION_CONTRACT"
                ),
                [
                    "PRINCIPAL_IMAGINARY_MODE_NOT_ACCEPTED",
                    *(
                        ["LOCAL_PARTIAL_HESSIAN_SCOPE_EXPANSION_REQUIRED"]
                        if expand_local_scope
                        else []
                    ),
                ],
            ),
            configured,
        )
    if vfa.get("geometry_status") != "pass":
        return (
            (
                "NEEDS_TS_GEOMETRY_REVIEW",
                "REVIEW_TS_GEOMETRY",
                ["TS_GEOMETRY_NOT_ACCEPTED"],
            ),
            configured,
        )
    if configured and vfa.get("principal_mode_is_meaningful") is not True:
        return (
            (
                "NEEDS_MEANINGFUL_IMAGINARY_MODE_REVIEW",
                "REVIEW_IMAGINARY_FREQUENCY_THRESHOLD_CLASSIFICATION",
                ["PRINCIPAL_IMAGINARY_MODE_BELOW_MEANINGFUL_THRESHOLD"],
            ),
            configured,
        )
    return None, configured


def _multi_ts_branch_gate(
    policy: dict[str, Any],
    topology_path: Path | None,
    plan_path: Path | None,
    segment_id: str | None,
    source_paths: list[Path],
) -> tuple[str, str, list[str]] | None:
    if not topology_path or not topology_path.is_file():
        return None
    topology = load_json_object(topology_path)
    source_paths.append(topology_path)
    peak_count = int(topology.get("independent_ts_candidate_count", 1))
    if peak_count <= 1:
        return None
    rule = policy["multi_transition_state"]
    if topology.get("status") != rule["topology_review_status"]:
        return (
            "NEEDS_MULTI_TS_TOPOLOGY_REVIEW",
            "REVIEW_PATH_MAXIMA_AND_INTERMEDIATE",
            ["MULTI_TS_PATH_TOPOLOGY_NOT_ACCEPTED"],
        )
    intermediates = topology.get("stable_intermediates", [])
    stable = [
        item
        for item in intermediates
        if item.get("relaxation_status") == "converged"
        and item.get("structure_sha256")
    ]
    if len(stable) < peak_count - 1:
        return (
            "NEEDS_STABLE_INTERMEDIATE_CONFIRMATION",
            "RELAX_AND_VALIDATE_INTERMEDIATE_CANDIDATES",
            ["MULTIPLE_TS_CANDIDATES_REQUIRE_CONVERGED_INTERMEDIATE"],
        )
    if not plan_path or not plan_path.is_file():
        return (
            "NEEDS_MULTI_TS_BRANCH_PLAN",
            "BUILD_SEGMENT_LOCAL_REACTION_CONTRACTS",
            ["GLOBAL_IS_FS_CONNECTIVITY_FOR_MULTI_TS_FORBIDDEN"],
        )
    plan = load_json_object(plan_path)
    source_paths.append(plan_path)
    segments = plan.get("segments", [])
    valid_segments = bool(
        plan.get("status") == rule["branch_plan_status"]
        and plan.get("source_path_topology_sha256") == sha256_file(topology_path)
        and len(segments) == peak_count
        and all(
            item.get("segment_id")
            and item.get("initial_endpoint_sha256")
            and item.get("final_endpoint_sha256")
            and item.get("ts_candidate_id")
            and item.get("reaction_contract_sha256")
            for item in segments
        )
    )
    if not valid_segments:
        return (
            "NEEDS_MULTI_TS_BRANCH_PLAN",
            "CORRECT_AND_BIND_SEGMENT_LOCAL_REACTION_CONTRACTS",
            ["MULTI_TS_BRANCH_PLAN_INVALID_OR_UNBOUND"],
        )
    if not segment_id or segment_id not in {item["segment_id"] for item in segments}:
        return (
            "NEEDS_MULTI_TS_SEGMENT_SELECTION",
            "RUN_ONE_VALIDATION_PIPELINE_PER_SEGMENT",
            ["MULTI_TS_SEGMENT_ID_MISSING_OR_UNKNOWN"],
        )
    return None


def _result(
    status: str,
    next_action: str,
    reasons: list[str],
    source_paths: list[Path],
    output: Path | None,
    *,
    scientifically_validated_ts: bool = False,
    frequency_validation_passed: bool = False,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "document_kind": "ts_validation_pipeline_status",
        "status": status,
        "reason_codes": reasons,
        "next_action": next_action,
        "source_files": source_file_manifest(source_paths),
        "connectivity_required": False,
        "connectivity_validated": False,
        "validation_basis": "DIMER_CONVERGENCE_AND_VIBRATIONAL_FREQUENCY",
        "scientifically_validated_ts": scientifically_validated_ts,
        "frequency_validation_passed": frequency_validation_passed,
        "final_grade_requires_vfa_analyzer": False,
        "optional_vfa_grade": "NOT_EVALUATED",
        "submission_executor": "scripts.neb_agent.submission",
    }
    if output:
        write_json(output, payload)
    return payload
