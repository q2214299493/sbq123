import sqlite3

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.ts_strategy_engine.evidence import record_matched_static_barrier, record_ts_validation
from scripts.ts_validation.analyze_vfa import analyze_vfa
from tests.registry_fixture_mutation import fixture_connection
from test_b21_scientific_acceptance import assert_not_accepted, bound_case, evaluate_case
from test_scientific_claim_authority import claim_gate
from test_ts_strategy_engine import barrier_validation, database, successful_record


@pytest.mark.parametrize("accepted_energy", [True, False])
def test_reviewed_dimer_grade_a_registers_and_keeps_final_energy_gate(tmp_path, accepted_energy):
    case = bound_case(tmp_path / "dimer_science")
    review_path = case["vfa"] / "vfa_review.json"
    review = load_json_object(review_path)
    review.update(
        validation_calculation_id="calc_vfa",
        source_saddle_calculation_id="calc_ts",
        source_job_record_id="job_ts_source",
        frequency_output_file_id="vfa_outcar",
    )
    write_json(review_path, review)
    payload = analyze_vfa(case["vfa"], case["contract"], review_path)
    assert payload["frequency_threshold_status"] != "configured"
    assert payload["grade"] == "A"
    assert payload["kinetic_eligible"] is True
    assert payload["dimer_technical_acceptance"] is True
    pipeline = evaluate_case(case)
    assert pipeline["status"] == "TS_ACCEPTED"
    assert pipeline["optional_vfa_grade"] == payload["grade"]
    assert pipeline["kinetic_eligible"] == payload["kinetic_eligible"]

    db = database(tmp_path / "registry.sqlite3", compatibility=case["contract"]["compatibility"])
    frequency = case["vfa"] / "OUTCAR"
    with fixture_connection(db) as connection:
        connection.execute("UPDATE jobs SET scheduler_job_id='123' WHERE job_record_id='job_ts_source'")
        connection.execute(
            "UPDATE files SET sha256=?, local_path=?, byte_size=? WHERE file_id='vfa_outcar'",
            (sha256_file(frequency), str(frequency), frequency.stat().st_size),
        )
    payload = {**payload, **barrier_validation()}
    analysis_path = write_json(case["vfa"] / "vfa_analysis.json", payload)
    gate, decision = claim_gate(analysis_path)
    record_ts_validation(
        db, "validation_a", payload, gate_decision=gate, gate_state_sha256=decision["state_sha256"],
    )
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT grade, kinetic_eligible FROM ts_validations").fetchall() == [("A", 1)]
    if not accepted_energy:
        with fixture_connection(db) as connection:
            connection.execute("UPDATE results SET validation_status='needs_review' WHERE result_id='ts_energy'")
    arguments = dict(
        gate_decision=gate, gate_state_sha256=decision["state_sha256"], barrier_set_id="barrier_a",
        reaction_id="co_split", source_calculation_id="calc_ts", ts_validation_id="validation_a",
        initial_result_id="is_energy", ts_result_id="ts_energy", final_result_id="fs_energy",
        learning_record=successful_record(),
    )
    if accepted_energy:
        result = record_matched_static_barrier(db, **arguments)
        assert result["forward_barrier_ev"] == 1.0
        assert result["reverse_barrier_ev"] == 1.5
    else:
        with pytest.raises(ValueError, match="accepted validation status"):
            record_matched_static_barrier(db, **arguments)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ts_barriers").fetchone()[0] == int(accepted_energy)


@pytest.mark.parametrize("damage", [
    "second_mode", "incomplete", "unassigned", "unreviewed", "frequency_only", "stale_review", "below_threshold",
])
def test_dimer_single_mode_review_cannot_waive_required_evidence(tmp_path, damage):
    case = bound_case(
        tmp_path / "science", soft_decision="allow_frequency_handoff" if damage == "frequency_only" else None,
    )
    review_path = case["vfa"] / "vfa_review.json"
    frequency = case["vfa"] / "OUTCAR"
    policy = None
    if damage == "second_mode":
        frequency.write_text(frequency.read_text() + "\n7 f/i= 3 THz 100 cm-1\n")
    elif damage == "incomplete":
        frequency.write_text(frequency.read_text().replace("General timing and accounting informations for this job", ""))
    elif damage in {"unassigned", "unreviewed"}:
        review = load_json_object(review_path)
        review["mode_assignment" if damage == "unassigned" else "status"] = "Needs confirmation"
        write_json(review_path, review)
    elif damage == "stale_review":
        review_path.write_bytes(review_path.read_bytes() + b"\n")
    elif damage == "below_threshold":
        policy = {"meaningful_imaginary_frequency_min_cm1": 600.0, "additional_soft_mode_abs_max_cm1": 30.0}
    if damage != "stale_review":
        payload = analyze_vfa(case["vfa"], case["contract"], review_path, policy)
        assert payload["grade"] != "A"
        assert payload["kinetic_eligible"] is False
    assert_not_accepted(case)
    _, decision = claim_gate(case["vfa"] / "vfa_analysis.json")
    assert "APPROVE_TS_CANDIDATE" not in decision["ALLOWED_ACTIONS"]


@pytest.mark.parametrize("policy", [
    {},
    {"meaningful_imaginary_frequency_min_cm1": None, "additional_soft_mode_abs_max_cm1": None},
])
def test_reviewed_single_dimer_mode_allows_both_frequency_thresholds_unset(tmp_path, policy):
    case = bound_case(tmp_path / "science")
    payload = analyze_vfa(case["vfa"], case["contract"], case["vfa"] / "vfa_review.json", policy)
    assert payload["grade"] == "A"
    assert payload["kinetic_eligible"] is True
    assert evaluate_case(case)["status"] == "TS_ACCEPTED"


@pytest.mark.parametrize("policy", [
    pytest.param({"meaningful_imaginary_frequency_min_cm1": 600.0}, id="meaningful_only"),
    pytest.param({"additional_soft_mode_abs_max_cm1": 30.0}, id="soft_only"),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": 600.0, "additional_soft_mode_abs_max_cm1": None}, id="soft_null",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": None, "additional_soft_mode_abs_max_cm1": 30.0}, id="meaningful_null",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": 0, "additional_soft_mode_abs_max_cm1": 30.0}, id="zero",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": 600.0, "additional_soft_mode_abs_max_cm1": -1}, id="negative",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": True, "additional_soft_mode_abs_max_cm1": 30.0}, id="boolean_meaningful",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": 600.0, "additional_soft_mode_abs_max_cm1": False}, id="boolean_soft",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": "600", "additional_soft_mode_abs_max_cm1": 30.0}, id="string_meaningful",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": 600.0, "additional_soft_mode_abs_max_cm1": "30"}, id="string_soft",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": float("inf"), "additional_soft_mode_abs_max_cm1": 30.0}, id="infinite",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": 600.0, "additional_soft_mode_abs_max_cm1": float("nan")}, id="nan",
    ),
    pytest.param(
        {"meaningful_imaginary_frequency_min_cm1": 10**400, "additional_soft_mode_abs_max_cm1": 30.0}, id="overflowing_integer",
    ),
])
def test_invalid_frequency_thresholds_cannot_reuse_reviewed_dimer_acceptance(tmp_path, policy):
    case = bound_case(tmp_path / "science")
    with pytest.raises(ValueError, match="frequency thresholds"):
        analyze_vfa(case["vfa"], case["contract"], case["vfa"] / "vfa_review.json", policy, write_output=False)
    analysis_path = case["vfa"] / "vfa_analysis.json"
    previous = load_json_object(analysis_path)
    assert previous["grade"] == "A"
    write_json(analysis_path, {**previous, "frequency_policy": policy, "frequency_policy_is_default": False})
    assert_not_accepted(case)
    _, decision = claim_gate(analysis_path)
    assert "APPROVE_TS_CANDIDATE" not in decision["ALLOWED_ACTIONS"]
