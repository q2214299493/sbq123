"""Synthetic planning integration: real temporary files/database, no scientific execution."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
import subprocess

import pytest

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json
from scripts.registry_schema import migrate_registry
from scripts.ts_strategy_engine import learning_cli, strategy_learning as learning
from scripts.ts_strategy_engine.decision_planner import COST_FIELDS, plan_next
from scripts.ts_strategy_engine.execution_gate import decide_execution
from scripts.ts_strategy_engine.learning_evidence import attempt_input_hashes, bind_files, input_key
from scripts.ts_strategy_engine.learning_store import get_event, history_token
from tests.test_ts_strategy_engine import contract


def synthetic_trial(tmp_path: Path, failure="optimizer", certainty="hypothesis", path=True, method="matris_ml_neb_sella"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = tmp_path / "synthetic.sqlite3"
    migrate_registry(database)
    contract_path = tmp_path / "contract.json"
    write_json(contract_path, contract())
    settings = {"candidate_method": "ordinary_neb", "initial_images": 5, "interpolation_strategy": "segmented_idpp"}
    source = tmp_path / "baseline-settings.json"
    write_json(source, {"provenance": "synthetic", "settings": settings})
    variant = learning.capture_baseline(database, {"task_id": "co_split", "cases": ["co_split", "other-task"],
        "settings": settings, "sources": {"actual_settings": str(source)}, "attempt_budget": 3})
    inputs = bind_files({"contract": str(contract_path), "seed": str(source)})
    key = input_key("matris_ml_neb", attempt_input_hashes("matris_ml_neb", inputs))
    raw = tmp_path / "raw-path-observations.json"
    checks = {name: True for reference in learning.reference_methods().values() for name in reference["prerequisites"]}
    write_json(raw, {"provenance": "synthetic", "task_id": "co_split", "input_key": key,
                     "symptom": "Optimizer stalled on the geometry-valid synthetic path", "path_geometry_valid": True,
                     "checks": checks, "force_calls": 12, "gpu_hours": 0.25})
    evidence = [{"evidence_id": identity, "path": str(raw), "sha256": sha256_file(raw), "pointer": pointer, "value": value}
                for identity, pointer, value in [("symptom", "/symptom", "Optimizer stalled on the geometry-valid synthetic path"),
                                                  ("path", "/path_geometry_valid", True)]]
    evidence.extend({"evidence_id": name, "path": str(raw), "sha256": sha256_file(raw), "pointer": "/checks/" + name,
                     "value": True} for name in checks)
    assessment = {"task_id": "co_split", "variant_id": variant, "input_key": key, "provenance": "synthetic",
        "diagnosis": {"failure_class": failure, "causal_status": certainty,
            "causal_claim": None if certainty == "unknown" else "Investigate the observed optimization stall",
            "causal_evidence_ids": [] if certainty == "unknown" else ["symptom"],
            "next_review": learning.policy()["failure_routes"][failure], "evidence_ids": ["symptom", "path"]},
        "evidence": evidence, "path_evidence_ids": ["path"] if path else [],
        "prerequisites": {name: name for name in checks},
        "method_support": {} if certainty == "unknown" else {method: {
            "rationale": "Review local peak refinement for the observed stall; model error remains an alternative explanation",
            "evidence_ids": ["symptom", "path"]}}}
    assessment_path = tmp_path / "assessment.json"
    write_json(assessment_path, assessment)
    request = {"schema_version": 1, "task_id": "co_split", "variant_id": variant, "variant_sha256": variant,
        "history_sha256": history_token(database), "kind": "matris_ml_neb", "inputs": inputs,
        "assessment": bind_files({"assessment": str(assessment_path)})["assessment"], "gate": None,
        "budget": {"remaining_attempts": 1, "force_calls": 100, "gpu_hours": 1.5, "vasp_core_hours": None}}
    request_path = tmp_path / "request.json"
    write_json(request_path, request)
    return database, request_path


def update_trial(request_path, *, request_changes=None, assessment_changes=None):
    request = load_json_object(request_path)
    if assessment_changes:
        path = Path(request["assessment"]["path"])
        assessment = load_json_object(path)
        assessment.update(assessment_changes)
        write_json(path, assessment)
        request["assessment"]["sha256"] = sha256_file(path)
    request.update(request_changes or {})
    write_json(request_path, request)


def run_trial(database, request):
    return plan_next(database, request, sha256_file(request))


def add_history(database, request_path, *, identity="old-1", task="co_split", changed=False, pending=False):
    request = load_json_object(request_path)
    inputs = {name: value["path"] for name, value in request["inputs"].items()}
    if changed:
        path = request_path.parent / (identity + "-input.json")
        write_json(path, {"provenance": "synthetic", "different": identity})
        inputs["seed"] = str(path)
    learning.start_attempt(database, {"attempt_id": identity, "variant_id": request["variant_id"], "task_id": task,
                           "kind": request["kind"], "inputs": inputs, "parent_attempt_id": None})
    if not pending:
        assessment = load_json_object(Path(request["assessment"]["path"]))
        observation = {k: v for k, v in assessment["evidence"][0].items() if k != "evidence_id"}
        raw = Path(observation["path"])
        observations = [observation, {"path": str(raw), "sha256": sha256_file(raw), "pointer": "/force_calls", "value": 12},
                        {"path": str(raw), "sha256": sha256_file(raw), "pointer": "/gpu_hours", "value": 0.25}]
        learning.record_outcome(database, identity, {"status": "failure", "failure_class": "optimizer",
            "root_cause_status": "confirmed", "deterministic": True, "reviewer": "synthetic fixture reviewer",
            "observations": observations, "costs": {"force_calls": 12, "gpu_hours": 0.25}, "ts_template_id": None})
    update_trial(request_path, request_changes={"history_sha256": history_token(database)})


@pytest.mark.parametrize("failure", ["runtime", "input", "scf"])
def test_upstream_failures_suppress_TS_method_and_parameter_reviews(tmp_path, failure):
    database, request = synthetic_trial(tmp_path, failure=failure)
    result = run_trial(database, request)
    assert not result["candidates"]
    assert result["mandatory_first"][0]["next_review"] == learning.policy()["failure_routes"][failure]
    assert "resolve_upstream_failure_before_TS_method_review" in result["evidence_gaps"]


def test_unknown_cause_and_missing_geometry_collect_evidence(tmp_path):
    database, request = synthetic_trial(tmp_path / "unknown", certainty="unknown")
    result = run_trial(database, request)
    assert not result["candidates"]
    assert any(row["kind"] == "collect_cause_specific_evidence" for row in result["mandatory_first"])
    database, request = synthetic_trial(tmp_path / "geometry", failure="geometry", path=False)
    result = run_trial(database, request)
    assert not result["candidates"]
    assert "path_evidence_missing" in result["evidence_gaps"]


def test_geometry_only_reviews_existing_fields_without_numeric_change(tmp_path):
    database, request = synthetic_trial(tmp_path, failure="geometry")
    result = run_trial(database, request)
    assert [row["field"] for row in result["candidates"]] == ["interpolation_strategy", "initial_images"]
    assert all(row["new_value"] == "NOT_PROPOSED" for row in result["candidates"])


@pytest.mark.parametrize("method", ["matris_ml_neb_sella", "aqcat25_ba_sella"])
def test_optimizer_considers_only_supported_method_and_reuses_proposal_schema(tmp_path, method):
    database, request = synthetic_trial(tmp_path, method=method)
    before = sha256_file(database)
    result = run_trial(database, request)
    search = [row for row in result["candidates"] if row["kind"] == "TS_search_candidate"]
    assert len(search) == 1 and search[0]["method"] == method
    candidate = search[0]
    assert candidate["status"] == "CONSIDER_FOR_REVIEW"
    assert candidate["proposal"]["changes"] == {"candidate_method": method}
    assert set(candidate["proposal"]) == {"parent_id", "changes", "rationale", "observations"}
    assert candidate["result_class"] == "predicted_transition_state_candidate_only"
    assert not candidate["proposal_recorded"] and sha256_file(database) == before
    # Explicitly test existing propose_variant separately in this synthetic DB.
    child = learning.propose_variant(database, **candidate["proposal"])
    update_trial(request, request_changes={"variant_id": child, "variant_sha256": child, "history_sha256": history_token(database)},
                 assessment_changes={"variant_id": child})
    later = run_trial(database, request)
    assert later["existing_variant_comparison"]["decision"] == "NEEDS_MORE_EVIDENCE"
    assert later["automatic_promotion"] is False


def test_missing_prerequisite_and_no_method_reason_never_qualify(tmp_path):
    database, request = synthetic_trial(tmp_path)
    update_trial(request, assessment_changes={"prerequisites": {}})
    searches = [row for row in run_trial(database, request)["candidates"] if row["kind"] == "TS_search_candidate"]
    assert searches[0]["status"] == "NEEDS_MORE_EVIDENCE"
    assert searches[0]["missing_prerequisites"] == learning.reference_methods()[searches[0]["method"]]["prerequisites"]
    update_trial(request, assessment_changes={"method_support": {}})
    assert all(row["kind"] != "TS_search_candidate" for row in run_trial(database, request)["candidates"])


def test_exact_input_failure_and_unresolved_attempt_cannot_be_retried(tmp_path):
    database, request = synthetic_trial(tmp_path / "failed")
    add_history(database, request)
    result = run_trial(database, request)
    assert result["unchanged_retry"]["status"] == "BLOCKED_KNOWN_FAILURE"
    assert result["unchanged_retry"]["blocked_attempts"] == ["old-1"]
    assert result["historical_attempts"][0]["scope"] == "same_input"
    assert result["historical_attempts"][0]["observed_costs"]["force_calls"] == 12
    assert result["future_cost"]["force_calls"] == "NOT_MEASURED"
    database, request = synthetic_trial(tmp_path / "pending")
    add_history(database, request, pending=True)
    result = run_trial(database, request)
    assert result["unchanged_retry"]["pending_attempts"] == ["old-1"]
    assert result["unchanged_retry"]["history_clear"] is False


def test_history_scope_does_not_create_global_method_scores(tmp_path):
    database, request = synthetic_trial(tmp_path)
    add_history(database, request, identity="same-task", changed=True)
    add_history(database, request, identity="other-task", task="other-task", changed=True)
    result = run_trial(database, request)
    assert [row["scope"] for row in result["historical_attempts"]] == ["same_task", "other_task"]
    assert result["unchanged_retry"]["status"] == "NO_KNOWN_FAILURE"
    assert result["ranking"] == "UNRANKED_NO_COMPARATIVE_EVIDENCE"
    assert "probability" not in json.dumps(result)


@pytest.mark.parametrize("value", [False, None])
def test_failed_or_unreviewed_actual_prerequisite_never_qualifies(tmp_path, value):
    database, request = synthetic_trial(tmp_path)
    spec = load_json_object(request)
    assessment_path = Path(spec["assessment"]["path"])
    assessment = load_json_object(assessment_path)
    raw_path = Path(assessment["evidence"][0]["path"])
    raw = load_json_object(raw_path)
    name = learning.reference_methods()["matris_ml_neb_sella"]["prerequisites"][0]
    raw["checks"][name] = value
    write_json(raw_path, raw)
    for item in assessment["evidence"]:
        item["sha256"] = sha256_file(raw_path)
        if item["evidence_id"] == name:
            item["value"] = value
    update_trial(request, assessment_changes={"evidence": assessment["evidence"]})
    candidate = next(row for row in run_trial(database, request)["candidates"] if row["kind"] == "TS_search_candidate")
    assert name in candidate["missing_prerequisites"]
    assert candidate["status"] == "NEEDS_MORE_EVIDENCE" and candidate["proposal"] is None


def test_same_input_on_other_task_stays_explicitly_distinct(tmp_path):
    database, request = synthetic_trial(tmp_path)
    add_history(database, request, task="other-task")
    result = run_trial(database, request)
    row = result["historical_attempts"][0]
    assert row["scope"] == "same_input" and row["same_task"] is False
    assert result["task_lessons"] == []
    assert result["unchanged_retry"]["status"] == "BLOCKED_KNOWN_FAILURE"


def test_stale_history_remains_review_required_and_cost_unknown(tmp_path):
    database, request = synthetic_trial(tmp_path)
    add_history(database, request)
    spec = load_json_object(request)
    assessment = load_json_object(Path(spec["assessment"]["path"]))
    # Use a separate, now-stale historical observation while current sources remain valid.
    raw = tmp_path / "historical.json"
    write_json(raw, {"failure": True})
    previous = get_event(database, "outcome", "old-1")
    learning.revise_outcome(database, "old-1", {"status": "failure", "failure_class": "optimizer",
        "root_cause_status": "confirmed", "deterministic": True, "reviewer": "synthetic fixture",
        "observations": [{"path": str(raw), "sha256": sha256_file(raw), "pointer": "/failure", "value": True}],
        "costs": {}, "ts_template_id": None}, previous_sha256=sha256_json(previous), reason="synthetic correction")
    write_json(raw, {"failure": False})
    update_trial(request, request_changes={"history_sha256": history_token(database)})
    result = run_trial(database, request)
    assert result["historical_attempts"][0]["evidence_status"] == "NEEDS_REVIEW"
    assert set(result["historical_attempts"][0]["observed_costs"].values()) == {"NOT_MEASURED"}
    assert result["unchanged_retry"]["status"] == "NEEDS_REVIEW"
    assert result["history_semantics"] == "latest_reviewed_outcomes_not_past_decision_time"
    assert load_json_object(Path(spec["assessment"]["path"])) == assessment


def test_missing_budget_costs_and_history_are_unknown_not_zero(tmp_path):
    database, request = synthetic_trial(tmp_path)
    update_trial(request, request_changes={"budget": None})
    result = run_trial(database, request)
    assert all(value is None for value in result["budget"].values())
    assert set(result["future_cost"].values()) == {"NOT_MEASURED"}
    assert "historical_results_not_recorded" in result["evidence_gaps"]
    assert "budget_limits_missing_or_partial" in result["evidence_gaps"]
    update_trial(request, request_changes={"budget": {"remaining_attempts": 0, **dict.fromkeys(COST_FIELDS)}})
    searches = [row for row in run_trial(database, request)["candidates"] if row["kind"] == "TS_search_candidate"]
    assert searches[0]["status"] == "BUDGET_EXHAUSTED" and searches[0]["proposal"] is None


@pytest.mark.parametrize("damage", ["task", "contract", "strategy", "policy", "history", "request_hash",
    "raw_hash", "raw_task", "raw_input", "assessment_variant", "json_type", "budget_bool", "method", "gate_identity"])
def test_mismatched_sources_and_versions_fail_closed(tmp_path, damage):
    database, request_path = synthetic_trial(tmp_path)
    request = load_json_object(request_path)
    assessment_path = Path(request["assessment"]["path"])
    assessment = load_json_object(assessment_path)
    if damage == "task":
        request["task_id"] = "other-task"
    elif damage == "contract":
        source = Path(request["inputs"]["contract"]["path"])
        write_json(source, contract(reaction_id="wrong"))
        request["inputs"]["contract"]["sha256"] = sha256_file(source)
    elif damage in {"strategy", "policy"}:
        if damage == "strategy":
            request["variant_sha256"] = "f" * 64
        else:
            monkey_policy = get_event(database, "variant", request["variant_id"])
            monkey_policy["policy_sha256"] = "f" * 64
            # The existing immutable ID cannot match changed content.
            import scripts.ts_strategy_engine.decision_planner as planner
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(planner, "get_event", lambda *_: monkey_policy)
                with pytest.raises(ValueError):
                    run_trial(database, request_path)
            return
    elif damage == "history":
        request["history_sha256"] = "f" * 64
    elif damage == "request_hash":
        with pytest.raises(ValueError):
            plan_next(database, request_path, "f" * 64)
        return
    elif damage in {"raw_hash", "raw_task", "raw_input"}:
        source = Path(assessment["evidence"][0]["path"])
        raw = load_json_object(source)
        raw["task_id" if damage != "raw_input" else "input_key"] = "wrong"
        write_json(source, raw)
        if damage != "raw_hash":
            for item in assessment["evidence"]:
                item["sha256"] = sha256_file(source)
    elif damage == "assessment_variant":
        assessment["variant_id"] = "wrong"
    elif damage == "json_type":
        assessment["evidence"][1]["value"] = 1
    elif damage == "budget_bool":
        request["budget"]["force_calls"] = True
    elif damage == "method":
        assessment["method_support"]["arbitrary_shell"] = assessment["method_support"].pop("matris_ml_neb_sella")
    else:
        gate_path = tmp_path / "bad-gate.json"
        write_json(gate_path, {"DECISION": "PASS", "ALLOWED_ACTIONS": ["SUBMIT_VASP"]})
        request["gate"] = bind_files({"gate": str(gate_path)})["gate"]
    write_json(assessment_path, assessment)
    request["assessment"]["sha256"] = sha256_file(assessment_path)
    write_json(request_path, request)
    with pytest.raises(ValueError):
        run_trial(database, request_path)


def test_actual_gate_STOP_is_preserved_and_has_priority(tmp_path):
    database, request = synthetic_trial(tmp_path)
    spec = load_json_object(request)
    gate = decide_execution({"status": "STOP", "errors": ["synthetic mapping mismatch"]}, {}, {}, climb=False, path_reviewed=False,
                            source_bindings={"assessment": spec["assessment"]})
    gate_path = tmp_path / "gate.json"
    write_json(gate_path, gate)
    original = copy.deepcopy(gate)
    update_trial(request, request_changes={"gate": bind_files({"gate": str(gate_path)})["gate"]})
    result = run_trial(database, request)
    assert result["current_gate"] == original
    assert result["current_STOP_preserved"] is True
    assert result["mandatory_first"][0]["decision"] == original["DECISION"]
    assert not any(row["kind"] == "TS_search_candidate" for row in result["candidates"])
    assert load_json_object(gate_path) == original


def test_cli_synthetic_end_to_end_read_only_and_explicit_database(tmp_path, monkeypatch, capsys):
    database, request = synthetic_trial(tmp_path)
    def forbidden(*_args, **_kwargs):
        pytest.fail("planner must never write history, execute a process or change a strategy")
    for name in ("apply_variant", "propose_variant", "start_attempt", "record_outcome", "revise_outcome"):
        monkeypatch.setattr(learning, name, forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr("scripts.ts_strategy_engine.learning_store.append_event", forbidden)
    before = sha256_file(database)
    with pytest.raises(SystemExit) as exc:
        learning_cli.main(["plan-next", "--request", str(request), "--expected-request-sha256", sha256_file(request)])
    assert exc.value.code == 2
    assert "explicit --database" in capsys.readouterr().err
    report = tmp_path / "plan.json"
    learning_cli.main(["--database", str(database), "--output", str(report), "plan-next", "--request", str(request),
                       "--expected-request-sha256", sha256_file(request)])
    assert load_json_object(report)["status"] == "ADVISORY_ONLY_NOT_AUTHORIZED"
    assert sha256_file(database) == before
    with pytest.raises(SystemExit):
        learning_cli.main(["--database", str(database), "--output", str(report), "plan-next", "--request", str(request),
                           "--expected-request-sha256", sha256_file(request)])


def test_planning_rejects_SQL_writes_and_never_touches_another_database(tmp_path, monkeypatch):
    database, request = synthetic_trial(tmp_path)
    original = sqlite3.connect
    connections = []
    def read_only_connection(path, *args, **kwargs):
        assert Path(path) == database
        connection = original(path, *args, **kwargs)
        connections.append(connection)
        blocked = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                   sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_ALTER_TABLE}
        connection.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action in blocked else sqlite3.SQLITE_OK)
        return connection
    before = sha256_file(database)
    monkeypatch.setattr(sqlite3, "connect", read_only_connection)
    assert run_trial(database, request)["automatic_submission"] is False
    assert connections and sha256_file(database) == before


def test_pure_plan_has_no_file_IO_and_does_not_mutate_inputs(tmp_path, monkeypatch):
    import builtins
    import io
    from scripts.ts_strategy_engine import decision_planner as planner
    database, request = synthetic_trial(tmp_path)
    original = planner.build_plan
    captured = []
    def capture(context):
        captured.append(context)
        return original(context)
    monkeypatch.setattr(planner, "build_plan", capture)
    run_trial(database, request)
    context = captured[0]
    before = copy.deepcopy(context)
    def reject_IO(*_args, **_kwargs):
        pytest.fail("pure planner attempted file I/O")
    monkeypatch.setattr(builtins, "open", reject_IO)
    monkeypatch.setattr(io, "open", reject_IO)
    assert original(context)["candidates"]
    assert context == before
