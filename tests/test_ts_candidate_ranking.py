"""Synthetic integration through real registry/validation and plan-next; no calculations."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import socket
import sqlite3
import subprocess

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.ts_strategy_engine import learning_cli, template_reference
from scripts.ts_strategy_engine.decision_planner import plan_next
from scripts.ts_strategy_engine.execution_gate import decide_execution
from scripts.ts_strategy_engine.fingerprint import build_fingerprint
from scripts.ts_strategy_engine.learning_evidence import bind_files
from scripts.ts_strategy_engine.learning_store import get_event
from scripts.ts_strategy_engine.templates import record_template
from tests.registry_fixture_mutation import fixture_connection
from tests.test_ts_decision_planner import add_history, synthetic_trial, update_trial
from tests.test_ts_planner_template_reuse import ci_readiness, rebind_contract, trial, with_templates
from tests.test_ts_strategy_engine import raw_contract, successful_record


def support_methods(request, methods):
    spec = load_json_object(request)
    assessment = load_json_object(Path(spec["assessment"]["path"]))
    support = next(iter(assessment["method_support"].values()))
    update_trial(request, assessment_changes={"method_support": {method: copy.deepcopy(support) for method in methods}})


def two_candidates(tmp_path, *, templates=True, methods=("matris_ml_neb_sella", "ci_neb")):
    database, request = (trial if templates else synthetic_trial)(tmp_path)
    support_methods(request, methods)
    if "ci_neb" in methods or "ordinary_neb" in methods:
        ci_readiness(request, tmp_path)
    return database, request


def searches(result):
    return {row["method"]: row for row in result["candidates"] if row["kind"] == "TS_search_candidate"}


def test_matching_registered_template_ranks_explicit_method_not_catalog_members(tmp_path):
    database, request = two_candidates(tmp_path)
    spec = load_json_object(request)
    variant = copy.deepcopy(get_event(database, "variant", spec["variant_id"]))
    before = sha256_file(database)
    snapshot = template_reference.template_snapshot(database)
    result = with_templates(database, request, snapshot["snapshot_sha256"])
    candidates = searches(result)
    assert [c["method"] for c in result["candidates"] if c["kind"] == "TS_search_candidate"] == ["ci_neb", "matris_ml_neb_sella"]
    assert candidates["ci_neb"]["rank"] == 1 and candidates["matris_ml_neb_sella"]["rank"] == 2
    assert all(c["status"] == "CONSIDER_FOR_REVIEW" and c["proposal"] is not None for c in candidates.values())
    row = candidates["ci_neb"]["supporting_evidence"]["templates"][0]
    assert row["template_id"] == "fe110_co_split_grade_a" and row["ts_validation_id"] == "validation_a"
    assert row["strategy_transferable"] and row["result_transferable"] and row["template_similarity"] == 1
    assert candidates["matris_ml_neb_sella"]["supporting_evidence"]["templates"] == []
    assert result["ranking_type"] == "evidence_supported_priority" and result["ranking"] == "EVIDENCE_SUPPORTED_PRIORITY"
    assert result["current_strategy_settings"] == variant["settings"]
    assert get_event(database, "variant", spec["variant_id"]) == variant and load_json_object(request) == spec
    assert sha256_file(database) == before and template_reference.template_snapshot(database) == snapshot
    assert all(not c["automatic_execution"] and not c["proposal_recorded"] for c in candidates.values())
    for name in ("automatic_submission", "automatic_promotion", "execution_permissions_changed"):
        assert result[name] is False
    serialized = json.dumps(result)
    assert not any('"' + key + '":' in serialized for key in (
        "success_probability", "predicted_barrier", "expected_convergence_rate", "forward_barrier_ev"))


def test_existing_similarity_distinguishes_two_qualified_method_references(tmp_path):
    database, request = two_candidates(tmp_path)
    other = raw_contract()
    other["reactant_id"] = "synthetic_related_CO"
    record_template(database, successful_record(template_id="synthetic-related-method-reference",
                    fingerprint=build_fingerprint(other), neb_settings={"sequence": ["matris_ml_neb_sella"]}))
    result = with_templates(database, request)
    candidates = searches(result)
    ci = candidates["ci_neb"]["supporting_evidence"]["templates"][0]
    gpu = candidates["matris_ml_neb_sella"]["supporting_evidence"]["templates"][0]
    assert ci["strategy_transferable"] and gpu["strategy_transferable"]
    assert ci["template_similarity"] > gpu["template_similarity"]
    assert ci["result_transferable"] is True and gpu["result_transferable"] is False
    assert candidates["ci_neb"]["rank"] < candidates["matris_ml_neb_sella"]["rank"]


@pytest.mark.parametrize("resource,blocked,eligible", [
    ("gpu_hours", "matris_ml_neb_sella", "ci_neb"),
    ("vasp_core_hours", "ci_neb", "matris_ml_neb_sella"),
])
def test_zero_relevant_budget_blocks_rank_without_harming_other_backend(tmp_path, resource, blocked, eligible):
    database, request = two_candidates(tmp_path)
    spec = load_json_object(request)
    update_trial(request, request_changes={"budget": {**spec["budget"], resource: 0}})
    result = with_templates(database, request)
    candidates = searches(result)
    assert candidates[blocked]["rank"] is None and candidates[blocked]["proposal"] is None
    assert "budget:" + resource in candidates[blocked]["blocking_conditions"]
    assert candidates[eligible]["rank"] == 1 and candidates[eligible]["proposal"] is not None
    assert all(c["budget_fit"] == "NOT_ESTABLISHED" for c in candidates.values())


def test_known_limit_can_prioritize_availability_but_never_claim_cost_fit(tmp_path):
    database, request = two_candidates(tmp_path, templates=False)
    result = plan_next(database, request, sha256_file(request))
    candidates = searches(result)
    assert candidates["matris_ml_neb_sella"]["rank"] == 1 and candidates["ci_neb"]["rank"] == 2
    assert "relevant_resource_limits_unknown" in candidates["ci_neb"]["uncertainty"]
    assert all(c["budget_fit"] == "NOT_ESTABLISHED" and set(c["future_cost"].values()) == {"NOT_MEASURED"}
               for c in candidates.values())


def test_unknown_cause_has_no_confident_ranking_even_with_success_template(tmp_path):
    database, request = trial(tmp_path, certainty="unknown")
    result = with_templates(database, request)
    assert searches(result) == {} and result["ranking"] == "UNRANKED_NO_COMPARATIVE_EVIDENCE"
    assert result["ranking_uncertainty"] == ["causal_evidence_missing_no_TS_ranking"]
    assert any(item["kind"] == "collect_cause_specific_evidence" for item in result["mandatory_first"])


def test_exact_unchanged_failure_cannot_rank_but_changed_method_is_not_banned(tmp_path):
    database, request = two_candidates(tmp_path, methods=("ordinary_neb", "ci_neb"))
    add_history(database, request)
    # Freeze gate to the same updated assessment; history update changes only request.
    result = with_templates(database, request)
    candidates = searches(result)
    assert result["unchanged_retry"]["status"] == "BLOCKED_KNOWN_FAILURE"
    unchanged = candidates["ordinary_neb"]
    assert unchanged["rank"] is None and "confirmed_deterministic_unchanged_failure:old-1" in unchanged["blocking_conditions"]
    row = unchanged["supporting_evidence"]["unchanged_failures"][0]
    assert row["input_key"] == result["input_key"] and row["variant_id"] == result["variant_id"]
    assert unchanged["supporting_evidence"]["task_lessons"][0]["evidence_status"] == "current"
    assert candidates["ci_neb"]["rank"] == 1 and candidates["ci_neb"]["supporting_evidence"]["unchanged_failures"] == []
    assert "fresh_candidate_inputs_require_existing_retry_review" in candidates["ci_neb"]["uncertainty"]


@pytest.mark.parametrize("scope", ["same_task", "other_task"])
def test_different_input_failures_cannot_create_method_frequency_ranking(tmp_path, scope):
    database, request = two_candidates(tmp_path, templates=False, methods=("matris_ml_neb_sella", "aqcat25_ba_sella"))
    add_history(database, request, changed=True, task="co_split" if scope == "same_task" else "other-task")
    result = plan_next(database, request, sha256_file(request))
    assert result["historical_attempts"][0]["scope"] == scope
    assert result["ranking"] == "UNRANKED_NO_COMPARATIVE_EVIDENCE"
    assert all(c["rank"] is None and c["supporting_evidence"]["unchanged_failures"] == [] for c in searches(result).values())


def test_no_comparative_evidence_keeps_null_ranks_and_original_order(tmp_path):
    database, request = two_candidates(tmp_path, templates=False, methods=("aqcat25_ba_sella", "matris_ml_neb_sella"))
    result = plan_next(database, request, sha256_file(request))
    assert list(searches(result)) == ["aqcat25_ba_sella", "matris_ml_neb_sella"]
    assert result["ranking"] == "UNRANKED_NO_COMPARATIVE_EVIDENCE"
    assert all(c["rank"] is None and "no_comparative_priority_evidence" in c["uncertainty"] for c in searches(result).values())
    update_trial(request, request_changes={"budget": None})
    result = plan_next(database, request, sha256_file(request))
    assert all(c["rank"] is None and "relevant_resource_limits_unknown" in c["uncertainty"] for c in searches(result).values())


def test_equal_template_evidence_does_not_turn_sequence_into_ranking(tmp_path):
    database, request = trial(tmp_path, template_settings={"sequence": ["matris_ml_neb_sella", "ci_neb"]})
    support_methods(request, ["ci_neb", "matris_ml_neb_sella"])
    ci_readiness(request, tmp_path)
    spec = load_json_object(request)
    update_trial(request, request_changes={"budget": {**spec["budget"], "vasp_core_hours": 2}})
    result = with_templates(database, request)
    assert list(searches(result)) == ["ci_neb", "matris_ml_neb_sella"]
    assert result["ranking"] == "UNRANKED_NO_COMPARATIVE_EVIDENCE"
    assert all(c["rank"] is None and len(c["supporting_evidence"]["templates"]) == 1 for c in searches(result).values())


@pytest.mark.parametrize("limit", ["remaining_attempts", "force_calls"])
def test_exhausted_shared_budget_cannot_gain_rank_from_template(tmp_path, limit):
    database, request = two_candidates(tmp_path)
    spec = load_json_object(request)
    update_trial(request, request_changes={"budget": {**spec["budget"], limit: 0}})
    result = with_templates(database, request)
    assert result["ranking"] == "UNRANKED_NO_COMPARATIVE_EVIDENCE"
    assert all(c["rank"] is None and c["proposal"] is None and "budget:" + limit in c["blocking_conditions"]
               for c in searches(result).values())


@pytest.mark.parametrize("blocker", ["runtime", "input", "scf", "STOP", "path_missing"])
def test_template_cannot_rank_through_existing_diagnostic_or_STOP_blocker(tmp_path, blocker):
    options = {"failure": blocker} if blocker in {"runtime", "input", "scf"} else {"path": blocker != "path_missing"}
    database, request = trial(tmp_path, **options)
    if blocker == "STOP":
        spec = load_json_object(request)
        gate = decide_execution({"status": "STOP", "errors": ["synthetic identity failure"]}, {}, {},
                                climb=False, path_reviewed=False, source_bindings={"assessment": spec["assessment"]})
        target = tmp_path / "STOP.json"
        write_json(target, gate)
        update_trial(request, request_changes={"gate": bind_files({"gate": str(target)})["gate"]})
    result = with_templates(database, request)
    assert searches(result) == {} and result["ranking"] == "UNRANKED_NO_COMPARATIVE_EVIDENCE"
    if blocker == "STOP":
        assert result["current_STOP_preserved"] and result["current_gate"] == gate and load_json_object(target) == gate


def test_missing_prerequisite_never_ranks_above_complete_candidate(tmp_path):
    database, request = two_candidates(tmp_path)
    update_trial(request, assessment_changes={"prerequisites": {}})
    ci_readiness(request, tmp_path)
    result = with_templates(database, request)
    candidates = searches(result)
    assert candidates["ci_neb"]["rank"] == 1
    gpu = candidates["matris_ml_neb_sella"]
    assert gpu["rank"] is None and gpu["status"] == "NEEDS_MORE_EVIDENCE" and gpu["proposal"] is None
    assert all("prerequisite:" + name in gpu["blocking_conditions"] for name in gpu["missing_prerequisites"])


@pytest.mark.parametrize("damage", ["grade", "file", "failure", "unsafe_method"])
def test_invalid_or_failed_template_cannot_support_ranking(tmp_path, damage):
    database, request = two_candidates(tmp_path, methods=("aqcat25_ba_sella", "matris_ml_neb_sella"))
    with fixture_connection(database) as connection:
        if damage == "grade":
            connection.execute("UPDATE ts_validations SET grade='B',kinetic_eligible=0")
        elif damage == "file":
            connection.execute("UPDATE files SET existence_status='missing' WHERE file_id='vfa_outcar'")
        elif damage == "failure":
            connection.execute("DELETE FROM ts_strategy_templates")
        else:
            connection.execute("UPDATE ts_strategy_templates SET neb_settings_json=?", (json.dumps({"sequence": ["arbitrary_shell"]}),))
    if damage == "failure":
        record_template(database, successful_record(outcome="failure", validation_grade="Ungraded",
                        failure_cases=["synthetic failure"], correction_strategy="review actual sources"))
    result = with_templates(database, request)
    assert result["ranking"] == "UNRANKED_NO_COMPARATIVE_EVIDENCE"
    assert all(not c["supporting_evidence"]["templates"] for c in searches(result).values())
    assert "arbitrary_shell" not in searches(result)


def test_cross_branch_strategy_support_never_imports_results(tmp_path):
    database, request = two_candidates(tmp_path)
    contract = raw_contract()
    contract["compatibility"]["branch"] = "synthetic_incompatible_energy_branch"
    rebind_contract(request, contract)
    ci_readiness(request, tmp_path)
    result = with_templates(database, request)
    row = searches(result)["ci_neb"]["supporting_evidence"]["templates"][0]
    assert row["strategy_transferable"] and not row["result_transferable"] and not row["scientific_results_imported"]
    assert searches(result)["ci_neb"]["rank"] == 1
    assert result["composed_strategy"]["result_reuse_policy"] == "forbidden"


def test_ranked_cli_is_read_only_and_retains_actual_bound_checks(tmp_path, monkeypatch, capsys):
    database, request = two_candidates(tmp_path)
    digest = template_reference.template_snapshot(database)["snapshot_sha256"]
    before = sha256_file(database)
    original = sqlite3.connect
    def read_only(path, *args, **kwargs):
        assert Path(path) == database
        connection = original(path, *args, **kwargs)
        connection.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action in {
            sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
            sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_DROP_TABLE} else sqlite3.SQLITE_OK)
        return connection
    def forbidden(*_args, **_kwargs):
        pytest.fail("planning attempted network/process/model or executor access")
    monkeypatch.setattr(sqlite3, "connect", read_only)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    target = tmp_path / "ranked-plan.json"
    assert learning_cli.main(["--database", str(database), "--output", str(target), "plan-next", "--request", str(request),
                             "--expected-request-sha256", sha256_file(request), "--use-templates",
                             "--expected-template-snapshot-sha256", digest]) is None
    capsys.readouterr()
    result = load_json_object(target)
    gpu = searches(result)["matris_ml_neb_sella"]
    for name, check in gpu["supporting_evidence"]["prerequisites"].items():
        assert check["status"] == "PASS" and check["source"]["pointer"] == "/checks/" + name
        assert check["source"]["value"] is True and sha256_file(Path(check["source"]["path"])) == check["source"]["sha256"]
    assert sha256_file(database) == before and result["ranking"] == "EVIDENCE_SUPPORTED_PRIORITY"
