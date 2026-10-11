"""Synthetic local review traces only: no real strategy acceptance or scientific evaluation."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import socket

import pytest

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json
from scripts.ts_strategy_engine import learning_cli, workflow_improvement as loop
from scripts.ts_strategy_engine.next_review import recommend_next_reviews, review_field_orders
from scripts.ts_strategy_engine.strategy_learning import policy


def reference(path):
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def observation(path, pointer, value):
    return {**reference(path), "pointer": pointer, "value": value}


def experiment(tmp_path, provenance="synthetic"):
    """Every generated file is a synthetic fixture, even when testing a real-mode boundary."""
    source = tmp_path / "synthetic-source.json"
    write_json(source, {"symptoms": ["fixture symptom 0", "fixture symptom 1", "fixture symptom 2"]})
    cases, answers, observations = [], [], []
    for index in range(3):
        case_id, task_id = f"case-{index}", f"synthetic-task-{index}"
        item = observation(source, f"/symptoms/{index}", f"fixture symptom {index}")
        observations.append(item)
        case = {"case_id": case_id, "group_id": task_id, "question": "Synthetic review?",
                "evidence": [{"evidence_id": "symptom", "pointer": item["pointer"],
                              "value": item["value"], "source_sha256": item["sha256"]}]}
        case["input_sha256"] = sha256_json(case)
        cases.append(case)
        unknown = index == 2
        answers.append({"case_id": case_id, "input_sha256": case["input_sha256"], "failure_class": "geometry",
                        "causal_status": "unknown" if unknown else "hypothesis",
                        "causal_claim": None if unknown else "Synthetic specific hypothesis",
                        "causal_evidence_ids": [] if unknown else ["symptom"], "evidence_ids": ["symptom"],
                        "next_review": policy()["failure_routes"]["geometry"]})
    public_path, answers_path = tmp_path / "public.json", tmp_path / "answers.json"
    public = {"schema_version": 2, "cases": cases}
    write_json(public_path, public)
    write_json(answers_path, {"schema_version": 2, "public_sha256": sha256_json(public), "answers": answers})
    store = tmp_path / "store"
    baseline_request = {"scope": "synthetic-review-trial", "provenance": provenance,
                        "inputs": {"public": reference(public_path), "answers": reference(answers_path)},
                        "observations": observations}
    p0 = loop.create_baseline(store, baseline_request)
    proposal = {"parent_id": p0["policy_id"], "scope": baseline_request["scope"],
                "changes": {"geometry": review_field_orders()["geometry"][::-1]},
                "rationale": "Synthetic hypothesis: earlier review reduces recorded review actions",
                "observations": observations, "evaluation_contract": {
                    "method": loop.METHOD, "rules": loop.RULES,
                    "tasks": [{"case_id": c["case_id"], "task_id": c["group_id"], "input_sha256": c["input_sha256"],
                               "required_checks": ["diagnostic_priority_preserved", "necessary_checks_retained"]} for c in cases]}}
    p1 = loop.propose_policy(store, proposal)
    return {"root": tmp_path, "store": store, "p0": p0, "p1": p1, "proposal": proposal, "baseline": baseline_request,
            "public": public_path, "answers": answers_path, "public_hash": sha256_json(public)}


def advice(env, identity=None, *, offline=False, name="advice.json", scope=None):
    options = {} if identity is None else {"workflow_store": env["store"], "workflow_policy": identity,
                                          "workflow_scope": scope or env["baseline"]["scope"], "offline_evaluation": offline}
    return recommend_next_reviews(env["public"], env["answers"], env["root"] / name, env["public_hash"], **options)


def evaluation(env, candidate_counts=(2, 2), candidate_check=True, parent_counts=(3, 3)):
    """Saved paired traces and scalar raw observations, explicitly synthetic fixtures."""
    directory = env["root"] / "synthetic-evaluation"
    directory.mkdir()
    pairs = []
    for name in ("parent", "candidate"):
        identity = env["p0" if name == "parent" else "p1"]["policy_id"]
        report_name = f"synthetic-evaluation/{name}-advice.json"
        report = advice(env, identity, offline=True, name=report_name)
        report_path = env["root"] / report_name
        for index, task in enumerate(env["proposal"]["evaluation_contract"]["tasks"]):
            fields = report["recommendations"][index]["ts_strategy_fields_to_review"]
            count = (parent_counts[index] if name == "parent" else candidate_counts[index]) if fields else 0
            order = [fields[0]] * (count - 1) + [fields[-1]] if fields else []
            raw = directory / f"{name}-{index}-raw.json"
            context = {"schema_version": 2, "provenance": env["baseline"]["provenance"], "policy_id": identity,
                     "scope": env["baseline"]["scope"], "contract_sha256": env["p1"]["contract_sha256"],
                     **{key: task[key] for key in ("case_id", "task_id", "input_sha256")}}
            write_json(raw, {**context,
                             "actions": [{"event_id": f"{name}-{index}-{j}", "sequence": j, "field": field,
                                          "result": f"synthetic recorded action {j}"} for j, field in enumerate(order)],
                             "checks": [{"check_id": key, "result": True if name == "parent" else candidate_check}
                                        for key in task["required_checks"]]})
            trace = {**context, "advice": reference(report_path), "source": reference(raw),
                     "actions": [{"event_id": f"{name}-{index}-{j}", "field": field,
                                  "observation": observation(raw, f"/actions/{j}/result", f"synthetic recorded action {j}")}
                                 for j, field in enumerate(order)],
                     "checks": [{"check_id": key, "observation": observation(raw, f"/checks/{j}/result",
                                                                                 True if name == "parent" else candidate_check)}
                                for j, key in enumerate(task["required_checks"])]}
            trace_path = directory / f"{name}-{index}.json"
            write_json(trace_path, trace)
            if name == "parent":
                pairs.append({"case_id": task["case_id"], "parent": reference(trace_path)})
            else:
                pairs[index]["candidate"] = reference(trace_path)
    request = {"schema_version": 2, "candidate_id": env["p1"]["policy_id"], "parent_id": env["p0"]["policy_id"],
               "scope": env["baseline"]["scope"], "contract_sha256": env["p1"]["contract_sha256"],
               "provenance": env["baseline"]["provenance"], "pairs": pairs}
    path = directory / "evaluation.json"
    write_json(path, request)
    return path


def decide(env, result, action="ACCEPT"):
    return {"candidate_id": env["p1"]["policy_id"], "evaluation_id": result["evaluation_id"], "decision": action,
            "reviewer": "synthetic fixture human", "reason": "Synthetic fixture decision, no real acceptance",
            "actor_kind": "synthetic_fixture"}


def test_end_to_end_synthetic_loop(tmp_path):
    env = experiment(tmp_path)
    assert env["p1"]["status"] == "WAITING_FOR_EVALUATION"
    assert env["p1"]["comparison"] is None and env["p1"]["evaluation_id"] is None
    assert loop.propose_policy(env["store"], env["proposal"]) == env["p1"]
    baseline = advice(env)
    candidate = advice(env, env["p1"]["policy_id"], offline=True, name="preview.json")
    assert baseline["recommendations"][0]["ts_strategy_fields_to_review"] == review_field_orders()["geometry"]
    assert candidate["recommendations"][0]["ts_strategy_fields_to_review"] == review_field_orders()["geometry"][::-1]
    assert candidate["recommendations"][2]["ts_strategy_fields_to_review"] == []
    for before, after in zip(baseline["recommendations"], candidate["recommendations"]):
        assert {k: v for k, v in before.items() if k != "ts_strategy_fields_to_review"} == \
            {k: v for k, v in after.items() if k != "ts_strategy_fields_to_review"}
    path = evaluation(env)
    reviewed = loop.bind_evaluation(env["store"], reference(path))
    assert reviewed["status"] == "AWAITING_HUMAN_REVIEW"
    assert reviewed["comparison"]["scientific_success"] == "NOT_EVALUATED"
    assert reviewed["comparison"]["compute_cost"] == "NOT_MEASURED"
    assert loop.bind_evaluation(env["store"], reference(path)) == reviewed
    accepted = loop.record_decision(env["store"], decide(env, reviewed))
    assert accepted["status"] == "ACCEPTED" and accepted["provenance"] == "synthetic"
    assert loop.record_decision(env["store"], decide(env, reviewed)) == accepted
    selected = advice(env, accepted["policy_id"], offline=True, name="accepted.json")
    assert selected["workflow_strategy"]["policy_id"] == accepted["policy_id"]
    assert selected["recommendations"][0]["ts_strategy_fields_to_review"] == env["proposal"]["changes"]["geometry"]
    next_proposal = {**env["proposal"], "parent_id": accepted["policy_id"], "changes": {"geometry": review_field_orders()["geometry"]}}
    p2 = loop.propose_policy(env["store"], next_proposal)
    assert p2["policy_id"] != accepted["policy_id"] and p2["status"] == "WAITING_FOR_EVALUATION"
    with pytest.raises(ValueError, match="stale parent"):
        loop.propose_policy(env["store"], env["proposal"])
    with pytest.raises(ValueError, match="conflicting"):
        loop.record_decision(env["store"], decide(env, reviewed, "REJECT"))
    assert len(list((env["store"] / "evaluations").glob("*.json"))) == 1
    assert len(list((env["store"] / "decisions").glob("*.json"))) == 1


def test_pending_and_rejected_never_change_default(tmp_path):
    env = experiment(tmp_path)
    with pytest.raises(ValueError, match="offline"):
        advice(env, env["p1"]["policy_id"])
    with pytest.raises(ValueError, match="not human-accepted"):
        loop.propose_policy(env["store"], {**env["proposal"], "parent_id": env["p1"]["policy_id"]})
    with pytest.raises(ValueError, match="no eligible"):
        loop.record_decision(env["store"], decide(env, env["p1"]))
    rejected = loop.record_decision(env["store"], decide(env, env["p1"], "REJECT"))
    assert rejected["status"] == "REJECTED"
    with pytest.raises(ValueError, match="rejected"):
        advice(env, env["p1"]["policy_id"], offline=True)
    assert "workflow_strategy" not in advice(env)


@pytest.mark.parametrize("changes", [{}, {"geometry": ["initial_images"]}, {"geometry": ["initial_images", "initial_images"]},
                                    {"execution_gate": ["RUN"]}, {"initial_images": 13}, {"scientific_threshold": 0},
                                    {"geometry": ["initial_images", "execute_python"]},
                                    {"geometry": review_field_orders()["geometry"]},
                                    {"geometry": review_field_orders()["geometry"][::-1], "optimizer": ["candidate_method"]}])
def test_only_one_existing_order_permutation_allowed(tmp_path, changes):
    env = experiment(tmp_path)
    with pytest.raises(ValueError):
        loop.propose_policy(env["store"], {**env["proposal"], "changes": changes})
    assert len(list((env["store"] / "policies").glob("*.json"))) == 2


@pytest.mark.parametrize("counts,check", [((2, 4), True), ((3, 3), True), ((2, 2), False)])
def test_no_aggregate_masking_or_automatic_promotion(tmp_path, counts, check):
    env = experiment(tmp_path)
    result = loop.bind_evaluation(env["store"], reference(evaluation(env, counts, check)))
    assert result["status"] == "NOT_SUPPORTED"
    with pytest.raises(ValueError, match="no eligible"):
        loop.record_decision(env["store"], decide(env, result))
    assert "workflow_strategy" not in advice(env)


@pytest.mark.parametrize("damage", ["task", "version", "input", "contract", "stale_trace", "stale_raw", "order",
                                    "duplicate_event", "wrong_advice", "wrong_type", "duplicate_case", "improved_flag"])
def test_corrupt_evaluation_rejected(tmp_path, damage):
    env = experiment(tmp_path)
    path = evaluation(env)
    request = load_json_object(path)
    ref = request["pairs"][0]["candidate"]
    trace_path = Path(ref["path"])
    trace = load_json_object(trace_path)
    if damage in {"task", "version", "input", "contract"}:
        key = {"task": "task_id", "version": "policy_id", "input": "input_sha256", "contract": "contract_sha256"}[damage]
        trace[key] = "wrong" if damage == "task" else "a" * 64
    elif damage == "stale_trace":
        trace["scope"] = "changed"
    elif damage == "stale_raw":
        raw = Path(trace["actions"][0]["observation"]["path"])
        write_json(raw, {"tampered": True})
    elif damage == "order":
        trace["actions"].reverse()
    elif damage == "duplicate_event":
        trace["actions"][1]["event_id"] = trace["actions"][0]["event_id"]
    elif damage == "wrong_advice":
        trace["advice"] = reference(env["root"] / "synthetic-evaluation/parent-advice.json")
    elif damage == "wrong_type":
        trace["checks"][0]["observation"]["value"] = 1
    elif damage == "duplicate_case":
        request["pairs"].append(deepcopy(request["pairs"][0]))
    else:
        request = {"improved": True, "candidate_id": env["p1"]["policy_id"]}
    write_json(trace_path, trace)
    if damage != "stale_trace":
        ref.update(reference(trace_path))
    write_json(path, request)
    with pytest.raises(ValueError):
        loop.bind_evaluation(env["store"], reference(path))
    assert not (env["store"] / "evaluations" / f"{env['p1']['policy_id']}.json").exists()


@pytest.mark.parametrize("missing", ["pair", "trace", "checks", "actions", "null_check"])
def test_missing_measurements_are_gaps_not_zero_or_success(tmp_path, missing):
    env = experiment(tmp_path)
    path = evaluation(env)
    request = load_json_object(path)
    if missing == "pair":
        request["pairs"].pop()
    elif missing == "trace":
        request["pairs"][0]["candidate"] = None
    else:
        ref = request["pairs"][0]["candidate"]
        trace_path = Path(ref["path"])
        trace = load_json_object(trace_path)
        if missing == "null_check":
            item = trace["checks"][0]["observation"]
            raw = Path(item["path"])
            data = load_json_object(raw)
            data["checks"][0]["result"] = None
            write_json(raw, data)
            for check in trace["checks"]:
                check["observation"].update(reference(raw))
            for action in trace["actions"]:
                action["observation"].update(reference(raw))
            trace["source"] = reference(raw)
            item["value"] = None
        else:
            trace[missing] = []
        write_json(trace_path, trace)
        ref.update(reference(trace_path))
    write_json(path, request)
    result = loop.bind_evaluation(env["store"], reference(path))
    assert result["status"] == "NEEDS_MORE_EVIDENCE" and result["evidence_gaps"]
    assert result["evaluation_id"] is None
    assert loop.policy_status(env["store"], env["p1"]["policy_id"])["status"] == "WAITING_FOR_EVALUATION"


def test_real_mode_requires_acceptance(tmp_path):
    # Synthetic files exercise the saved-real pending boundary; no real/simulated ACCEPT is made here.
    env = experiment(tmp_path, provenance="saved_real")
    with pytest.raises(ValueError, match="not human-accepted"):
        advice(env, env["p1"]["policy_id"])
    loop.bind_evaluation(env["store"], reference(evaluation(env)))
    with pytest.raises(ValueError, match="not human-accepted"):
        advice(env, env["p1"]["policy_id"])


def test_synthetic_acceptance_remains_offline_scoped_and_source_bound(tmp_path):
    env = experiment(tmp_path)
    result = loop.bind_evaluation(env["store"], reference(evaluation(env)))
    loop.record_decision(env["store"], decide(env, result))
    with pytest.raises(ValueError, match="offline"):
        advice(env, env["p1"]["policy_id"])
    selected = advice(env, env["p1"]["policy_id"], offline=True)
    assert selected["workflow_strategy"]["mode"] == "offline_evaluation"
    with pytest.raises(ValueError, match="scope/task/input"):
        advice(env, env["p1"]["policy_id"], scope="wrong", offline=True, name="bad-scope.json")
    raw = env["root"] / "synthetic-evaluation/candidate-0-raw.json"
    write_json(raw, {"changed": True})
    with pytest.raises(ValueError, match="stale"):
        advice(env, env["p1"]["policy_id"], offline=True, name="stale.json")


def test_stale_parent_and_conflicting_bindings_fail(tmp_path, monkeypatch):
    env = experiment(tmp_path)
    with pytest.raises(ValueError):
        loop.record_decision(env["store"], {**decide(env, env["p1"], "REJECT"), "evaluation_id": "a" * 64})
    with pytest.raises(ValueError):
        loop.propose_policy(env["store"], {**env["proposal"], "parent_id": "a" * 64})
    engine = loop._engine()
    monkeypatch.setattr(loop, "_engine", lambda: {**engine, "policy_sha256": "a" * 64})
    with pytest.raises(ValueError, match="stale"):
        loop.propose_policy(env["store"], env["proposal"])


def test_duplicate_order_and_conflicting_evaluation_are_rejected(tmp_path):
    env = experiment(tmp_path)
    with pytest.raises(ValueError, match="duplicate candidate order"):
        loop.propose_policy(env["store"], {**env["proposal"], "rationale": "Same change with different wording"})
    path = evaluation(env)
    original = loop.bind_evaluation(env["store"], reference(path))
    copy_path = path.with_name("another-evaluation.json")
    write_json(copy_path, load_json_object(path))
    with pytest.raises(ValueError, match="conflicting"):
        loop.bind_evaluation(env["store"], reference(copy_path))
    assert loop.policy_status(env["store"], env["p1"]["policy_id"])["evaluation_id"] == original["evaluation_id"]


def test_bound_contract_and_policy_tampering(tmp_path):
    env = experiment(tmp_path)
    proposal = deepcopy(env["proposal"])
    proposal["evaluation_contract"]["rules"]["no_per_task_regression"] = 1
    with pytest.raises(ValueError, match="rules"):
        loop.propose_policy(env["store"], proposal)
    proposal = deepcopy(env["proposal"])
    proposal["evaluation_contract"]["tasks"][0]["task_id"] = "other-task"
    with pytest.raises(ValueError, match="identity"):
        loop.propose_policy(env["store"], proposal)
    policy_path = Path(env["p1"]["policy_path"])
    candidate = load_json_object(policy_path)
    candidate["rationale"] = "Tampered in place"
    write_json(policy_path, candidate)
    with pytest.raises(ValueError, match="policy identity"):
        advice(env, env["p1"]["policy_id"], offline=True)


def test_selection_rejects_different_answer_and_missing_explicit_flags(tmp_path):
    env = experiment(tmp_path)
    another = tmp_path / "other-answers.json"
    answers = load_json_object(env["answers"])
    answers["answers"][0]["causal_claim"] = "Different specific hypothesis"
    write_json(another, answers)
    with pytest.raises(ValueError, match="scope/task/input"):
        recommend_next_reviews(env["public"], another, tmp_path / "wrong-answer.json", env["public_hash"],
                               workflow_store=env["store"], workflow_policy=env["p1"]["policy_id"],
                               workflow_scope=env["baseline"]["scope"], offline_evaluation=True)
    with pytest.raises(ValueError, match="explicit store"):
        recommend_next_reviews(env["public"], env["answers"], tmp_path / "flags.json", env["public_hash"], offline_evaluation=True)


def test_cli_end_to_end_has_no_database_model_or_execution_calls(tmp_path, monkeypatch, capsys):
    env = experiment(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("workflow improvement must never call a model, SSH, executor or registry")
    monkeypatch.setattr("scripts.registry_connection.open_registry", forbidden)
    monkeypatch.setattr(learning_cli, "read_events", forbidden)
    monkeypatch.setattr(learning_cli, "start_vasp_attempt", forbidden)
    monkeypatch.setattr("scripts.ts_strategy_engine.execution_gate.decide_execution", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    # Run every public operation, rather than calling the module functions only.
    def command(name, request):
        request_path = tmp_path / f"{name}.json"
        write_json(request_path, request)
        learning_cli.main([name, "--store", str(env["store"]), "--request", str(request_path)])
        return json.loads(capsys.readouterr().out)
    assert command("workflow-baseline", env["baseline"])["policy_id"] == env["p0"]["policy_id"]
    assert command("workflow-propose", env["proposal"])["status"] == "WAITING_FOR_EVALUATION"
    learning_cli.main(["workflow-status", "--store", str(env["store"]), "--policy-id", env["p1"]["policy_id"]])
    assert json.loads(capsys.readouterr().out)["comparison"] is None
    path = evaluation(env)
    learning_cli.main(["workflow-bind-evaluation", "--store", str(env["store"]), "--request", str(path)])
    result = json.loads(capsys.readouterr().out)
    accepted = command("workflow-decide", decide(env, result))
    learning_cli.main(["advise-next", "--public", str(env["public"]), "--answers", str(env["answers"]),
                       "--expected-public-sha256", env["public_hash"], "--report", str(tmp_path / "cli-advice.json"),
                       "--workflow-store", str(env["store"]), "--workflow-policy", accepted["policy_id"],
                       "--workflow-scope", env["baseline"]["scope"], "--offline-evaluation"])
    assert json.loads(capsys.readouterr().out)["recommendations"][0]["ts_strategy_fields_to_review"] == \
        env["proposal"]["changes"]["geometry"]
    next_request = {**env["proposal"], "parent_id": accepted["policy_id"], "changes": {"geometry": review_field_orders()["geometry"]}}
    assert command("workflow-propose", next_request)["status"] == "WAITING_FOR_EVALUATION"
    assert not list(tmp_path.rglob("*.sqlite*"))


def test_outer_learning_entrypoint_exposes_workflow_commands():
    result = subprocess.run([sys.executable, "-m", "scripts.ts_strategy_engine.cli", "learning", "--help"],
                            capture_output=True, text=True, check=True)
    assert "workflow-propose" in result.stdout and "workflow-decide" in result.stdout


@pytest.mark.parametrize("damage", ["relabeled_duplicate", "foreign_raw"])
def test_raw_source_ownership_and_duplicate_counts_are_rejected(tmp_path, damage):
    env = experiment(tmp_path)
    path = evaluation(env)
    request = load_json_object(path)
    trace_path = Path(request["pairs"][0]["parent"]["path"])
    trace = load_json_object(trace_path)
    raw_path = Path(trace["actions"][0]["observation"]["path"])
    raw = load_json_object(raw_path)
    if damage == "relabeled_duplicate":
        raw["actions"].pop(1)
        if isinstance(raw["actions"][1], dict):
            raw["actions"][1]["sequence"] = 1
        write_json(raw_path, raw)
        for action, index in zip(trace["actions"], (0, 0, 1)):
            value = raw["actions"][index]
            suffix = "/result" if isinstance(value, dict) else ""
            action["observation"] = observation(raw_path, f"/actions/{index}{suffix}",
                                                value["result"] if isinstance(value, dict) else value)
        trace["actions"][1]["event_id"] = "relabeled-same-original-action"
    else:
        raw.update({"task_id": "foreign-task", "case_id": "foreign-case", "policy_id": "a" * 64,
                    "input_sha256": "b" * 64, "contract_sha256": "c" * 64, "scope": "foreign-scope"})
        write_json(raw_path, raw)
        for action in trace["actions"]:
            action["observation"].update(reference(raw_path))
    for check in trace["checks"]:
        check["observation"].update(reference(raw_path))
    if "source" in trace:
        trace["source"] = reference(raw_path)
    write_json(trace_path, trace)
    request["pairs"][0]["parent"] = reference(trace_path)
    write_json(path, request)
    with pytest.raises(ValueError):
        loop.bind_evaluation(env["store"], reference(path))
    assert not (env["store"] / "evaluations" / f"{env['p1']['policy_id']}.json").exists()


def save_changed_pair(path, request, side, trace_path, trace, raw_path=None, raw=None):
    if raw_path is not None:
        write_json(raw_path, raw)
        trace["source"] = reference(raw_path)
        for item in trace["actions"] + trace["checks"]:
            item["observation"].update(reference(raw_path))
    write_json(trace_path, trace)
    request["pairs"][0][side] = reference(trace_path)
    write_json(path, request)


@pytest.mark.parametrize("key", ["case_id", "task_id", "policy_id", "input_sha256", "contract_sha256", "scope", "provenance"])
def test_each_raw_source_identity_must_match_the_trace(tmp_path, key):
    env = experiment(tmp_path)
    path = evaluation(env)
    request = load_json_object(path)
    trace_path = Path(request["pairs"][0]["candidate"]["path"])
    trace = load_json_object(trace_path)
    raw_path = Path(trace["source"]["path"])
    raw = load_json_object(raw_path)
    raw[key] = "foreign-identity"
    save_changed_pair(path, request, "candidate", trace_path, trace, raw_path, raw)
    with pytest.raises(ValueError, match="identity mismatch"):
        loop.bind_evaluation(env["store"], reference(path))


@pytest.mark.parametrize("kind", ["actions", "checks"])
def test_foreign_action_or_check_cannot_borrow_correct_outer_identity(tmp_path, kind):
    env = experiment(tmp_path)
    path = evaluation(env)
    request = load_json_object(path)
    trace_path = Path(request["pairs"][0]["candidate"]["path"])
    trace = load_json_object(trace_path)
    raw = load_json_object(Path(trace["source"]["path"]))
    raw["task_id"] = "other-task"
    foreign_path = tmp_path / "foreign-raw.json"
    write_json(foreign_path, raw)
    trace[kind][0]["observation"].update(reference(foreign_path))
    save_changed_pair(path, request, "candidate", trace_path, trace)
    with pytest.raises(ValueError, match="bound original event"):
        loop.bind_evaluation(env["store"], reference(path))


@pytest.mark.parametrize("damage", ["event_id", "field", "sequence", "sequence_bool", "duplicate_raw_id", "check_id", "check_bool"])
def test_raw_event_identity_order_and_check_types_are_checked(tmp_path, damage):
    env = experiment(tmp_path)
    path = evaluation(env)
    request = load_json_object(path)
    trace_path = Path(request["pairs"][0]["candidate"]["path"])
    trace = load_json_object(trace_path)
    raw_path = Path(trace["source"]["path"])
    raw = load_json_object(raw_path)
    if damage == "event_id":
        raw["actions"][0]["event_id"] = "different-original-event"
    elif damage == "field":
        raw["actions"][0]["field"] = raw["actions"][1]["field"]
    elif damage.startswith("sequence"):
        raw["actions"][0]["sequence"] = False if damage == "sequence_bool" else 9
    elif damage == "duplicate_raw_id":
        raw["actions"][1]["event_id"] = raw["actions"][0]["event_id"]
    elif damage == "check_id":
        raw["checks"][0]["check_id"] = "foreign-check"
    else:
        raw["checks"][0]["result"] = 1
        trace["checks"][0]["observation"]["value"] = 1
    save_changed_pair(path, request, "candidate", trace_path, trace, raw_path, raw)
    with pytest.raises(ValueError):
        loop.bind_evaluation(env["store"], reference(path))


def test_same_source_event_copied_to_another_path_cannot_count_twice(tmp_path):
    env = experiment(tmp_path)
    path = evaluation(env)
    request = load_json_object(path)
    trace_path = Path(request["pairs"][0]["parent"]["path"])
    trace = load_json_object(trace_path)
    alias = tmp_path / "raw-path-alias.json"
    alias.write_bytes(Path(trace["source"]["path"]).read_bytes())
    trace["actions"][1]["observation"] = {**trace["actions"][0]["observation"], **reference(alias)}
    save_changed_pair(path, request, "parent", trace_path, trace)
    with pytest.raises(ValueError, match="bound original event"):
        loop.bind_evaluation(env["store"], reference(path))


@pytest.mark.parametrize("parent_counts,status", [((3, 3), "AWAITING_HUMAN_REVIEW"), ((2, 2), "NOT_SUPPORTED")])
def test_equal_text_from_distinct_events_counts_independently(tmp_path, parent_counts, status):
    env = experiment(tmp_path)
    path = evaluation(env, parent_counts=parent_counts)
    request = load_json_object(path)
    for pair in request["pairs"]:
        for side in ("parent", "candidate"):
            trace_path = Path(pair[side]["path"])
            trace = load_json_object(trace_path)
            raw_path = Path(trace["source"]["path"])
            raw = load_json_object(raw_path)
            for action in raw["actions"]:
                action["result"] = "same text, independent event identities"
            write_json(raw_path, raw)
            trace["source"] = reference(raw_path)
            for action in trace["actions"]:
                action["observation"].update(reference(raw_path))
                action["observation"]["value"] = "same text, independent event identities"
            for check in trace["checks"]:
                check["observation"].update(reference(raw_path))
            write_json(trace_path, trace)
            pair[side] = reference(trace_path)
    write_json(path, request)
    result = loop.bind_evaluation(env["store"], reference(path))
    assert result["status"] == status
    assert result["comparison"]["tasks"][0]["parent"]["review_actions"] == parent_counts[0]
    assert result["comparison"]["tasks"][0]["candidate"]["review_actions"] == 2


def test_full_field_coverage_cannot_hide_an_omitted_original_action(tmp_path):
    env = experiment(tmp_path)
    path = evaluation(env)
    request = load_json_object(path)
    trace_path = Path(request["pairs"][0]["parent"]["path"])
    trace = load_json_object(trace_path)
    raw_path = Path(trace["source"]["path"])
    raw = load_json_object(raw_path)
    raw["actions"][1]["field"] = raw["actions"][2]["field"]
    trace["actions"][1]["field"] = raw["actions"][1]["field"]
    trace["actions"].pop()
    save_changed_pair(path, request, "parent", trace_path, trace, raw_path, raw)
    result = loop.bind_evaluation(env["store"], reference(path))
    assert result["status"] == "NEEDS_MORE_EVIDENCE" and result["evaluation_id"] is None


@pytest.mark.parametrize("kind", ["evaluation", "trace", "raw", "unbound_raw"])
def test_legacy_or_unbound_records_are_not_given_invented_metadata(tmp_path, kind):
    env = experiment(tmp_path)
    path = evaluation(env)
    request = load_json_object(path)
    if kind == "evaluation":
        request["schema_version"] = 1
        write_json(path, request)
    else:
        trace_path = Path(request["pairs"][0]["candidate"]["path"])
        trace = load_json_object(trace_path)
        if kind == "trace":
            trace["schema_version"] = 1
            save_changed_pair(path, request, "candidate", trace_path, trace)
        else:
            raw_path = Path(trace["source"]["path"])
            raw = load_json_object(raw_path)
            if kind == "raw":
                raw["schema_version"] = 1
            else:
                del raw["policy_id"]
            save_changed_pair(path, request, "candidate", trace_path, trace, raw_path, raw)
    original_hash = sha256_file(path)
    with pytest.raises(ValueError):
        loop.bind_evaluation(env["store"], reference(path))
    assert sha256_file(path) == original_hash
