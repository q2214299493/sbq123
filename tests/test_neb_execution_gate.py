from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.ts_strategy_engine.execution_gate_cli import build_decision


THRESHOLDS = {
    "high_force_warning_threshold_eVA": 1.5,
    "min_ionic_steps_for_force_warning": 5,
    "persistent_high_force_failure_min_ionic_steps": 10,
}


def analysis(**updates: object) -> dict:
    payload = {
        "status": "ANALYZED",
        "path_binding_valid": True,
        "image_sequence_complete": True,
        "scf_failure": False,
        "internal_minimum_warning": False,
        "internal_maximum": True,
        "technically_converged": False,
        "images": [
            {"image": "00"},
            {
                "image": "01",
                "ionic_steps": 5,
                "final_neb_force_eVA": 0.2,
                "neb_force_trend": "decreasing",
            },
            {"image": "02"},
        ],
    }
    payload.update(updates)
    return payload


def test_electronic_failure_has_priority_over_underresolved_path() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(scf_persistent_failure_images=["01"]),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        path_quality={
            "PATH_QUALITY_STATUS": "UNDERRESOLVED_REACTION_COORDINATE",
            "REASON_CODES": ["B_large_reaction_coordinate_gap"],
        },
    )
    assert decision["DECISION"] == "STOP_ELECTRONIC_FAILURE"
    assert decision["ALLOWED_ACTIONS"] == []
    assert decision["CI_NEB_ALLOWED"] is False
    assert decision["DIMER_ALLOWED"] is False
    assert decision["TS_CLAIM_ALLOWED"] is False


def test_electronic_failure_can_only_submit_a_preflighted_diagnostic() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(scf_persistent_failure_images=["01"]),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        preflight={"kind": "diagnostic_static", "passed": True, "bundle_sha256": "a" * 64},
    )
    assert decision["ALLOWED_ACTIONS"] == ["SUBMIT_DIAGNOSTIC_VASP"]
    assert decision["SUBMISSION_ALLOWED"] is True


def test_magnetic_continuity_warning_does_not_block_ordinary_neb_submission() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(
            status="NO_OUTPUT",
            magnetic_continuity={
                "rule": "MAGNETIC_CONTINUITY_RULE",
                "severity": "SOFT_WARNING",
                "warning_threshold_muB": 2.0,
                "warnings": [{"left": "05", "right": "06", "delta_muB": 12.0}],
                "action": "CHECK_MAGNETIC_STATE_CONTINUITY",
                "stops_current_job": False,
                "blocks_ordinary_no_climb_neb": False,
                "proves_magnetic_state_switch": False,
            },
        ),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        preflight={"kind": "ordinary_neb", "passed": True, "bundle_sha256": "a" * 64},
    )
    assert decision["DECISION"] == "READY_FOR_ORDINARY_NEB_SUBMISSION"
    assert decision["REASON_CODES"] == []
    assert decision["ALLOWED_ACTIONS"] == ["SUBMIT_VASP"]
    assert decision["SUBMISSION_ALLOWED"] is True


def test_passed_electronic_remediation_exposes_next_path_failure() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(
            scf_persistent_failure_images=["01"],
            electronic_remediation_passed=True,
        ),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        path_quality={
            "PATH_QUALITY_STATUS": "UNDERRESOLVED_REACTION_COORDINATE",
            "REASON_CODES": ["B_large_reaction_coordinate_gap"],
        },
    )
    assert decision["DECISION"] == "STOP_UNDERRESOLVED_PATH"
    assert decision["ALLOWED_ACTIONS"] == ["REBUILD_PATH"]


def test_inline_evidence_cannot_authorize_stopping() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(scf_failure=True),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        scheduler={"scheduler": "LSF", "job_id": "123", "status": "RUN"},
    )
    assert decision["DECISION"] == "CONTINUE_NO_CLIMB_NEB"
    assert "STOP_JOB" not in decision["ALLOWED_ACTIONS"]


def test_unverified_quality_electronic_flag_cannot_trigger_hard_stop() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        path_quality={"PATH_QUALITY_STATUS": "ELECTRONIC_FAILURE"},
        scheduler={"scheduler": "LSF", "job_id": "123", "status": "RUN"},
    )
    assert decision["DECISION"] == "CONTINUE_NO_CLIMB_NEB"
    assert decision["ALLOWED_ACTIONS"] == ["CONTINUE_JOB"]


def test_file_bound_hard_failure_can_authorize_exact_running_job(tmp_path: Path) -> None:
    geometry = tmp_path / "geometry.json"
    analysis_path = tmp_path / "analysis.json"
    thresholds = tmp_path / "thresholds.yaml"
    scheduler = tmp_path / "scheduler.json"
    request = tmp_path / "request.json"
    output = tmp_path / "decision.json"
    raw_analysis = tmp_path / "OUTCAR"
    raw_analysis.write_text("persistent electronic failure", encoding="ascii")
    geometry.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    analysis_path.write_text(
        json.dumps(
            analysis(
                schema_version=1,
                document_kind="neb_output_analysis",
                producer="scripts.neb_agent.analyze_neb_outputs",
                source_files=[
                    {
                        "path": str(raw_analysis),
                        "sha256": hashlib.sha256(raw_analysis.read_bytes()).hexdigest(),
                    }
                ],
                scf_persistent_failure_images=["01"],
            )
        ),
        encoding="utf-8",
    )
    thresholds.write_text(yaml.safe_dump(THRESHOLDS), encoding="utf-8")
    scheduler_stdout = (
        "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
        "123 user RUN queue host exec neb Jul 24 00:00\n"
    )
    scheduler.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "scheduler_job_evidence",
                "stage": "neb_pilot",
                "scheduler": "LSF",
                "server_alias": "sunboquan-codex",
                "job_id": "123",
                "status": "RUN",
                "checked_at": "2026-07-24T00:00:00Z",
                "source_command": "ssh sunboquan-codex bjobs -a 123",
                "query": {
                    "argv": ["ssh", "sunboquan-codex", "bjobs", "-a", "123"],
                    "returncode": 0,
                    "stdout": scheduler_stdout,
                    "stderr": "",
                    "stdout_sha256": hashlib.sha256(
                        scheduler_stdout.encode()
                    ).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    request.write_text(
        json.dumps(
            {
                "geometry_file": geometry.name,
                "analysis_file": analysis_path.name,
                "thresholds_file": thresholds.name,
                "scheduler_file": scheduler.name,
                "climb": False,
                "path_reviewed": True,
            }
        ),
        encoding="utf-8",
    )
    decision = build_decision(request, output)
    assert decision["ALLOWED_ACTIONS"] == ["STOP_JOB"]
    require_action(output, "STOP_JOB", decision["state_sha256"])
    analysis_path.write_text(json.dumps(analysis()), encoding="utf-8")
    with pytest.raises(ValueError, match="authority fields"):
        require_action(output, "STOP_JOB", decision["state_sha256"])


def test_file_bound_user_request_can_cancel_exact_pending_job(tmp_path: Path) -> None:
    geometry = tmp_path / "geometry.json"
    analysis_path = tmp_path / "analysis.json"
    thresholds = tmp_path / "thresholds.yaml"
    scheduler = tmp_path / "scheduler.json"
    authorization = tmp_path / "authorization.json"
    request = tmp_path / "request.json"
    output = tmp_path / "decision.json"
    geometry.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    analysis_path.write_text(
        json.dumps(analysis(status="NO_OUTPUT", images=[])), encoding="utf-8"
    )
    thresholds.write_text(yaml.safe_dump(THRESHOLDS), encoding="utf-8")
    scheduler_stdout = (
        "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
        "123 user PEND queue host - neb Jul 27 00:00\n"
    )
    scheduler.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "scheduler_job_evidence",
                "stage": "neb_pilot",
                "scheduler": "LSF",
                "server_alias": "sunboquan-codex",
                "job_id": "123",
                "status": "PEND",
                "checked_at": "2026-07-27T00:00:00Z",
                "source_command": "ssh sunboquan-codex bjobs -a 123",
                "query": {
                    "argv": ["ssh", "sunboquan-codex", "bjobs", "-a", "123"],
                    "returncode": 0,
                    "stdout": scheduler_stdout,
                    "stderr": "",
                    "stdout_sha256": hashlib.sha256(
                        scheduler_stdout.encode()
                    ).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    authorization.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "user_execution_authorization",
                "action": "STOP_JOB",
                "job_id": "123",
                "allowed_scheduler_statuses": ["PEND", "RUN"],
                "authorized_at": "2026-07-27T00:01:00+08:00",
                "source": "explicit user instruction",
            }
        ),
        encoding="utf-8",
    )
    request.write_text(
        json.dumps(
            {
                "geometry_file": geometry.name,
                "analysis_file": analysis_path.name,
                "thresholds_file": thresholds.name,
                "scheduler_file": scheduler.name,
                "authorization_file": authorization.name,
                "climb": False,
                "path_reviewed": True,
            }
        ),
        encoding="utf-8",
    )
    decision = build_decision(request, output)
    assert decision["DECISION"] == "STOP_USER_REQUESTED"
    assert decision["ALLOWED_ACTIONS"] == ["STOP_JOB"]
    require_action(output, "STOP_JOB", decision["state_sha256"])


def test_transient_nelm_high_force_and_energy_dip_are_warnings_only() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(
            scf_warning=True,
            high_force_warnings=[{"image": "01"}],
            internal_minimum_warning=True,
        ),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        scheduler={"scheduler": "LSF", "job_id": "123", "status": "RUN"},
    )
    assert decision["DECISION"] == "CONTINUE_NO_CLIMB_NEB"
    assert decision["ALLOWED_ACTIONS"] == ["CONTINUE_JOB"]
    assert {
        "TRANSIENT_SCF_EXHAUSTION_WARNING",
        "EARLY_OR_NONPERSISTENT_HIGH_FORCE_WARNING",
        "TRANSIENT_INTERNAL_MINIMUM_WARNING",
    } <= set(decision["REASON_CODES"])


def test_persistent_high_force_without_decreasing_trend_blocks_path() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(persistent_high_force_failure_images=["01"]),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        scheduler={"scheduler": "LSF", "job_id": "123", "status": "RUN"},
    )
    assert decision["DECISION"] == "STOP_PATH_FAILURE"
    assert decision["ALLOWED_ACTIONS"] == ["REBUILD_PATH"]
    assert decision["REASON_CODES"] == [
        "PERSISTENT_HIGH_NEB_FORCE_NO_DECREASING_TREND:01"
    ]


def test_high_force_with_magnetic_discontinuity_blocks_path() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(
            high_force_observations=[{"image": "05", "force_eVA": 1.7}],
            magnetic_continuity={
                "warnings": [{"left": "05", "right": "06", "delta_muB": 3.0}]
            },
        ),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        scheduler={"scheduler": "LSF", "job_id": "123", "status": "RUN"},
    )
    assert decision["DECISION"] == "STOP_PATH_FAILURE"
    assert decision["REASON_CODES"] == [
        "HIGH_NEB_FORCE_WITH_MAGNETIC_DISCONTINUITY:05:06"
    ]


def test_continue_requires_current_running_scheduler_evidence() -> None:
    decision = decide_execution(
        {"status": "PASS"}, analysis(), THRESHOLDS,
        climb=False, path_reviewed=True,
    )
    assert decision["DECISION"] == "NEEDS_CURRENT_SCHEDULER_EVIDENCE"
    assert decision["ALLOWED_ACTIONS"] == []


def test_missing_path_binding_is_unresolved_not_a_stop() -> None:
    incomplete = analysis()
    incomplete.pop("path_binding_valid")
    decision = decide_execution(
        {"status": "PASS"},
        incomplete,
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        scheduler={"scheduler": "LSF", "job_id": "123", "status": "RUN"},
    )
    assert decision["DECISION"] == "NEEDS_PATH_BINDING_EVIDENCE"
    assert decision["ALLOWED_ACTIONS"] == []


def test_submission_requires_current_gate_decision(tmp_path: Path) -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(status="NO_OUTPUT", images=[]),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        preflight={"kind": "ordinary_neb", "passed": True, "bundle_sha256": "a" * 64},
    )
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(decision), encoding="utf-8")
    require_action(path, "SUBMIT_VASP", decision["state_sha256"])
    with pytest.raises(ValueError, match="stale"):
        require_action(path, "SUBMIT_VASP", "b" * 64)
    with pytest.raises(PermissionError):
        require_action(path, "START_DIMER", decision["state_sha256"])
    decision["schema_version"] = 1
    path.write_text(json.dumps(decision), encoding="utf-8")
    with pytest.raises(ValueError, match="complete authoritative"):
        require_action(path, "SUBMIT_VASP", decision["state_sha256"])


def test_short_neb_pilot_is_diagnostic_only() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(status="NO_OUTPUT", images=[]),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        preflight={"kind": "neb_pilot", "passed": True, "bundle_sha256": "a" * 64},
    )
    assert decision["ALLOWED_ACTIONS"] == ["SUBMIT_DIAGNOSTIC_VASP"]


def test_ordinary_neb_can_select_ci_neb_or_dimer() -> None:
    quality = {"PATH_QUALITY_STATUS": "CI_NEB_READINESS_EVIDENCE"}
    blocked = decide_execution(
        {"status": "PASS"}, analysis(), THRESHOLDS, climb=False,
        path_reviewed=True, path_quality=quality,
    )
    assert blocked["DECISION"] == "READY_TO_SELECT_CI_NEB_OR_DIMER"
    assert blocked["ALLOWED_ACTIONS"] == ["PREPARE_DIMER_HANDOFF"]
    ready = decide_execution(
        {"status": "PASS"}, analysis(), THRESHOLDS, climb=False,
        path_reviewed=True, path_quality=quality,
        preflight={"kind": "ci_neb", "passed": True},
    )
    assert ready["ALLOWED_ACTIONS"] == ["ENABLE_CI_NEB", "PREPARE_DIMER_HANDOFF"]
    assert ready["SUBMISSION_ALLOWED"] is True


def test_no_climb_parent_can_prepare_dimer_without_full_neb_convergence() -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(technically_converged=False),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
        path_quality={"PATH_QUALITY_STATUS": "PARENT_NEB_INCOMPLETE"},
        authorization={"action": "PREPARE_DIMER_HANDOFF"},
    )
    assert decision["DECISION"] == "READY_TO_PREPARE_DIMER_HANDOFF"
    assert decision["ALLOWED_ACTIONS"] == ["PREPARE_DIMER_HANDOFF"]


def test_coarse_neb_stable_other_images_and_stalled_peak_recommends_dimer() -> None:
    images = [
        {"image": "00"},
        {
            "image": "01",
            "ionic_steps": 60,
            "final_neb_force_eVA": 0.20,
            "neb_force_trend": "decreasing",
            "reached_required_accuracy": False,
        },
        {
            "image": "02",
            "ionic_steps": 80,
            "final_neb_force_eVA": 0.85,
            "neb_force_trend": "oscillating",
            "reached_required_accuracy": False,
        },
        {
            "image": "03",
            "ionic_steps": 60,
            "final_neb_force_eVA": 0.25,
            "neb_force_trend": "plateau",
            "reached_required_accuracy": False,
        },
        {"image": "04"},
    ]
    decision = decide_execution(
        {"status": "PASS"},
        analysis(maximum_image="02", images=images),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
    )
    assert decision["DECISION"] == "READY_TO_PREPARE_DIMER_HANDOFF"
    assert "COARSE_NEB_PEAK_STALL_DIMER_RECOMMENDED" in decision["REASON_CODES"]
    assert decision["ALLOWED_ACTIONS"] == ["PREPARE_DIMER_HANDOFF"]


def test_dimer_requires_its_own_preflight() -> None:
    quality = {"PATH_QUALITY_STATUS": "CI_NEB_READINESS_EVIDENCE"}
    preparation = decide_execution(
        {"status": "PASS"}, analysis(technically_converged=False), THRESHOLDS,
        climb=True, path_reviewed=True, path_quality=quality,
    )
    assert preparation["ALLOWED_ACTIONS"] == ["PREPARE_DIMER_HANDOFF"]
    assert preparation["DIMER_ALLOWED"] is False
    ready = decide_execution(
        {"status": "PASS"}, analysis(technically_converged=False), THRESHOLDS,
        climb=True, path_reviewed=True, path_quality=quality,
        preflight={"kind": "dimer", "passed": True, "dimer_hard_gate_passed": True},
    )
    assert ready["ALLOWED_ACTIONS"] == ["START_DIMER"]
    assert ready["SUBMISSION_ALLOWED"] is True

    blocked = decide_execution(
        {"status": "PASS"}, analysis(technically_converged=True), THRESHOLDS,
        climb=True, path_reviewed=True, path_quality=quality,
        preflight={"kind": "dimer", "passed": True, "dimer_hard_gate_passed": False},
    )
    assert blocked["DECISION"] == "DIMER_HARD_GATE_FAILED"
    assert blocked["ALLOWED_ACTIONS"] == []


def test_vfa_requires_its_own_passed_hard_gate() -> None:
    ready = decide_execution(
        {},
        {},
        THRESHOLDS,
        climb=False,
        path_reviewed=False,
        preflight={"kind": "vfa", "passed": True, "vfa_hard_gate_passed": True},
    )
    assert ready["DECISION"] == "READY_FOR_DIAGNOSTIC_VFA"
    assert ready["ALLOWED_ACTIONS"] == ["START_VFA"]
    assert ready["VFA_ALLOWED"] is True
    assert ready["TS_CLAIM_ALLOWED"] is False

    blocked = decide_execution(
        {},
        {},
        THRESHOLDS,
        climb=False,
        path_reviewed=False,
        preflight={"kind": "vfa", "passed": False, "vfa_hard_gate_passed": False},
    )
    assert blocked["DECISION"] == "VFA_HARD_GATE_FAILED"
    assert blocked["ALLOWED_ACTIONS"] == []


def test_tampered_action_cannot_bypass_authoritative_gate(tmp_path: Path) -> None:
    decision = decide_execution(
        {"status": "PASS"},
        analysis(scf_failure=True),
        THRESHOLDS,
        climb=False,
        path_reviewed=True,
    )
    decision["ALLOWED_ACTIONS"] = ["SUBMIT_VASP"]
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(decision), encoding="utf-8")
    with pytest.raises(ValueError, match="do not match"):
        require_action(path, "SUBMIT_VASP", decision["state_sha256"])
