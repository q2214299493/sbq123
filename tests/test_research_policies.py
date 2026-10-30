"""RSI integration/abuse/temporal checks with synthetic transport and sources only."""
from copy import deepcopy
import json

import pytest

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.research_assistant.cli import feedback
from scripts.research_assistant.contract import response_schema, validate_response
from scripts.research_assistant.policies import PolicyStore, utc_now
from scripts.research_assistant.policy_cli import usage_record
from scripts.research_assistant.policy_selection import settings
from scripts.research_assistant.runner import ResearchRun

from test_research_assistant import Peer, final_answer, request


def ref(path):
    return {"path": str(path), "sha256": sha256_file(path)}


@pytest.fixture
def environment(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    source = project / "history_review.md"
    source.write_text("Synthetic registered carbon structure build record. Compatibility remains unknown.\n", encoding="utf-8")
    store = PolicyStore(tmp_path / "policies", project)
    definition = {"policy_id": "check_registered_material", "version": 1, "proposed_at": utc_now(), "proposer": "external_proposal",
        "source_refs": [ref(source)], "scope": {"project": str(project), "intents": ["auto", "plan"],
        "required_tools": ["history.search", "evidence.read"], "goal_terms_any": ["prepare structure"], "excluded_goal_terms_any": [],
        "limitations": "Synthetic scope; no scientific acceptance."}, "previous_behavior": "May prepare the same structure twice.",
        "behavior_change": "Check registered source and build records before proposing new preparation.",
        "expected_help": "Potential source reuse; unmeasured.", "added_burden": "One bounded source check.",
        "validation_task": "A new synthetic preparation question.", "evaluation": "Check input/action/output identity, then independent content review.",
        "required_checks": ["Scientific owner compatibility cannot be skipped."],
        "checks": {"ordered_tool_groups": [["history.search", "methods.search", "evidence.list"], ["evidence.read"]],
                   "read_search_hit": True, "require_output_citation": True},
        "priority": 10, "equivalence_key": "", "conflict_group": "", "supersedes": []}
    return tmp_path, project, store, definition


def propose(environment, *, status="accepted", **updates):
    tmp, _, store, base = environment
    definition = {**deepcopy(base), **updates}
    record = store.propose(definition)
    if status != "candidate":
        evidence = tmp / (definition["policy_id"] + str(definition["version"]) + "-test-validation.json")
        write_json_exclusive(evidence, {"kind": "synthetic software validation fixture; not researcher adoption"})
        review(environment, definition, record, status, evidence)
    return record


def review(environment, definition, record, status, evidence=None):
    tmp, _, store, _ = environment
    request = {"policy_id": definition["policy_id"], "version": definition["version"], "content_sha256": record["content_sha256"],
               "status": status, "reviewer": "synthetic test user", "validation_scope": "offline wiring fixture only",
               "validation_refs": [ref(evidence)] if evidence else [], "reason": "Explicit synthetic review"}
    path = tmp / (sha256_json(request) + ".json")
    write_json_exclusive(path, request)
    return store.review(request, ref(path))


def run_for(environment, name, *, goal="prepare structure for an unseen synthetic question", parent=None, intent="plan", **config):
    tmp, project, store, _ = environment
    return ResearchRun(goal, intent, [project], project, tmp / name,
                       previous_run=parent.output if parent else None, update="synthetic follow-up" if parent else "",
                       max_turns=3, rsi={"store": str(store.root), **config})


def rsi(**updates):
    return {"applications": [], "observations": [], "improvement_candidates": [], **updates}


class PolicyPeer(Peer):
    def __init__(self, run, *, claims=None, candidates=(), observations=(), early_candidates=()):
        super().__init__(run)
        self.claims, self.candidates, self.observations = claims, list(candidates), list(observations)
        self.early_candidates = list(early_candidates)

    def rpc(self, method, params):
        if method != "turn/start":
            return super().rpc(method, params)
        self.calls += 1
        turn = "turn" + str(self.calls)
        if self.calls == 1:
            value = {"kind": "request", "requests": [request("history.search", query="registered carbon")], "answer": None,
                     "rsi": rsi(improvement_candidates=self.early_candidates)}
        elif self.calls == 2:
            identity = self.run.tools.results["E001"]["data"]["matches"][0]["source_id"]
            value = {"kind": "request", "requests": [request("evidence.read", [identity])], "answer": None, "rsi": rsi()}
        else:
            value = final_answer("plan", "E002", "Synthetic source read; compatibility is still unknown.")
            claims = []
            if self.run.rsi_context["selected_policies"]:
                policy = self.run.rsi_context["selected_policies"][0]
                claims = [{"policy_id": policy["definition"]["policy_id"], "version": policy["definition"]["version"],
                           "content_sha256": policy["content_sha256"], "intent": "Synthetic search then read",
                           "action_refs": ["E001", "E002"], "output_refs": ["/recommended_next"]}]
            value["rsi"] = rsi(applications=self.claims(claims) if self.claims else claims,
                               improvement_candidates=self.candidates, observations=self.observations)
            if self.run.continuation:
                value["answer"]["progress"] = {"changes": [{"previous_ref": "F001", "assessment": "unchanged",
                    "statement": "Synthetic revalidation", "evidence_ids": ["E002"]}], "completed_checks": [],
                    "remaining_checks": [], "next_product": "Synthetic owner review"}
        self.messages = [{"method": "item/completed", "params": {"threadId": "thread", "turnId": turn,
            "item": {"id": turn, "type": "agentMessage", "phase": "final_answer", "text": json.dumps(value)}}},
            {"method": "turn/completed", "params": {"threadId": "thread", "turn": {"id": turn, "status": "completed"}}}]
        return {"turn": {"id": turn}}


def execute(run, **kwargs):
    run.bind_workspace(run.output.parent / "auth")
    run.drive(PolicyPeer(run, **kwargs), synthetic=True)
    receipt = run.finish()
    return receipt, load_json_object(run.output / "rsi_application.json")


def candidate(**updates):
    return {"source_type": "repeated_work", "source_refs": ["E002"], "problem": "Synthetic repeated preparation",
        "previous_behavior": "Repeat preparation", "behavior_change": "Inspect the registered build list first",
        "applicability": "New structure preparation", "limitations": "No compatibility proof", "expected_help": "Possible reuse",
        "added_burden": "One bounded check", "validation_task": "An unseen task", "evaluation": "Content review plus measured cost",
        "existing_candidate_id": None, "changes_policy_id": None, "related_ids": [], **updates}


def test_new_run_freezes_accepted_policy_and_records_real_host_correspondence(environment):
    propose(environment)
    run = run_for(environment, "fresh")
    receipt, record = execute(run)
    assert receipt["status"] == "OFFLINE_TEST_GENERATED"
    assert sha256_file(run.output / "rsi_application.json") == receipt["rsi_application"]["sha256"]
    assert record["selected_policies"][0]["provided"]
    assert record["selected_policies"][0]["model_inputs"][0]["synthetic"]
    assert record["applications"][0]["host_status"] == "observed_correspondence_needs_content_review"
    assert record["value"]["user_confirmed_help"] is None and record["value"]["controlled_benefit"] is None
    assert "本轮 RSI 使用记录" in (run.output / "review.md").read_text(encoding="utf-8")


def test_frozen_run_keeps_version_but_resume_reads_disabled_current_state_and_reuses_science(environment):
    record = propose(environment)
    run = run_for(environment, "parent")
    run.prepare_rsi()
    review(environment, environment[3], record, "disabled")
    execute(run)
    child = run_for(environment, "resume", parent=run)
    receipt, result = execute(child)
    assert not result["selected_policies"]
    assert receipt["host_actions_reused_from_parent"] == 2
    assert result["selection"]["not_selected"][0]["reason"] == "disabled"


def test_candidates_trials_unmatched_versions_duplicates_conflicts_and_budget(environment):
    propose(environment, status="candidate")
    assert not run_for(environment, "candidate").prompt_for(1)["rsi_context"]["selected_policies"]
    propose(environment, policy_id="trial", status="trial")
    assert len(run_for(environment, "trial", trial_policy_ids=["trial"]).prompt_for(1)["rsi_context"]["selected_policies"]) == 1
    propose(environment, policy_id="duplicate_a", equivalence_key="explicit-equivalent")
    propose(environment, policy_id="duplicate_b", equivalence_key="explicit-equivalent")
    propose(environment, policy_id="conflict_a", conflict_group="unresolved")
    propose(environment, policy_id="conflict_b", conflict_group="unresolved")
    run = run_for(environment, "selection", max_active_policies=1)
    run.prompt_for(1)
    context = run.rsi_selection
    assert len(context["selected_policies"]) == 1
    assert sum(r["reason"] == "unresolved_explicit_conflict" for r in context["not_selected"]) == 2
    assert any(r["reason"] == "explicit_or_exact_duplicate" for r in context["not_selected"])
    assert not run_for(environment, "irrelevant", goal="explain a unit conversion").prompt_for(1)["rsi_context"]["selected_policies"]
    zero = run_for(environment, "zero", max_active_policies=0).prompt_for(1)
    assert not zero["rsi_context"]["selected_policies"] and len(zero["registered_tools"]) == 11
    assert any("科学阈值" in line for line in zero["instructions"])


def test_new_candidate_version_does_not_displace_accepted_and_disabled_latest_never_falls_back(environment):
    propose(environment)
    newer = propose(environment, version=2, status="candidate")
    assert run_for(environment, "old").prompt_for(1)["rsi_context"]["selected_policies"][0]["definition"]["version"] == 1
    review(environment, {**environment[3], "version": 2}, newer, "disabled")
    assert not run_for(environment, "none").prompt_for(1)["rsi_context"]["selected_policies"]


@pytest.mark.parametrize("change", [
    {"policy_id": "invented"}, {"version": 999}, {"content_sha256": "wrong"},
    {"action_refs": ["E999"]}, {"action_refs": ["E002", "E001"]}, {"output_refs": ["/invented"]}, {"output_refs": ["/scientific_limits"]}])
def test_fabricated_or_misbound_applications_never_pass(environment, change):
    propose(environment)
    _, record = execute(run_for(environment, "forged"), claims=lambda rows: [{**rows[0], **change}])
    assert record["applications"][0]["host_status"] == "rejected"


def test_selected_without_claim_is_provided_but_not_applied(environment):
    propose(environment)
    _, record = execute(run_for(environment, "no-use"), claims=lambda _: [])
    assert record["selected_policies"][0]["provided"]
    assert record["applications"][0]["host_status"] == "not_observed"


def test_all_observations_preserved_one_new_candidate_and_exact_duplicates_add_sources(environment):
    first = run_for(environment, "proposals")
    observations = [{"source_type": "unmet_goal", "source_refs": ["E002"], "observation": "Synthetic capability gap"}]
    _, record = execute(first, candidates=[candidate(), candidate(problem="Another opportunity"), candidate(source_refs=["E999"])], observations=observations)
    assert [r["status"] for r in record["candidate_records"]] == ["observation", "candidate", "deferred_observation", "quarantined_observation"]
    second = run_for(environment, "repeat")
    execute(second, candidates=[candidate(), candidate(behavior_change="", validation_task="")])
    state = environment[2].read()
    assert len(state["candidates"]) == 1 and len(state["candidates"][0]["occurrences"]) == 2
    assert state["candidates"][0]["status"] == "candidate" and len(state["observations"]) == 6
    assert state["candidates"][0]["occurrences"][0]["bound_sources"]
    context = run_for(environment, "pending").prompt_for(1)["rsi_context"]
    assert len(context["pending_observations"]) == 2
    assert len(run_for(environment, "pending-auto", intent="auto").prompt_for(1)["rsi_context"]["pending_observations"]) == 2


def test_experimental_baseline_does_not_receive_excluded_rule_or_feedback(environment):
    propose(environment)
    policy_id = environment[3]["policy_id"]
    run = run_for(environment, "blind", exclude_policy_ids=[policy_id], include_pending_feedback=False)
    context = run.prompt_for(1)["rsi_context"]
    assert policy_id not in json.dumps(context) and environment[3]["behavior_change"] not in json.dumps(context)
    assert not context["pending_feedback"] and not context["pending_observations"]


def test_candidate_to_independent_review_to_daily_loading(environment):
    _, _, store, definition = environment
    execute(run_for(environment, "origin"), candidates=[candidate()])
    archived = store.read()["candidates"][0]
    proposal = {**deepcopy(definition), "behavior_change": archived["proposal"]["behavior_change"],
                "source_refs": [archived["occurrences"][0]["raw_ref"]], "proposer": "assistant"}
    record = store.propose(proposal, archived["candidate_id"])
    assert not run_for(environment, "before-review").prompt_for(1)["rsi_context"]["selected_policies"]
    evidence = environment[0] / "candidate-validation.json"
    write_json_exclusive(evidence, {"kind": "synthetic independent validation fixture"})
    review(environment, proposal, record, "accepted", evidence)
    assert store.read()["candidates"][0]["status"] == "accepted"
    assert run_for(environment, "after-review").prompt_for(1)["rsi_context"]["selected_policies"][0]["origin_candidate_id"] == archived["candidate_id"]


def test_later_tool_result_cannot_validate_an_earlier_invented_candidate_source(environment):
    _, record = execute(run_for(environment, "chronology"), early_candidates=[candidate(source_refs=["E001"])])
    assert record["candidate_records"][0]["status"] == "quarantined_observation"
    assert not environment[2].read()["candidates"]


def test_policy_status_cannot_be_promoted_by_mutating_the_projection(environment):
    propose(environment, status="trial")
    with environment[2].transaction() as state:
        state["policies"][0]["status"] = "accepted"
    with pytest.raises(ValueError, match="review binding"):
        environment[2].read()


def test_feedback_indexes_next_normal_run_without_backfilling_or_policy_acceptance(environment):
    propose(environment, status="candidate")
    parent = run_for(environment, "feedback-parent")
    execute(parent)
    input_hash = sha256_file(parent.output / "turn-001/model_input.json")
    early = run_for(environment, "already-frozen")
    early.prepare_rsi()
    path = environment[0] / "usage.json"
    write_json_exclusive(path, {"adopted": True, "evidence_effectiveness": [], "repeated_checks": [],
        "followup_notes": "Synthetic researcher correction after completion", "scientific_result_reference": None,
        "human_review_seconds": None, "human_preparation_seconds": None, "human_correction_seconds": None})
    source = feedback(parent.output, path)
    assert "rsi_index_error" not in source
    assert not early.prompt_for(1)["rsi_context"]["pending_feedback"]
    context = run_for(environment, "next-question").prompt_for(1)["rsi_context"]
    assert len(context["pending_feedback"]) == 1 and not context["selected_policies"]
    assert len(run_for(environment, "next-auto", intent="auto").prompt_for(1)["rsi_context"]["pending_feedback"]) == 1
    assert environment[2].read()["policies"][0]["status"] == "candidate"
    assert sha256_file(parent.output / "turn-001/model_input.json") == input_hash
    assert not run_for(environment, "control", include_pending_feedback=False).prompt_for(1)["rsi_context"]["pending_feedback"]


def test_concrete_help_is_separate_user_report_without_editing_receipt(environment):
    propose(environment)
    run = run_for(environment, "user-report")
    execute(run)
    before = sha256_file(run.output / "run_receipt.json")
    request_path = environment[0] / "helpful.json"
    write_json_exclusive(request_path, {"adopted": None, "evidence_effectiveness": [], "repeated_checks": [],
        "followup_notes": "Synthetic feedback fixture, not a real research benefit", "scientific_result_reference": None,
        "rsi_feedback": [{"policy_id": "check_registered_material", "helpful": True, "reason": "Synthetic concrete help fixture",
                          "action_refs": ["E002"], "output_refs": ["/recommended_next"]}]})
    feedback(run.output, request_path)
    record = usage_record(run.output)
    assert record["later_user_feedback"][0]["user_report"]["helpful"]
    assert record["value"]["controlled_benefit"] is None
    assert sha256_file(run.output / "run_receipt.json") == before
    comparison = environment[0] / "comparison.json"
    write_json_exclusive(comparison, {"untrusted_benefit_claim": True})
    (run.output / "comparisons").mkdir()
    write_json_exclusive(run.output / "comparisons" / "binding.json", {"run_receipt_sha256": before, "comparison_reference": ref(comparison)})
    view = usage_record(run.output)
    assert view["value"]["paired_comparison_refs"] == [ref(comparison)] and view["value"]["controlled_benefit"] is None


def test_configuration_lock_scope_and_legacy_protocol(environment):
    tmp, project, store, _ = environment
    with pytest.raises(ValueError, match="unsupported RSI"):
        settings(project, {"execute": "anything"})
    with pytest.raises(ValueError, match="unsupported RSI"):
        settings(project, [])
    with pytest.raises(ValueError, match="budget"):
        settings(project, {"max_presented_candidates": 2})
    with store.transaction():
        with pytest.raises(ValueError, match="locked"):
            with store.transaction():
                pass
    run = run_for(environment, "scope")
    with pytest.raises(ValueError, match="not a scientific evidence scope"):
        run.catalog.freeze(store.root / "state.json")
    validate_response(final_answer("plan"), {"E001": {}}, "plan")
    value = final_answer("plan")
    value["answer"].pop("progress")
    validate_response(value, {"E001": {}}, "plan", version="project_research_assistant_v1")
    assert set(response_schema()["properties"]["requests"]["items"]["properties"]) == {"tool", "target_ids", "query", "limit"}
    assert not (tmp / "unexpected-command").exists()
