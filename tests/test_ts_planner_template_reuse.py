"""Synthetic real-registry/template validation tests; no physical calculation or model."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
import subprocess

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.ts_strategy_engine import learning_cli, template_reference
from scripts.ts_strategy_engine.decision_planner import plan_next
from scripts.ts_strategy_engine.execution_gate import decide_execution
from scripts.ts_strategy_engine.learning_evidence import attempt_input_hashes, bind_files, input_key
from scripts.ts_strategy_engine.learning_store import get_event, history_token
from scripts.ts_strategy_engine.templates import load_templates, record_template
from tests.registry_fixture_mutation import fixture_connection
from tests.test_ts_decision_planner import add_history, synthetic_trial, update_trial
from tests.test_ts_strategy_engine import database as scientific_database, raw_contract, successful_record


def trial(tmp_path, **options):
    # This existing fixture records Grade A via the actual gate/validation/barrier
    # path, including atomic template registration. Never inject evidence_valid.
    tmp_path.mkdir(parents=True, exist_ok=True)
    scientific_database(tmp_path / "synthetic.sqlite3")
    database, request = synthetic_trial(tmp_path, **options)
    assert load_templates(database)[0]["evidence_valid"] is True
    return database, request


def with_templates(database, request, expected=None):
    digest = expected or template_reference.template_snapshot(database)["snapshot_sha256"]
    return plan_next(database, request, sha256_file(request), use_templates=True, expected_template_snapshot_sha256=digest)


def rebind_contract(request_path, contract):
    spec = load_json_object(request_path)
    path = Path(spec["inputs"]["contract"]["path"])
    write_json(path, contract)
    spec["inputs"]["contract"]["sha256"] = sha256_file(path)
    key = input_key(spec["kind"], attempt_input_hashes(spec["kind"], spec["inputs"]))
    assessment_path = Path(spec["assessment"]["path"])
    assessment = load_json_object(assessment_path)
    assessment["input_key"] = key
    raw_path = Path(assessment["evidence"][0]["path"])
    raw = load_json_object(raw_path)
    raw["input_key"] = key
    write_json(raw_path, raw)
    for item in assessment["evidence"]:
        item["sha256"] = sha256_file(raw_path)
    write_json(assessment_path, assessment)
    spec["assessment"]["sha256"] = sha256_file(assessment_path)
    write_json(request_path, spec)


def test_default_never_reads_templates_and_empty_reference_falls_back(tmp_path, monkeypatch):
    database, request = synthetic_trial(tmp_path)
    expected = template_reference.template_snapshot(database)["snapshot_sha256"]
    original = template_reference.templates.load_templates
    def forbidden(*_args, **_kwargs):
        pytest.fail("disabled reference must not read templates")
    monkeypatch.setattr(template_reference.templates, "load_templates", forbidden)
    legacy = plan_next(database, request, sha256_file(request))
    assert "template_reference" not in legacy
    monkeypatch.setattr(template_reference.templates, "load_templates", original)
    enabled = with_templates(database, request, expected)
    assert enabled["composed_strategy"] == legacy["composed_strategy"]
    assert enabled["template_reference"]["templates"] == []
    assert enabled["template_reference"]["selection_status"] == "NO_QUALIFIED_MATCH_RULE_FALLBACK"


def test_real_registered_success_changes_composition_not_current_variant(tmp_path):
    database, request = trial(tmp_path)
    before = sha256_file(database)
    spec = load_json_object(request)
    variant = copy.deepcopy(get_event(database, "variant", spec["variant_id"]))
    legacy = plan_next(database, request, sha256_file(request))
    enabled = with_templates(database, request)
    strategy = enabled["composed_strategy"]
    assert legacy["composed_strategy"]["strategy_source"] == "rule_based"
    assert strategy["strategy_source"] == "template_transfer"
    assert strategy["waypoint_strategy"] == successful_record()["waypoint_strategy"]
    assert strategy["waypoint_strategy"] != legacy["composed_strategy"]["waypoint_strategy"]
    assert strategy["neb_settings"]["sequence"] == ["ordinary_neb", "ci_neb"]
    assert "initial_images" not in strategy["neb_settings"]
    assert enabled["current_strategy_settings"] == variant["settings"] == legacy["current_strategy_settings"]
    assert get_event(database, "variant", spec["variant_id"]) == variant
    assert load_json_object(request) == spec and sha256_file(database) == before
    reference = enabled["template_reference"]
    assert reference["selected_template_id"] == "fe110_co_split_grade_a"
    row = reference["templates"][0]
    assert row["source_calculation_id"] == "calc_ts" and row["ts_validation_id"] == "validation_a"
    assert row["registered_validation"]["evidence_grade"] == "A"
    assert row["strategy_transferable"] and row["result_transferable"]
    assert reference["scientific_results_imported"] is False
    assert reference["physical_source_files_reverified"] is False
    serialized = json.dumps(enabled)
    assert "evidence_barrier_ev" not in serialized and "forward_barrier_ev" not in serialized
    assert reference["ranking_kind"].startswith("existing_template_similarity")


@pytest.mark.parametrize("damage", ["grade", "file", "barrier", "nontransferable"])
def test_invalid_registered_evidence_or_unsafe_strategy_never_transfers(tmp_path, damage):
    database, request = trial(tmp_path)
    with fixture_connection(database) as connection:
        if damage == "grade":
            connection.execute("UPDATE ts_validations SET grade='B',kinetic_eligible=0 WHERE ts_validation_id='validation_a'")
        elif damage == "file":
            connection.execute("UPDATE files SET existence_status='missing' WHERE file_id='vfa_outcar'")
        elif damage == "barrier":
            connection.execute("UPDATE ts_barriers SET validation_status='rejected' WHERE barrier_set_id='barrier_a'")
        else:
            connection.execute("UPDATE ts_strategy_templates SET neb_settings_json=?", (json.dumps({"initial_images": 99}),))
    result = with_templates(database, request)
    assert result["composed_strategy"]["strategy_source"] == "rule_based"
    row = result["template_reference"]["templates"][0]
    assert not row["selected"] and not row["strategy_transferable"] and row["reasons"]
    assert "99" not in json.dumps(result["composed_strategy"])


def test_failure_experience_cannot_be_selected_as_success(tmp_path):
    database, request = trial(tmp_path)
    with fixture_connection(database) as connection:
        connection.execute("DELETE FROM ts_strategy_templates")
    record_template(database, successful_record(template_id="failed-experience", outcome="failure", validation_grade="Ungraded",
                    failure_cases=["synthetic optimizer failure"], correction_strategy="review optimizer and path"))
    result = with_templates(database, request)
    assert result["composed_strategy"]["strategy_source"] == "rule_based"
    assert result["template_reference"]["selected_template_id"] is None
    assert "failure_experience_not_success" in result["template_reference"]["templates"][0]["reasons"]


@pytest.mark.parametrize("query", ["missing_chemistry", "other_event", "other_branch", "different_endpoint_ids"])
def test_existing_matching_semantics_and_nontransferable_results(tmp_path, query):
    database, request = trial(tmp_path)
    contract = raw_contract()
    if query == "missing_chemistry":
        contract.pop("atom_symbols")
    elif query == "other_event":
        contract["broken_bonds"] = [[0, 2]]
    elif query == "other_branch":
        contract["compatibility"]["branch"] = "synthetic_other_compatibility_branch"
    else:
        contract["endpoints"]["initial"]["structure_file_id"] = "synthetic_other_IS"
    rebind_contract(request, contract)
    result = with_templates(database, request)
    reference = result["template_reference"]
    match = reference["templates"][0]
    if query in {"missing_chemistry", "other_event"}:
        assert match["chemical_event_equivalent"] is False
        assert match["strategy_transferable"] is False
        assert result["composed_strategy"]["strategy_source"] == "rule_based"
        assert match["reasons"]
    else:
        assert match["strategy_transferable"] is True and match["result_transferable"] is False
        assert result["composed_strategy"]["strategy_source"] == "template_transfer"
        assert result["composed_strategy"]["result_reuse_policy"] == "forbidden"
    assert reference["scientific_results_imported"] is False
    assert "atom_indices" in reference["nontransferable_fields"] and "initial_images" in reference["nontransferable_fields"]
    assert "structure_file_id" not in json.dumps(reference["borrowable_method_strategy"])


@pytest.mark.parametrize("change", ["template", "validation", "file_registration"])
def test_old_snapshot_expires_independently_of_learning_history_token(tmp_path, change):
    database, request = trial(tmp_path)
    expected = template_reference.template_snapshot(database)["snapshot_sha256"]
    learning_history = history_token(database)
    with fixture_connection(database) as connection:
        if change == "template":
            connection.execute("UPDATE ts_strategy_templates SET interpolation_strategy='constrained_idpp'")
        elif change == "validation":
            connection.execute("UPDATE ts_validations SET notes='synthetic amended validation record'")
        else:
            connection.execute("UPDATE files SET byte_size=2 WHERE file_id='ts_file'")
    assert history_token(database) == learning_history
    assert template_reference.template_snapshot(database)["snapshot_sha256"] != expected
    with pytest.raises(ValueError, match="template snapshot identity mismatch"):
        with_templates(database, request, expected)


@pytest.mark.parametrize("blocker", ["runtime", "input", "scf", "unknown", "path_missing", "STOP", "gpu_zero", "retry", "wrong_source"])
def test_matching_template_cannot_override_current_blockers(tmp_path, blocker):
    options = {"failure": blocker} if blocker in {"runtime", "input", "scf"} else {}
    if blocker == "unknown":
        options["certainty"] = "unknown"
    if blocker == "path_missing":
        options["path"] = False
    database, request = trial(tmp_path, **options)
    spec = load_json_object(request)
    if blocker == "STOP":
        gate = decide_execution({"status": "STOP", "errors": ["synthetic mapping failure"]}, {}, {}, climb=False,
                                path_reviewed=False, source_bindings={"assessment": spec["assessment"]})
        path = tmp_path / "current-gate.json"
        write_json(path, gate)
        update_trial(request, request_changes={"gate": bind_files({"gate": str(path)})["gate"]})
    elif blocker == "gpu_zero":
        update_trial(request, request_changes={"budget": {**spec["budget"], "gpu_hours": 0}})
    elif blocker == "retry":
        add_history(database, request)
    elif blocker == "wrong_source":
        assessment = load_json_object(Path(spec["assessment"]["path"]))
        assessment["evidence"][0]["sha256"] = "f" * 64
        update_trial(request, assessment_changes={"evidence": assessment["evidence"]})
        with pytest.raises(ValueError, match="stale evidence"):
            with_templates(database, request)
        return
    result = with_templates(database, request)
    assert result["template_reference"]["selected_template_id"]
    assert result["automatic_submission"] is False and result["execution_permissions_changed"] is False
    if blocker in {"runtime", "input", "scf", "unknown", "path_missing", "STOP"}:
        assert not any(c["kind"] == "TS_search_candidate" for c in result["candidates"])
    elif blocker == "gpu_zero":
        candidate = next(c for c in result["candidates"] if c["kind"] == "TS_search_candidate")
        assert candidate["status"] == "BUDGET_EXHAUSTED" and candidate["proposal"] is None
    else:
        assert result["unchanged_retry"]["status"] == "BLOCKED_KNOWN_FAILURE"
        assert result["unchanged_retry"]["execution_permitted_by_planner"] is False
    if blocker == "STOP":
        assert result["current_gate"] == gate and result["current_STOP_preserved"] is True


def test_cli_snapshot_and_enabled_plan_are_read_only(tmp_path, monkeypatch, capsys):
    database, request = trial(tmp_path)
    connect = sqlite3.connect
    def readonly(path, *args, **kwargs):
        assert Path(path) == database
        return connect(database.as_uri() + "?mode=ro", *args, uri=True, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", readonly)
    def forbidden(*_args, **_kwargs):
        pytest.fail("reference planning cannot execute or write history")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr("scripts.ts_strategy_engine.learning_store.append_event", forbidden)
    before = sha256_file(database)
    snapshot_path = tmp_path / "snapshot.json"
    learning_cli.main(["--database", str(database), "--output", str(snapshot_path), "template-snapshot"])
    expected = load_json_object(snapshot_path)["snapshot_sha256"]
    report = tmp_path / "plan-with-reference.json"
    learning_cli.main(["--database", str(database), "--output", str(report), "plan-next", "--request", str(request),
                      "--expected-request-sha256", sha256_file(request), "--use-templates",
                      "--expected-template-snapshot-sha256", expected])
    assert load_json_object(report)["composed_strategy"]["strategy_source"] == "template_transfer"
    assert sha256_file(database) == before
    assert "template_transfer" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        learning_cli.main(["template-snapshot"])


@pytest.mark.parametrize("enabled,expected", [(True, None), (False, "f" * 64), (True, "f" * 64)])
def test_explicit_enable_and_correct_expected_snapshot_are_required(tmp_path, enabled, expected):
    database, request = trial(tmp_path)
    with pytest.raises(ValueError):
        plan_next(database, request, sha256_file(request), use_templates=enabled, expected_template_snapshot_sha256=expected)


@pytest.mark.parametrize("stage", ["snapshot_loading", "planning"])
def test_registered_state_change_during_read_fails_closed(tmp_path, monkeypatch, stage):
    from scripts.ts_strategy_engine import decision_planner
    database, request = trial(tmp_path)
    expected = template_reference.template_snapshot(database)["snapshot_sha256"]
    def mutate():
        with fixture_connection(database) as connection:
            connection.execute("UPDATE ts_validations SET notes='synthetic concurrent revision'")
    if stage == "snapshot_loading":
        original = template_reference.templates.load_templates
        def read_then_change(*args, **kwargs):
            loaded = original(*args, **kwargs)
            mutate()
            return loaded
        monkeypatch.setattr(template_reference.templates, "load_templates", read_then_change)
    else:
        original = decision_planner.build_plan
        def plan_then_change(context):
            result = original(context)
            mutate()
            return result
        monkeypatch.setattr(decision_planner, "build_plan", plan_then_change)
    with pytest.raises(ValueError, match="registry changed during"):
        with_templates(database, request, expected)


def test_template_cannot_qualify_a_different_prerequisite_source(tmp_path):
    database, request = trial(tmp_path, method="aqcat25_ba_sella")
    spec = load_json_object(request)
    assessment = load_json_object(Path(spec["assessment"]["path"]))
    assessment["prerequisites"]["reviewed_gpu_handoff"] = "compatible_model_and_environment"
    update_trial(request, assessment_changes={"prerequisites": assessment["prerequisites"]})
    result = with_templates(database, request)
    assert result["template_reference"]["selected_template_id"]
    candidate = next(c for c in result["candidates"] if c["kind"] == "TS_search_candidate")
    assert candidate["prerequisite_checks"]["reviewed_gpu_handoff"] == "SOURCE_CHECK_IDENTITY_MISMATCH"
    assert candidate["proposal"] is None and candidate["status"] == "NEEDS_MORE_EVIDENCE"
