"""Synthetic local snapshots for temporal replay; no production database or runner."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json
from scripts.ts_strategy_engine import learning_cli
from scripts.ts_strategy_engine.historical_replay import replay_history
from scripts.ts_strategy_engine.next_review import recommend_next_reviews


def observation(path, pointer):
    value = load_json_object(path)
    for token in pointer[1:].split("/"):
        value = value[token]
    return {"path": str(path), "sha256": sha256_file(path), "pointer": pointer, "value": value}


def event(path, name):
    return {"event_id": name, "at": observation(path, "/at"),
            "job": observation(path, "/job"), "fact": observation(path, "/fact")}


def freeze(root, spec, public, answers):
    for case, answer in zip(public["cases"], answers["answers"], strict=True):
        case["input_sha256"] = sha256_json({k: v for k, v in case.items() if k != "input_sha256"})
        answer["input_sha256"] = case["input_sha256"]
    answers["public_sha256"] = sha256_json(public)
    write_json(root / "public.json", public)
    write_json(root / "answers.json", answers)
    advice_path = root / "new-advice.json"
    # Each generated Phase 3B artifact has a fresh path, including negative-test fixtures.
    for index in range(100):
        advice_path = root / f"advice-{index}.json"
        if not advice_path.exists():
            break
    recommend_next_reviews(root / "public.json", root / "answers.json", advice_path, sha256_json(public))
    for name, path in [("public", root / "public.json"), ("answers", root / "answers.json"), ("advice", advice_path)]:
        spec[name] = {"path": str(path), "sha256": sha256_file(path)}
    write_json(root / "replay.json", spec)
    return root / "replay.json"


def sample(root, suffix="1", hour="01", *, value="execution denied", background=None):
    root.mkdir(exist_ok=True)
    def save(name, value):
        path = root / f"{name}.json"
        write_json(path, value)
        return path
    failure = save("failure", {"task": "task-1", "job": f"failure-{suffix}", "symptom": value})
    decision_data = {"at": f"2026-08-29T{hour}:19:00+08:00", "job": f"failure-{suffix}",
                     "fact": "review runtime", "request": "a" * 64, "failure_sha256": sha256_file(failure)}
    if background is not None:
        shared = save(background, {"value": 400.0 if background == "config" else "a" * 64})
        decision_data["background_sha256"] = sha256_file(shared)
    decision = save("decision", decision_data)
    auth = save("auth", {"at": f"2026-08-29T{hour}:18:30+08:00", "job": f"failure-{suffix}",
                         "fact": True, "task": "task-1"})
    action = save("action", {"at": f"2026-08-29T{hour}:20:30+08:00", "job": f"retry-{suffix}",
                             "fact": "recorded corrected retry", "task": "task-1",
                             "parent": sha256_file(decision), "auth": sha256_file(auth)})
    after = save("after", {"at": f"2026-08-29T{hour}:31:44+08:00", "job": f"retry-{suffix}",
                           "fact": "producer completed; path not accepted", "force_calls": 4})
    classification = save("classification", {"task_id": "task-1", "outcome": {
        "status": "failure", "failure_class": "runtime", "observations": [{"sha256": sha256_file(failure)}]}})
    source = observation(failure, "/symptom")
    case = {"case_id": f"c{suffix}", "group_id": "task-1", "question": "What needs review?",
            "evidence": [{"evidence_id": "e1", "pointer": source["pointer"], "value": source["value"],
                          "source_sha256": source["sha256"]}]}
    answer = {"case_id": f"c{suffix}", "failure_class": "runtime", "causal_claim": None,
              "causal_status": "unknown", "causal_evidence_ids": [], "evidence_ids": ["e1"],
              "next_review": "repair_runtime_without_training"}
    trace = {"case_id": f"c{suffix}", "decision": event(decision, f"decision-{suffix}"),
             "task": observation(failure, "/task"), "failure_job": observation(failure, "/job"),
             "request": observation(decision, "/request"),
             "evidence": [{"evidence_id": "e1", "source": source,
                           "links": [observation(decision, "/failure_sha256")]}],
             "action": event(action, f"action-{suffix}"), "action_parent": observation(action, "/parent"),
             "action_task": observation(action, "/task"), "authorization": {
                 "event": event(auth, f"authorization-{suffix}"), "binding": observation(action, "/auth"),
                 "task": observation(auth, "/task")},
             "after": [event(after, f"after-{suffix}")], "costs": [observation(after, "/force_calls")],
             "recorded_classification": observation(classification, "/outcome/failure_class")}
    if background is not None:
        source = observation(shared, "/value")
        case["evidence"].append({"evidence_id": "e2", "pointer": source["pointer"], "value": source["value"],
                                 "source_sha256": source["sha256"]})
        trace["evidence"].append({"evidence_id": "e2", "source": source,
                                  "links": [observation(decision, "/background_sha256")]})
        answer["evidence_ids"].append("e2")
    spec = {"schema_version": 1, "traces": [trace], "unreplayable": []}
    public, answers = {"schema_version": 2, "cases": [case]}, {"schema_version": 2, "answers": [answer]}
    path = freeze(root, spec, public, answers)
    return path, spec, public, answers


def run(path, root):
    return replay_history(path, root / "report.json", sha256_file(path))


@pytest.mark.parametrize("original,changed", [
    (False, 0), (0, False), (True, 1), (1, True), (1, 1.0), (1.0, 1),
])
def test_public_evidence_requires_strict_json_types(tmp_path, original, changed):
    normal = tmp_path / "normal"
    path, _, _, _ = sample(normal, value=original)
    assert run(path, normal)["records"][0]["route_matches_recorded_classification"] is True

    altered = tmp_path / "altered"
    _, spec, public, answers = sample(altered, value=original)
    source_sha = sha256_file(altered / "failure.json")
    witness_sha = sha256_file(altered / "decision.json")
    public["cases"][0]["evidence"][0]["value"] = changed
    path = freeze(altered, spec, public, answers)
    assert sha256_file(altered / "failure.json") == source_sha
    assert sha256_file(altered / "decision.json") == witness_sha
    with pytest.raises(ValueError, match="source differs from frozen public evidence"):
        run(path, altered)
    assert not (altered / "report.json").exists()


@pytest.mark.parametrize("background", ["config", "request"])
@pytest.mark.parametrize("failure_class", ["runtime", "optimizer"])
def test_shared_background_cannot_bind_another_failure(tmp_path, background, failure_class):
    _, spec, public, answers = sample(tmp_path, background=background)
    other = tmp_path / "other-failure.json"
    write_json(other, {"task": "task-1", "job": "failure-OTHER", "symptom": "optimizer exhausted"})
    classification = tmp_path / "foreign-classification.json"
    write_json(classification, {"task_id": "task-1", "attempt_id": "failure-OTHER", "outcome": {
        "status": "failure", "failure_class": failure_class,
        "observations": [observation(other, "/symptom"), observation(tmp_path / f"{background}.json", "/value")]}})
    spec["traces"][0]["recorded_classification"] = observation(classification, "/outcome/failure_class")
    if failure_class == "optimizer":
        answers["answers"][0].update(failure_class="optimizer", next_review="diagnose_optimizer_and_path",
                                     causal_status="hypothesis", causal_claim="Optimizer cause to test",
                                     causal_evidence_ids=["e1"])
    path = freeze(tmp_path, spec, public, answers)
    with pytest.raises(ValueError, match="lacks this failure's source binding"):
        run(path, tmp_path)
    assert not (tmp_path / "report.json").exists()


@pytest.mark.parametrize("background", ["config", "request"])
def test_exact_failure_binding_accepts_shared_background_and_import_attempt_id(tmp_path, background):
    path, spec, _, _ = sample(tmp_path, background=background)
    classification = load_json_object(tmp_path / "classification.json")
    classification["attempt_id"] = "historical-import-1"
    classification["outcome"]["observations"].append(observation(tmp_path / f"{background}.json", "/value"))
    write_json(tmp_path / "classification.json", classification)
    spec["traces"][0]["recorded_classification"] = observation(tmp_path / "classification.json", "/outcome/failure_class")
    write_json(path, spec)
    row = run(path, tmp_path)["records"][0]
    assert row["route_matches_recorded_classification"] is True
    assert row["recorded_authorization_verified"] is True


def test_saved_trace_preserves_boundaries_and_has_no_execution_authority(tmp_path):
    path, spec, _, _ = sample(tmp_path)
    spec["unreplayable"] = [{"case_id": "missing-history", "evidence_gaps": ["no saved decision cutoff"],
                             "sources": [{"path": str(tmp_path / "failure.json"),
                                          "sha256": sha256_file(tmp_path / "failure.json")}]}]
    write_json(path, spec)
    result = run(path, tmp_path)
    row = result["records"][0]
    assert result["replayable_count"] == 1
    assert result["status"] == "ADVISORY_ONLY_NOT_AUTHORIZED"
    assert result["automatic_execution"] is False
    assert result["counterfactual_benefits_established"] is False
    assert row["route_matches_recorded_classification"] is True
    assert row["recorded_authorization_verified"] is True
    assert row["verified_costs"] == {"force_calls": 4}
    assert row["exact_retry_condition_verified"] is False
    assert row["requires_further_review"] is True
    assert result["records"][1]["status"] == "UNREPLAYABLE"
    assert result["records"][1]["sources"] == spec["unreplayable"][0]["sources"]
    with pytest.raises(FileExistsError):
        run(path, tmp_path)


@pytest.mark.parametrize("damage", ["future_revision", "wrong_job", "wrong_task", "missing_evidence",
                                      "stale_hash", "duplicate_event", "action_before_decision", "naive_time",
                                      "wrong_parent", "wrong_classification", "stale_advice", "duplicate_case",
                                      "execution_request"])
def test_invalid_inputs_never_write_report(tmp_path, damage):
    path, spec, public, answers = sample(tmp_path)
    trace = spec["traces"][0]
    if damage == "future_revision":
        revision = tmp_path / "later-revision.json"
        write_json(revision, {"symptom": "model error concluded later"})
        source = observation(revision, "/symptom")
        trace["evidence"][0]["source"] = source
        public["cases"][0]["evidence"][0].update(value=source["value"], source_sha256=source["sha256"])
        freeze(tmp_path, spec, public, answers)
    elif damage in {"wrong_job", "naive_time"}:
        after = load_json_object(tmp_path / "after.json")
        after["job" if damage == "wrong_job" else "at"] = "other-job" if damage == "wrong_job" else "2026-08-29T01:31:44"
        write_json(tmp_path / "unrelated.json", after)
        trace["after"] = [event(tmp_path / "unrelated.json", "unrelated")]
        trace["costs"] = []
    elif damage == "wrong_task":
        public["cases"][0]["group_id"] = "other-task"
        freeze(tmp_path, spec, public, answers)
    elif damage == "missing_evidence":
        trace["evidence"] = []
    elif damage == "stale_hash":
        write_json(tmp_path / "failure.json", {"symptom": "changed"})
    elif damage == "duplicate_event":
        trace["after"].append(copy.deepcopy(trace["after"][0]))
    elif damage == "action_before_decision":
        trace["action"] = trace["authorization"]["event"]
    elif damage == "wrong_parent":
        trace["action_parent"] = trace["authorization"]["binding"]
    elif damage == "wrong_classification":
        classification = load_json_object(tmp_path / "classification.json")
        classification["task_id"] = "other-task"
        write_json(tmp_path / "classification-other.json", classification)
        trace["recorded_classification"] = observation(tmp_path / "classification-other.json", "/outcome/failure_class")
    elif damage == "stale_advice":
        advice_path = Path(spec["advice"]["path"])
        advice = load_json_object(advice_path)
        advice["recommendations"][0]["next_review"] = "invented"
        write_json(advice_path, advice)
        spec["advice"]["sha256"] = sha256_file(advice_path)
    elif damage == "execution_request":
        trace["execute"] = "submit a VASP job"
    else:
        spec["traces"].append(copy.deepcopy(trace))
    write_json(path, spec)
    with pytest.raises(ValueError):
        run(path, tmp_path)
    assert not (tmp_path / "report.json").exists()


def test_priority_mismatch_withholds_strategy_hints(tmp_path):
    path, spec, public, answers = sample(tmp_path)
    answers["answers"][0].update(failure_class="optimizer", next_review="diagnose_optimizer_and_path",
                                 causal_status="hypothesis", causal_claim="Optimizer cause to test", causal_evidence_ids=["e1"])
    freeze(tmp_path, spec, public, answers)
    row = run(path, tmp_path)["records"][0]
    assert row["route_matches_recorded_classification"] is False
    assert row["saved_advice_fields_to_review"] == ["candidate_method"]
    assert row["ts_strategy_fields_to_review"] == []
    assert row["requires_further_review"] is True


def test_unverified_authorization_and_missing_costs_are_gaps(tmp_path):
    path, spec, _, _ = sample(tmp_path)
    spec["traces"][0].update(authorization=None, costs=[], recorded_classification=None)
    write_json(path, spec)
    row = run(path, tmp_path)["records"][0]
    assert row["recorded_authorization_verified"] is False
    assert row["verified_costs"] == {}
    assert row["route_matches_recorded_classification"] is None
    assert len(row["evidence_gaps"]) == 5


def test_missing_temporal_trace_is_unreplayable(tmp_path):
    path, spec, _, _ = sample(tmp_path)
    spec["traces"][0]["decision"] = None
    write_json(path, spec)
    result = run(path, tmp_path)
    assert result["replayable_count"] == 0
    assert result["records"][0]["status"] == "UNREPLAYABLE"


def test_repeated_request_is_a_clue_not_an_exact_input_ban(tmp_path):
    _, spec, public, answers = sample(tmp_path / "first")
    _, second, pub2, ans2 = sample(tmp_path / "second", suffix="2", hour="02")
    spec["traces"].extend(second["traces"])
    public["cases"].extend(pub2["cases"])
    answers["answers"].extend(ans2["answers"])
    path = freeze(tmp_path, spec, public, answers)
    row = run(path, tmp_path)["records"][1]
    assert row["prior_same_request_cases"] == ["c1"]
    assert row["exact_retry_condition_verified"] is False
    assert row["requires_further_review"] is True


def test_cli_never_reads_merged_events_or_opens_registry(monkeypatch, tmp_path, capsys):
    path, _, _, _ = sample(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("replay must not access a registry, merged outcomes or executor")
    monkeypatch.setattr(learning_cli, "read_events", forbidden)
    monkeypatch.setattr("scripts.ts_strategy_engine.registry.open_registry", forbidden)
    monkeypatch.setattr("scripts.ts_strategy_engine.execution_gate.decide_execution", forbidden)
    learning_cli.main(["replay-history", "--request", str(path), "--expected-request-sha256", sha256_file(path),
                       "--report", str(tmp_path / "cli-report.json")])
    assert "ADVISORY_ONLY_NOT_AUTHORIZED" in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        learning_cli.main(["--output", str(tmp_path / "bad.json"), "replay-history", "--request", str(path),
                           "--expected-request-sha256", sha256_file(path), "--report", str(tmp_path / "absent.json")])
    assert error.value.code == 2
    assert not (tmp_path / "absent.json").exists()


def test_wrong_manifest_identity_never_writes_report(tmp_path):
    path, _, _, _ = sample(tmp_path)
    with pytest.raises(ValueError, match="explicitly supplied identity"):
        replay_history(path, tmp_path / "report.json", "f" * 64)
    assert not (tmp_path / "report.json").exists()
