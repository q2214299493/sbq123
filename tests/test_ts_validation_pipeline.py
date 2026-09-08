from __future__ import annotations

import json
from pathlib import Path

from scripts.artifact_io import sha256_file
from scripts.ts_validation.validation_pipeline import evaluate_validation_pipeline


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _dimer(path: Path, **updates: object) -> Path:
    payload = {
        "technically_converged": True,
        "normal_completion": True,
        "vasp_force_converged": True,
        "negative_curvature": True,
        "dimer_soft_gate_passed": True,
    }
    payload.update(updates)
    return _write(path, payload)


def _vfa(path: Path, **updates: object) -> Path:
    payload = {
        "normal_completion": True,
        "imaginary_frequency_count": 1,
        "principal_mode_index": 6,
        "principal_mode_assignment": "accepted",
        "principal_mode_reaction_atom_overlap": [45, 46],
        "frequency_threshold_status": "configured",
        "principal_mode_is_meaningful": True,
        "geometry_status": "pass",
    }
    payload.update(updates)
    return _write(path, payload)


def test_pipeline_blocks_before_frequency_when_dimer_hard_gate_fails(tmp_path: Path) -> None:
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(tmp_path / "dimer.json", negative_curvature=False)
    )
    assert result["status"] == "BLOCKED_DIMER_HARD_GATE"


def test_pipeline_requires_exactly_one_raw_imaginary_mode(tmp_path: Path) -> None:
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(tmp_path / "dimer.json"),
        vfa_analysis_path=_vfa(tmp_path / "vfa.json", imaginary_frequency_count=2),
    )
    assert result["status"] == "BLOCKED_HIGHER_ORDER_SADDLE_OR_SOFT_MODE_REVIEW"


def test_pipeline_reviews_unassigned_local_partial_hessian_mode(tmp_path: Path) -> None:
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(tmp_path / "dimer.json"),
        vfa_analysis_path=_vfa(
            tmp_path / "vfa.json", principal_mode_assignment="Needs confirmation"
        ),
    )
    assert result["status"] == "NEEDS_PRINCIPAL_MODE_ASSIGNMENT"
    assert result["next_action"] == "REVIEW_IMAGINARY_MODE_AGAINST_REACTION_CONTRACT"


def test_pipeline_expands_local_scope_when_mode_coupling_is_ambiguous(
    tmp_path: Path,
) -> None:
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(tmp_path / "dimer.json"),
        vfa_analysis_path=_vfa(
            tmp_path / "vfa.json",
            principal_mode_assignment="unresolved_local_surface_coupling",
        ),
    )
    assert result["status"] == "NEEDS_PRINCIPAL_MODE_ASSIGNMENT"
    assert result["next_action"] == "EXPAND_LOCAL_ACTIVE_SET_AND_REPEAT_FREQUENCY"
    assert "LOCAL_PARTIAL_HESSIAN_SCOPE_EXPANSION_REQUIRED" in result["reason_codes"]


def test_dimer_pipeline_accepts_after_frequency_validation(tmp_path: Path) -> None:
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(tmp_path / "dimer.json"),
        vfa_analysis_path=_vfa(tmp_path / "vfa.json"),
    )
    assert result["status"] == "TS_ACCEPTED"
    assert result["connectivity_required"] is False
    assert result["next_action"] == "RECORD_TS_RESULT"
    assert result["scientifically_validated_ts"] is True


def test_legacy_connectivity_report_does_not_gate_dimer(tmp_path: Path) -> None:
    report = _write(
        tmp_path / "connectivity.json",
        {"status": "FAIL", "reaction_connectivity": "FAIL"},
    )
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(tmp_path / "dimer.json"),
        vfa_analysis_path=_vfa(tmp_path / "vfa.json"),
        connectivity_report_path=report,
    )
    assert result["status"] == "TS_ACCEPTED"
    assert result["connectivity_validated"] is False
    assert result["scientifically_validated_ts"] is True


def test_frequency_only_soft_review_cannot_finalize_dimer(tmp_path: Path) -> None:
    review = _write(
        tmp_path / "review.json",
        {
            "status": "accepted",
            "decision": "allow_frequency_handoff",
        },
    )
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(
            tmp_path / "dimer.json", dimer_soft_gate_passed=False
        ),
        dimer_soft_review_path=review,
        vfa_analysis_path=_vfa(tmp_path / "vfa.json"),
    )
    assert result["status"] == "DIMER_FREQUENCY_COMPLETE_SOFT_REVIEW_REQUIRED"
    assert result["next_action"] == "REVIEW_DIMER_FORCE_AND_TORQUE_FOR_TS_VALIDATION"


def test_ts_validation_soft_review_is_reported_as_final_acceptance(
    tmp_path: Path,
) -> None:
    review = _write(
        tmp_path / "review.json",
        {
            "status": "accepted",
            "decision": "accept_for_ts_validation",
        },
    )
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(
            tmp_path / "dimer.json", dimer_soft_gate_passed=False
        ),
        dimer_soft_review_path=review,
        vfa_analysis_path=_vfa(
            tmp_path / "vfa.json", frequency_threshold_status="needs_configuration"
        ),
    )
    assert result["status"] == "TS_ACCEPTED"
    assert "DIMER_SOFT_WARNING_ACCEPTED_FOR_TS_VALIDATION" in result["reason_codes"]


def test_frequency_thresholds_do_not_block_dimer_ts_acceptance(
    tmp_path: Path,
) -> None:
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(tmp_path / "dimer.json"),
        vfa_analysis_path=_vfa(
            tmp_path / "vfa.json", frequency_threshold_status="needs_configuration"
        ),
    )
    assert result["status"] == "TS_ACCEPTED"
    assert result["connectivity_validated"] is False
    assert result["scientifically_validated_ts"] is True
    assert result["next_action"] == "RECORD_TS_RESULT"
    assert result["optional_vfa_grade"] == "NOT_EVALUATED"


def test_multiple_ts_candidates_require_a_converged_intermediate(tmp_path: Path) -> None:
    topology = _write(
        tmp_path / "topology.json",
        {
            "status": "accepted",
            "independent_ts_candidate_count": 2,
            "stable_intermediates": [],
        },
    )
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(tmp_path / "dimer.json"),
        path_topology_path=topology,
    )
    assert result["status"] == "NEEDS_STABLE_INTERMEDIATE_CONFIRMATION"


def test_multiple_ts_candidates_run_one_local_contract_per_segment(tmp_path: Path) -> None:
    topology = _write(
        tmp_path / "topology.json",
        {
            "status": "accepted",
            "independent_ts_candidate_count": 2,
            "stable_intermediates": [
                {"relaxation_status": "converged", "structure_sha256": "a" * 64}
            ],
        },
    )
    plan = _write(
        tmp_path / "plan.json",
        {
            "status": "accepted",
            "source_path_topology_sha256": sha256_file(topology),
            "segments": [
                {
                    "segment_id": "is_to_im",
                    "initial_endpoint_sha256": "1" * 64,
                    "final_endpoint_sha256": "2" * 64,
                    "ts_candidate_id": "ts1",
                    "reaction_contract_sha256": "3" * 64,
                },
                {
                    "segment_id": "im_to_fs",
                    "initial_endpoint_sha256": "2" * 64,
                    "final_endpoint_sha256": "4" * 64,
                    "ts_candidate_id": "ts2",
                    "reaction_contract_sha256": "5" * 64,
                },
            ],
        },
    )
    result = evaluate_validation_pipeline(
        dimer_analysis_path=_dimer(tmp_path / "dimer.json"),
        path_topology_path=topology,
        branch_plan_path=plan,
        segment_id="is_to_im",
    )
    assert result["status"] == "READY_FOR_VFA"
    assert "MULTI_TS_SEGMENT:is_to_im" in result["reason_codes"]
