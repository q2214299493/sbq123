from __future__ import annotations

import math
import sqlite3
from tests.registry_fixture_mutation import fixture_connection
from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object, sha256_file, sha256_text, write_json
from scripts.neb_agent.utils_structure import write_poscar
from scripts.ts_strategy_engine.dimer_analysis import analyze_dimer
from scripts.ts_strategy_engine.evidence import record_matched_static_barrier
from scripts.ts_strategy_engine.matched_static_evidence import barrier_values, matched_static_convention, matched_static_rows
from scripts.ts_validation.analyze_vfa import analyze_vfa
from scripts.ts_validation.prepare_vfa_from_ts_image import prepare_vfa_handoff
from scripts.ts_validation.validation_pipeline import evaluate_validation_pipeline
from test_ts_strategy_engine import authoritative_gate, barrier_validation, contract, database, successful_record
from test_ts_validation import _connectivity_structure


def bound_case(root: Path, *, soft_decision: str | None = None) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    dimer = root / "dimer"
    dimer.mkdir()
    chemistry = contract()
    for name in ("POSCAR", "CONTCAR"):
        write_poscar(dimer / name, _connectivity_structure(2.0))
    (dimer / "INCAR").write_text("EDIFFG=-0.02; EDIFF=1e-5; NELM=60; ICHAIN=2; DFNMin=0.01\n")
    torque = 0.02 if soft_decision else 0.01
    (dimer / "DIMCAR").write_text(f"1 0.01 {torque} -10 -0.5 0.1\n")
    (dimer / "OUTCAR").write_text("FORCES: max atom, RMS 0.01 0.001\nGeneral timing and accounting informations for this job\n")
    (dimer / "OSZICAR").write_text("RMM: 5 -10 -1e-7 -1e-7 100 1e-4\n1 F= -10 E0= -10 d E= -1e-7\n")
    (dimer / "MODECAR").write_text("0 0 0\n1 0 0\n-1 0 0\n")
    hashes = {key: chemistry[key] for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")}
    write_json(dimer / "dimer_handoff.json", {**hashes, "source_sha256": sha256_file(dimer / "POSCAR"),
                                            "path_generation_sha256": "4" * 64, "ts_candidate_id": "ts1"})
    stdout = "123 user DONE queue host exec dimer Jan 1 00:00\n"
    write_json(dimer / "scheduler_evidence.json", {
        "schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": "dimer",
        "scheduler": "LSF", "server_alias": "sunboquan-codex", "job_id": "123", "status": "DONE",
        "checked_at": "2026-01-01", "source_command": "bjobs -a 123",
        "query": {"argv": ["ssh", "sunboquan-codex", "bjobs", "-a", "123"], "returncode": 0,
                  "stdout": stdout, "stderr": "", "stdout_sha256": sha256_text(stdout)},
    })
    for name in ("mode_review.json", "final_mode_review.json"):
        write_json(dimer / name, {"status": "accepted", "reviewer": "test", "reviewed_at": "2026-01-01",
                                  "modecar_sha256": sha256_file(dimer / "MODECAR")})
    analysis = analyze_dimer(dimer)
    assert analysis["technically_converged"]
    soft = root / "soft_review.json" if soft_decision else None
    if soft:
        write_json(soft, {"status": "accepted", "decision": soft_decision, "reviewer": "test",
                         "reviewed_at": "2026-01-01", "saddle_analysis_sha256": sha256_file(dimer / "dimer_analysis.json"),
                         "source_structure_sha256": sha256_file(dimer / "CONTCAR"),
                         "acknowledged_warning_codes": analysis["dimer_soft_warnings"]})
    vfa = root / "vfa"
    prepare_vfa_handoff(dimer, vfa, [1, 2], chemistry, dimer / "dimer_analysis.json", False, soft)
    scope = load_json_object(vfa / "vfa_scope_review.json")
    scope.update(status="accepted_for_partial_hessian", reviewer="test", reviewed_at="2026-01-01")
    write_json(vfa / "vfa_scope_review.json", scope)
    (vfa / "OUTCAR").write_text("6 f/i= 15 THz 500 cm-1\n1 0 0 0 0 0 0\n2 0 0 0 0.7 0 0\n3 0 0 0 -0.7 0 0\nGeneral timing and accounting informations for this job\n")
    review = vfa / "vfa_review.json"
    write_json(review, {**hashes, "status": "accepted", "source_method": "dimer", "validation_calculation_id": "vfa",
                        "source_saddle_calculation_id": "dimer", "source_job_record_id": "123", "frequency_output_file_id": "frequency",
                        "mode_assignment": "accepted", "geometry_status": "pass", "reviewer": "test", "reviewed_at": "2026-01-01",
                        "vfa_handoff": "vfa_handoff.json", "vfa_handoff_sha256": sha256_file(vfa / "vfa_handoff.json")})
    analyze_vfa(vfa, chemistry, review)
    return {"dimer": dimer, "vfa": vfa, "contract": chemistry, "soft": soft}


def evaluate_case(case: dict, **overrides):
    kwargs = {"dimer_analysis_path": case["dimer"] / "dimer_analysis.json", "vfa_workdir": case["vfa"],
              "vfa_analysis_path": case["vfa"] / "vfa_analysis.json", "dimer_soft_review_path": case["soft"]}
    kwargs.update(overrides)
    return evaluate_validation_pipeline(**kwargs)


def assert_not_accepted(case: dict, **overrides):
    try:
        result = evaluate_case(case, **overrides)
    except (ValueError, OSError):
        return
    assert result["scientifically_validated_ts"] is False, result
    assert result["status"] != "TS_ACCEPTED"


def test_pipeline_accepts_current_matching_chain_without_optional_topology(tmp_path):
    result = evaluate_case(bound_case(tmp_path))
    assert result["status"] == "TS_ACCEPTED"
    assert result["scientifically_validated_ts"] is True
    assert result["connectivity_required"] is False
    assert result["optional_vfa_grade"] == "NOT_EVALUATED"


def test_pipeline_cannot_combine_independently_valid_dimer_and_vfa(tmp_path):
    first, second = bound_case(tmp_path / "first"), bound_case(tmp_path / "second")
    assert_not_accepted(first, vfa_workdir=second["vfa"], vfa_analysis_path=second["vfa"] / "vfa_analysis.json")


@pytest.mark.parametrize("key", ["contract_sha256", "atom_map_sha256", "compatibility_sha256", "saddle_analysis_sha256", "source_saddle_sha256"])
def test_pipeline_rejects_mismatched_vfa_identity(tmp_path, key):
    case = bound_case(tmp_path)
    path = case["vfa"] / "vfa_analysis.json"
    summary = load_json_object(path)
    summary[key] = "f" * 64
    write_json(path, summary)
    assert_not_accepted(case)


@pytest.mark.parametrize("owner,name", [("dimer", "CONTCAR"), ("dimer", "OUTCAR"), ("dimer", "dimer_handoff.json"),
                                       ("dimer", "final_mode_review.json"), ("vfa", "POSCAR"), ("vfa", "OUTCAR"),
                                       ("vfa", "vfa_handoff.json"), ("vfa", "vfa_scope_review.json"), ("vfa", "vfa_review.json")])
@pytest.mark.parametrize("damage", ["missing", "stale"])
def test_pipeline_rejects_missing_or_stale_chain_files(tmp_path, owner, name, damage):
    case = bound_case(tmp_path)
    path = case[owner] / name
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    assert_not_accepted(case)


@pytest.mark.parametrize("damage", ["missing", "stale", "wrong_object"])
def test_pipeline_checks_current_soft_review_even_after_frequency_completed(tmp_path, damage):
    case = bound_case(tmp_path, soft_decision="accept_for_ts_validation")
    if damage == "missing":
        case["soft"].unlink()
    elif damage == "stale":
        case["soft"].write_bytes(case["soft"].read_bytes() + b"\n")
    else:
        review = load_json_object(case["soft"])
        review["source_structure_sha256"] = "f" * 64
        write_json(case["soft"], review)
    assert_not_accepted(case)


def test_pipeline_rejects_explicitly_missing_topology(tmp_path):
    assert_not_accepted(bound_case(tmp_path), path_topology_path=tmp_path / "missing.json")


def test_pipeline_rejects_other_segment_contract(tmp_path):
    case = bound_case(tmp_path)
    topology = write_json(tmp_path / "topology.json", {"status": "accepted", "independent_ts_candidate_count": 2,
        "stable_intermediates": [{"relaxation_status": "converged", "structure_sha256": "a" * 64}]})
    segments = [{"segment_id": f"segment{i}", "initial_endpoint_sha256": "1" * 64, "final_endpoint_sha256": "2" * 64,
                 "ts_candidate_id": f"ts{i}", "reaction_contract_sha256": "f" * 64} for i in (1, 2)]
    plan = write_json(tmp_path / "plan.json", {"status": "accepted", "source_path_topology_sha256": sha256_file(topology), "segments": segments})
    assert_not_accepted(case, path_topology_path=topology, branch_plan_path=plan, segment_id="segment1")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), None, True, False])
def test_final_energy_and_barrier_reject_invalid_scalars(tmp_path, value):
    db = database(tmp_path / "test.sqlite3")
    with fixture_connection(db) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in matched_static_rows(connection, ("is_energy", "ts_energy", "fs_energy"))]
    rows[1]["numeric_value"] = value
    with pytest.raises(ValueError):
        matched_static_convention(rows)
    with pytest.raises(ValueError):
        barrier_values(rows)


def test_finite_energies_cannot_overflow_barrier_outputs():
    with pytest.raises(ValueError, match="finite"):
        barrier_values([{"numeric_value": x} for x in (-1e308, 1e308, 0)])


def test_negative_total_energies_and_original_negative_barrier_rule():
    assert barrier_values([{"numeric_value": x} for x in (-10, -9, -10.5)]) == {
        "forward_barrier_ev": 1.0, "reverse_barrier_ev": 1.5, "reaction_energy_ev": -0.5}
    with pytest.raises(ValueError, match="below an endpoint"):
        barrier_values([{"numeric_value": x} for x in (-10, -11, -10.5)])


@pytest.mark.parametrize("energies", [[0, float("inf"), 1], [0, float("nan"), 1], [-1e308, 1e308, 0]])
def test_formal_barrier_registration_cannot_accept_invalid_energy(tmp_path, energies):
    db = database(tmp_path / "test.sqlite3")
    barrier_id = "invalid_barrier"
    with fixture_connection(db) as connection:
        for result_id, energy in zip(("is_energy", "ts_energy", "fs_energy"), energies, strict=True):
            connection.execute("UPDATE results SET numeric_value=? WHERE result_id=?", ("NaN" if math.isnan(energy) else energy, result_id))
    gate, state = authoritative_gate(db, barrier_validation(barrier_set_id=barrier_id, reaction_id="invalid_reaction"))
    with pytest.raises(ValueError):
        record_matched_static_barrier(db, gate_decision=gate, gate_state_sha256=state, barrier_set_id=barrier_id,
            reaction_id="invalid_reaction", source_calculation_id="calc_ts", ts_validation_id="validation_a",
            initial_result_id="is_energy", ts_result_id="ts_energy", final_result_id="fs_energy",
            learning_record=successful_record(template_id="invalid_template", barrier_set_id=barrier_id))
    with fixture_connection(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ts_barriers WHERE barrier_set_id=?", (barrier_id,)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM ts_strategy_templates WHERE template_id='invalid_template'").fetchone()[0] == 0


@pytest.mark.parametrize("key", ["reviewer", "reviewed_at", "status"])
def test_pipeline_cannot_promote_reanalyzed_unapproved_review(tmp_path, key):
    case = bound_case(tmp_path)
    review_path = case["vfa"] / "vfa_review.json"
    review = load_json_object(review_path)
    review[key] = None
    write_json(review_path, review)
    analyze_vfa(case["vfa"], case["contract"], review_path)
    assert_not_accepted(case)


def test_pipeline_rejects_different_geometry_even_with_consistent_handoff_hashes(tmp_path):
    case = bound_case(tmp_path)
    vfa = case["vfa"]
    write_poscar(vfa / "POSCAR", _connectivity_structure(2.8))
    handoff = load_json_object(vfa / "vfa_handoff.json")
    handoff["frequency_poscar_sha256"] = sha256_file(vfa / "POSCAR")
    write_json(vfa / "vfa_handoff.json", handoff)
    for name in ("vfa_scope_review.json", "vfa_review.json"):
        review = load_json_object(vfa / name)
        review["vfa_handoff_sha256"] = sha256_file(vfa / "vfa_handoff.json")
        if name == "vfa_scope_review.json":
            review["frequency_poscar_sha256"] = sha256_file(vfa / "POSCAR")
        write_json(vfa / name, review)
    analyze_vfa(vfa, case["contract"], vfa / "vfa_review.json")
    assert_not_accepted(case)


@pytest.mark.parametrize("field", ["forward_barrier_ev", "reverse_barrier_ev", "reaction_energy_ev"])
def test_export_and_template_consumers_reject_nonfinite_stored_barriers(tmp_path, field):
    from scripts.registry_excel_promotion import _barrier_context
    from scripts.ts_strategy_engine.templates import load_templates

    db = database(tmp_path / "test.sqlite3")
    with fixture_connection(db) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(f"UPDATE ts_barriers SET {field}=? WHERE barrier_set_id='barrier_a'", (float("inf"),))
        with pytest.raises(ValueError, match="finite"):
            _barrier_context(connection, "barrier_a")
    assert not load_templates(db)[0]["evidence_valid"]



def test_pipeline_accepts_bound_local_segment_and_does_not_rewrite_sources(tmp_path):
    case = bound_case(tmp_path, soft_decision="accept_for_ts_validation")
    topology = write_json(tmp_path / "topology.json", {"status": "accepted", "independent_ts_candidate_count": 2,
        "stable_intermediates": [{"relaxation_status": "converged", "structure_sha256": "a" * 64}]})
    segments = [{"segment_id": f"segment{i}", "initial_endpoint_sha256": "1" * 64, "final_endpoint_sha256": "2" * 64,
                 "ts_candidate_id": f"ts{i}", "reaction_contract_sha256": case["contract"]["contract_sha256"] if i == 1 else "f" * 64}
                for i in (1, 2)]
    plan = write_json(tmp_path / "plan.json", {"status": "accepted", "source_path_topology_sha256": sha256_file(topology), "segments": segments})
    before = {str(path): sha256_file(path) for path in tmp_path.rglob("*") if path.is_file()}
    result = evaluate_case(case, path_topology_path=topology, branch_plan_path=plan, segment_id="segment1")
    assert result["status"] == "TS_ACCEPTED", result
    assert "MULTI_TS_SEGMENT:segment1" in result["reason_codes"]
    assert {str(path): sha256_file(path) for path in tmp_path.rglob("*") if path.is_file()} == before
    assert_not_accepted(case, path_topology_path=topology, branch_plan_path=plan, segment_id="segment2")


@pytest.mark.parametrize("damage", ["missing", "corrupt", "stale"])
def test_explicit_branch_plan_is_not_ignored_on_single_peak(tmp_path, damage):
    case = bound_case(tmp_path)
    topology = write_json(tmp_path / "topology.json", {"status": "accepted", "independent_ts_candidate_count": 1})
    plan = tmp_path / "plan.json"
    if damage == "corrupt":
        plan.write_text("not json")
    elif damage == "stale":
        write_json(plan, {"status": "accepted", "source_path_topology_sha256": "f" * 64})
    assert_not_accepted(case, path_topology_path=topology, branch_plan_path=plan)



def test_pipeline_bound_sources_survive_a_different_caller_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    case = bound_case(Path("relative_case"))
    case["dimer"] = case["dimer"].resolve()
    case["vfa"] = case["vfa"].resolve()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    result = evaluate_case(case)
    assert result["status"] == "TS_ACCEPTED", result
