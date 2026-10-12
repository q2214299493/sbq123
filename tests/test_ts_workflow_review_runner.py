"""Synthetic transport fixtures only. Actual temporary-file reads, no model/scientific runs."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json
from scripts.ts_strategy_engine import learning_cli, review_app_server as protocol
from scripts.ts_strategy_engine import workflow_improvement as loop
from scripts.ts_strategy_engine.review_evidence import EvidenceTools
from scripts.ts_strategy_engine.workflow_review_runner import ReviewRun, load_trial, reference, run_review


@pytest.fixture
def frozen(tmp_path, request):
    trial = tmp_path / "frozen"
    trial.mkdir()
    material = trial / "source.json"
    write_json(material, {"symptom": "synthetic saved geometry", "method": "segmented_idpp"})
    item = {**reference(material), "pointer": "/symptom", "value": "synthetic saved geometry"}
    case = {"case_id": "case", "group_id": "synthetic-task", "question": "Synthetic geometry review?",
            "evidence": [{"evidence_id": "symptom", "pointer": "/symptom", "value": item["value"],
                          "source_sha256": item["sha256"]}]}
    case["input_sha256"] = sha256_json(case)
    public = {"schema_version": 2, "cases": [case]}
    public_path, answers_path = trial / "public.json", trial / "answers.json"
    write_json(public_path, public)
    write_json(answers_path, {"schema_version": 2, "public_sha256": sha256_json(public), "answers": [{
        "case_id": "case", "input_sha256": case["input_sha256"], "failure_class": "geometry",
        "causal_status": "hypothesis", "causal_claim": "HUMAN_REFERENCE_NOT_FOR_MODEL",
        "causal_evidence_ids": ["symptom"], "evidence_ids": ["symptom"],
        "next_review": "path_rebuild_review"}]})
    # Reuse the existing route rather than assuming a report label.
    from scripts.ts_strategy_engine.strategy_learning import policy
    answer = load_json_object(answers_path)
    answer["answers"][0]["next_review"] = policy()["failure_routes"]["geometry"]
    write_json(answers_path, answer)
    inputs = {"public": reference(public_path), "answers": reference(answers_path)}
    store = tmp_path / "store"
    p0 = loop.create_baseline(store, {"scope": "synthetic-pair", "provenance": "synthetic",
                                    "inputs": inputs, "observations": [item]})
    task = {"case_id": "case", "task_id": "synthetic-task", "input_sha256": case["input_sha256"],
            "required_checks": ["source_and_task_identity", "interpolation_strategy_evidence_read", "initial_images_evidence_read"]}
    if getattr(request, "param", False):
        task["required_checks"].append("human_chemical_review")
    contract = {"method": loop.METHOD, "rules": loop.RULES, "tasks": [task]}
    p1 = loop.propose_policy(store, {"parent_id": p0["policy_id"], "scope": "synthetic-pair",
                                   "changes": {"geometry": p0["orders"]["geometry"][::-1]},
                                   "rationale": "Synthetic order test", "observations": [item], "evaluation_contract": contract})
    poscar = trial / "POSCAR"
    poscar.write_text("synthetic\n1\n10 0 0\n0 10 0\n0 0 10\nO H\n1 1\nSelective dynamics\nDirect\n0 0 0 F F F\n0.12 0 0 T T T\n")
    document = {"scope": "synthetic-pair", "provenance": "synthetic", "inputs": inputs,
                "evaluation_contract": contract, "materials": {"seed_generation": reference(material),
                                                               "input_image_00": reference(poscar)}}
    trial_path = trial / "TRIAL.json"
    write_json(trial_path, document)
    request = {"schema_version": 1, "trial": reference(trial_path), "candidate_id": p1["policy_id"],
               "policy_id": p0["policy_id"], "scope": "synthetic-pair", **{k: task[k] for k in
                                                                         ("case_id", "task_id", "input_sha256")}}
    return {"store": store, "p0": p0, "p1": p1, "request": request, "trial_path": trial_path,
            "material": material, "root": tmp_path}


class SyntheticTransport:
    def __init__(self, order, evidence_ids, mode="normal"):
        self.thread, self.session, self.turn = (str(uuid.uuid4()) for _ in range(3))
        self.order, self.evidence_ids, self.mode = order, evidence_ids, mode
        self.sent, self.receipts, self.messages, self.closed = [], [], [], False

    def rpc(self, method, params):
        self.sent.append({"method": method, "params": params})
        if method == "initialize":
            return {"userAgent": "synthetic"}
        if method == "thread/start":
            assert params["ephemeral"] and params["environments"] == []
            assert len(params["dynamicTools"]) == 2
            return {"model": params["model"], "reasoningEffort": "medium", "approvalPolicy": "never",
                    "sandbox": {"type": "readOnly"}, "thread": {"id": self.thread, "sessionId": self.session,
                                                                  "turns": [], "ephemeral": True}}
        assert method == "turn/start"
        assert "HUMAN_REFERENCE_NOT_FOR_MODEL" not in params["input"][0]["text"]
        names = {"interpolation_strategy": "inspect_interpolation", "initial_images": "inspect_image_allocation"}
        for index, field in enumerate(self.order):
            message = {"id": f"rpc-{index}", "method": "item/tool/call", "params": {
                "threadId": self.thread, "turnId": self.turn, "callId": f"call-{index}",
                "tool": names[field], "arguments": {"evidence_ids": self.evidence_ids}}}
            self.messages.append(message)
            if self.mode == "retransmit" and index == 0:
                duplicate = deepcopy(message)
                duplicate["id"] = "new-rpc-id-same-call"
                self.messages.append(duplicate)
        if self.mode != "disconnect":
            self.messages.append({"method": "turn/completed", "params": {"threadId": self.thread,
                                  "turn": {"id": self.turn, "status": "completed"}}})
        return {"turn": {"id": self.turn}}

    def send(self, message):
        self.receipts.append(message)

    def receive(self):
        if not self.messages:
            raise EOFError("synthetic disconnection")
        return self.messages.pop(0)

    def close(self):
        self.closed = True


def prepared(env, name, identity=None):
    request = {**env["request"], "policy_id": identity or env["request"]["policy_id"]}
    loaded = load_trial(env["store"], request)
    return ReviewRun(loaded, env["root"] / name, "synthetic-model", "medium", 30)


def call(run, identity="call", tool=None, arguments=None):
    if run.session_id is None:
        run.session_id, run.thread_id, run.turn_id = (str(uuid.uuid4()) for _ in range(3))
    return {"threadId": run.thread_id, "turnId": run.turn_id, "callId": identity,
            "tool": tool or "inspect_interpolation",
            "arguments": arguments or {"evidence_ids": ["seed_generation", "input_image_00"]}}


def test_end_to_end_synthetic_real_file_reads_and_existing_binding(frozen):
    outputs, sessions = [], []
    for name, identity in [("A", frozen["p0"]["policy_id"]), ("B", frozen["p1"]["policy_id"])]:
        run = prepared(frozen, name, identity)
        peer = SyntheticTransport(run.loaded["order"], ["seed_generation", "input_image_00"], "retransmit")
        result = run.drive(peer, synthetic=True)
        assert result["status"] == "RECORDED" and result["actual_tool_calls"] == 2 and peer.closed
        assert all(c["result"] is True for c in result["required_checks"])
        replies = [r for r in peer.receipts if "result" in r]
        parsed = json.loads(replies[0]["result"]["contentItems"][0]["text"])
        assert parsed["evidence"][0]["parsed"]["method"] == "segmented_idpp"
        assert parsed["evidence"][1]["parsed"]["atom_count"] == 2
        assert replies[0]["result"] == replies[1]["result"]
        raw = load_json_object(run.output / "raw.json")
        assert [a["field"] for a in raw["actions"]] == run.loaded["order"]
        assert all(a["event_id"].startswith(run.run_id) for a in raw["actions"])
        outputs.append(result["trace"])
        sessions.append(peer.session)
    assert sessions[0] != sessions[1]
    evaluation = {"schema_version": 2, "candidate_id": frozen["p1"]["policy_id"],
                  "parent_id": frozen["p0"]["policy_id"], "scope": "synthetic-pair", "provenance": "synthetic",
                  "contract_sha256": frozen["p1"]["contract_sha256"],
                  "pairs": [{"case_id": "case", "parent": outputs[0], "candidate": outputs[1]}]}
    source = frozen["root"] / "evaluation.json"
    write_json(source, evaluation)
    result = loop.bind_evaluation(frozen["store"], reference(source))
    assert result["status"] == "NOT_SUPPORTED"  # Equal actions are a valid result, not manufactured improvement.
    assert result["decision"] is None
    evaluation["pairs"][0].update(parent=outputs[1], candidate=outputs[0])
    write_json(source, evaluation)
    with pytest.raises(ValueError, match="identity mismatch"):
        loop.bind_evaluation(frozen["store"], reference(source))


@pytest.mark.parametrize("key,value", [("policy_id", "a" * 64), ("task_id", "wrong"),
                                       ("input_sha256", "0" * 64), ("scope", "other")])
def test_wrong_binding_rejected(frozen, key, value):
    with pytest.raises(ValueError):
        load_trial(frozen["store"], {**frozen["request"], key: value})


def test_stale_source_and_policy_hash_rejected(frozen):
    frozen["material"].write_text('{"symptom":"changed"}')
    with pytest.raises(ValueError, match="stale"):
        load_trial(frozen["store"], frozen["request"])


def test_valid_but_unrelated_source_manifest_rejected(frozen):
    other = frozen["trial_path"].parent / "other-task.json"
    write_json(other, {"symptom": "another task"})
    trial = load_json_object(frozen["trial_path"])
    trial["materials"]["seed_generation"] = reference(other)
    write_json(frozen["trial_path"], trial)
    with pytest.raises(ValueError, match="original evidence"):
        load_trial(frozen["store"], {**frozen["request"], "trial": reference(frozen["trial_path"])})


def test_same_call_retransmit_but_independent_calls_count(frozen):
    run = prepared(frozen, "duplicates")
    params = call(run)
    assert run.tool_call(params)["success"]
    assert run.tool_call(deepcopy(params))["success"]
    assert run.tool_call({**params, "callId": "independent"})["success"]
    assert len(run.calls) == 2
    assert not run.tool_call({**params, "arguments": {"evidence_ids": ["seed_generation"]}})["success"]
    assert run.incomplete and len(run.calls) == 2


@pytest.mark.parametrize("arguments", [{"evidence_ids": ["../outside"]}, {"evidence_ids": ["seed_generation"], "field": "initial_images"},
                                      {"evidence_ids": ["seed_generation"], "path": "C:/secret"}])
def test_out_of_manifest_and_field_spoof_rejected(frozen, arguments):
    run = prepared(frozen, "bad")
    response = run.tool_call(call(run, arguments=arguments))
    assert not response["success"] and run.calls[0]["status"] == "FAILED"
    assert run.incomplete


@pytest.mark.parametrize("tool", ["shell", "write_file", "spawn_agent", "inspect_interpolation/../../exec"])
def test_write_native_and_delegation_tools_rejected(frozen, tool):
    run = prepared(frozen, "native")
    assert not run.tool_call(call(run, tool=tool))["success"]
    assert run.incomplete and not run.calls


def test_ninth_call_and_wrong_session_blocked(frozen):
    run = prepared(frozen, "budget")
    for i in range(8):
        assert run.tool_call(call(run, identity=str(i)))["success"]
    assert not run.tool_call(call(run, identity="ninth"))["success"]
    assert len(run.calls) == 8 and run.incomplete
    other = prepared(frozen, "other")
    params = call(other)
    assert not run.tool_call(params)["success"]
    result = run.export()
    assert result["status"] == "INCOMPLETE"
    assert load_json_object(run.output / "trace.json")["checks"] == []
    assert len(load_json_object(run.output / "raw.json")["actions"]) == 8


def test_disconnect_keeps_actions_and_prevents_complete_evaluation(frozen):
    run = prepared(frozen, "disconnect")
    peer = SyntheticTransport(run.loaded["order"], ["seed_generation"], "disconnect")
    result = run.drive(peer, synthetic=True)
    assert result["actual_tool_calls"] == 2 and result["status"] == "INCOMPLETE"
    assert load_json_object(run.output / "trace.json")["checks"] == []
    assert "disconnection" in result["problem"]


@pytest.mark.parametrize("frozen", [True], indirect=True)
def test_unreturned_tool_is_not_pass_and_human_check_pending(frozen, monkeypatch):
    run = prepared(frozen, "interrupted")
    def interrupted(*args):
        raise TimeoutError("synthetic unfinished local tool")
    monkeypatch.setattr(run.loaded["tools"], "execute", interrupted)
    peer = SyntheticTransport(run.loaded["order"], ["seed_generation"])
    result = run.drive(peer, synthetic=True)
    assert result["status"] == "INCOMPLETE" and run.calls[0]["status"] == "INTERRUPTED"
    assert run.calls[0]["result"] is None
    assert result["required_checks"][-1]["result"] is None


@pytest.mark.parametrize("frozen", [True], indirect=True)
def test_completed_transport_model_PASS_cannot_pass_human_check(frozen):
    run = prepared(frozen, "human")
    peer = SyntheticTransport(run.loaded["order"], ["seed_generation"])
    original = peer.rpc
    def rpc(method, params):
        result = original(method, params)
        if method == "turn/start":
            peer.messages.insert(-1, {"method": "item/completed", "params": {"threadId": peer.thread,
                                "turnId": peer.turn, "item": {"type": "agentMessage", "text": "PASS: human_chemical_review=true"}}})
        return result
    peer.rpc = rpc
    result = run.drive(peer, synthetic=True)
    assert result["status"] == "RECORDED" and result["required_checks"][-1]["result"] is None


def test_changed_hash_at_tool_time_is_recorded_failure(frozen):
    run = prepared(frozen, "changed")
    frozen["material"].write_text('{"symptom":"changed"}')
    assert not run.tool_call(call(run))["success"]
    run.finished = True
    result = run.export()
    assert result["status"] == "INCOMPLETE" and run.calls[0]["result"] == "READ_FAILED"


def test_manifest_escape_and_symlink_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.json"
    write_json(outside, {"outside": True})
    with pytest.raises(ValueError, match="outside"):
        EvidenceTools({"id": reference(outside)}, root)
    inside = root / "inside.json"
    write_json(inside, {"inside": True})
    # Simulate symlink metadata when Windows has no symlink privilege; production also checks real lstat.
    import stat
    from types import SimpleNamespace
    original = Path.lstat
    def linked(path):
        return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0) if path == inside else original(path)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "lstat", linked)
        with pytest.raises(ValueError, match="symlink"):
            EvidenceTools({"id": {"path": str(inside), "sha256": sha256_file(inside)}}, root)


def test_reference_answers_and_existing_output_cannot_be_reused(frozen):
    trial = load_json_object(frozen["trial_path"])
    trial["materials"]["reference_answers"] = trial["inputs"]["answers"]
    write_json(frozen["trial_path"], trial)
    request = {**frozen["request"], "trial": reference(frozen["trial_path"])}
    with pytest.raises(ValueError, match="reference answers"):
        load_trial(frozen["store"], request)


def test_source_result_and_finished_receipt_are_bound_at_real_read_time(frozen):
    run = prepared(frozen, "receipts")
    assert run.tool_call(call(run))["success"]
    events = [json.loads(line) for line in (run.output / "journal.jsonl").read_text().splitlines()]
    start = next(e for e in events if e["kind"] == "action_started")
    finish = next(e for e in events if e["kind"] == "action_finished")
    assert start["event_id"] == finish["event_id"] and start["result"] is None
    assert start["time_utc"] <= finish["time_utc"] and finish["status"] == "COMPLETED"
    assert all(start[k] == finish[k] == run.context[k] for k in ["task_id", "policy_id", "input_sha256", "contract_sha256"])
    result = json.loads(finish["response"]["contentItems"][0]["text"])
    assert result["evidence"][0]["sha256"] == sha256_file(frozen["material"])


def test_output_is_new_and_not_inside_frozen_inputs(frozen):
    prepared(frozen, "unique")
    with pytest.raises(FileExistsError):
        prepared(frozen, "unique")
    loaded = load_trial(frozen["store"], frozen["request"])
    with pytest.raises(ValueError, match="outside"):
        ReviewRun(loaded, frozen["trial_path"].parent / "wrong", "synthetic-model", "medium", 30)


@pytest.mark.parametrize("timeout", [0, -1, 3601, float("nan"), float("inf")])
def test_invalid_process_budget_rejected_before_output(frozen, timeout):
    loaded = load_trial(frozen["store"], frozen["request"])
    output = frozen["root"] / "invalid"
    with pytest.raises(ValueError, match="timeout"):
        ReviewRun(loaded, output, "synthetic-model", "medium", timeout)
    assert not output.exists()


def test_prepare_cli_never_launches_process_or_production_database(frozen, monkeypatch, capsys):
    request = frozen["root"] / "request.json"
    write_json(request, frozen["request"])
    def forbidden(*args, **kwargs):
        raise AssertionError("prepare must not invoke model/backend/database/execution")
    monkeypatch.setattr(protocol.subprocess, "Popen", forbidden)
    monkeypatch.setattr(learning_cli, "read_events", forbidden)
    learning_cli.main(["workflow-run-review", "--store", str(frozen["store"]), "--request", str(request),
                       "--output-dir", str(frozen["root"] / "prepare"), "--model", "synthetic-model", "--effort", "medium"])
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PREPARED" and result["model_calls"] == 0
    assert not (frozen["root"] / "prepare" / "trace.json").exists()


@pytest.mark.parametrize("value", ["task-001", "task-local", "case-task-local", "event-task-001",
                                   "task-" + "x" * 64, "case-sk-local", "event-sk-001",
                                   {"nested": [{"task_id": "task-local", "ok": True}]}])
def test_redaction_preserves_non_sensitive_identity_and_nested_results(value):
    assert protocol.redacted(value) == value


def test_redaction_preserves_unchanged_JSON_return_bytes():
    text = '{  "task_id": "task-local", "case_id": "case-task-001", "fmax": 400.0, "ok": true }\n'
    assert protocol.redacted(text) == text


@pytest.mark.parametrize("key", ["api_key", "apiKey", "password", "secret", "access_token", "credential", "Authorization"])
def test_redaction_keeps_sensitive_field_protection(key):
    payload = {"task_id": "task-local", "nested": [{key: "synthetic fixture secret", "result": "kept"}]}
    assert protocol.redacted(payload) == {"task_id": "task-local", "nested": [{key: "[REDACTED]", "result": "kept"}]}


@pytest.mark.parametrize("credential", ["sk-secret", "sk-" + "aB012345" * 6, "sk-proj-" + "aB012345" * 8,
                                        "sk-svcacct-" + "aB012345" * 8])
def test_redaction_masks_only_standalone_synthetic_API_credential(credential):
    assert protocol.redacted(f"task-001 before {credential}; task-local after") == "task-001 before [REDACTED]; task-local after"


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
def test_redaction_masks_only_synthetic_bearer_token(scheme):
    text = f"task-local before {scheme} eyJhbGci.fixture.signature==; event-task-001 after"
    assert protocol.redacted(text) == f"task-local before {scheme} [REDACTED]; event-task-001 after"


def test_redaction_of_nested_JSON_tool_return_keeps_non_sensitive_values():
    credential = "sk-proj-" + "aB012345" * 8
    returned = {"task_id": "task-local", "nested": [{"apiKey": credential, "count": 11}],
                "note": f"before {credential} after", "ok": True, "number": 400.0}
    payload = {"contentItems": [{"type": "inputText", "text": json.dumps(returned)}], "success": True}
    masked = protocol.redacted(payload)
    expected = {**returned, "nested": [{"apiKey": "[REDACTED]", "count": 11}], "note": "before [REDACTED] after"}
    assert json.loads(masked["contentItems"][0]["text"]) == expected
    assert type(json.loads(masked["contentItems"][0]["text"])["number"]) is float
    assert masked["success"] is True and credential not in json.dumps(masked)
    assert protocol.redacted(masked) == masked


def test_ReviewRun_record_preserves_identity_and_partially_redacts_JSON_return(frozen):
    run = prepared(frozen, "synthetic-redaction-journal")
    credential = "sk-proj-" + "aB012345" * 8
    ordinary = '{ "task_id": "task-001", "result": "geometry saved", "count": 11 }'
    sensitive = json.dumps({"task_id": "task-local", "api_key": credential,
                            "note": "before Bearer synthetic.fixture.token after", "count": 15})
    payload = {"task_id": "task-001", "case_id": "case-task-local", "event_id": "event-task-001",
               "nested": [{"password": "synthetic fixture password", "result": "kept"}],
               "ordinary_return": ordinary, "tool_return": {"contentItems": [{"type": "inputText", "text": sensitive}]}}
    run.record("synthetic_redaction_regression", payload)
    data = (run.output / "journal.jsonl").read_text(encoding="utf-8")
    row = next(json.loads(line) for line in data.splitlines() if json.loads(line)["kind"] == "synthetic_redaction_regression")
    assert row["task_id"] == "task-001" and row["case_id"] == "case-task-local" and row["event_id"] == "event-task-001"
    assert row["ordinary_return"] == ordinary
    assert row["nested"] == [{"password": "[REDACTED]", "result": "kept"}]
    assert json.loads(row["tool_return"]["contentItems"][0]["text"]) == {
        "task_id": "task-local", "api_key": "[REDACTED]", "note": "before Bearer [REDACTED] after", "count": 15}
    assert credential not in data and "synthetic.fixture.token" not in data and "synthetic fixture password" not in data
    assert payload["tool_return"]["contentItems"][0]["text"] == sensitive  # The caller's original return is not mutated.


def test_live_execution_fails_closed_even_with_forged_probe_claim(frozen, monkeypatch):
    request = frozen["root"] / "request.json"
    write_json(request, frozen["request"])
    monkeypatch.setattr("scripts.ts_strategy_engine.workflow_review_runner.executable", lambda _: Path(sys.executable))
    monkeypatch.setattr("scripts.ts_strategy_engine.workflow_review_runner.probe_backend",
                        lambda *a: {"blocking_reason": "unverified native read scope", "model_read_scope_verified": True})
    result = run_review(frozen["store"], request, frozen["root"] / "live", model="synthetic-model", effort="medium", execute=True)
    assert result["status"] == "BLOCKED" and result["model_calls"] == 0
    run = prepared(frozen, "unsafe")
    with pytest.raises(ValueError, match="blocked"):
        run.drive(SyntheticTransport(run.loaded["order"], ["seed_generation"]))


def test_stdio_synthetic_child_deadline_and_redaction(tmp_path, monkeypatch):
    directory = tmp_path / "process"
    directory.mkdir()
    (directory / "workspace").mkdir()
    child = directory / "synthetic_peer.py"
    child.write_text("import time\ntime.sleep(30)\n")
    original = subprocess.Popen
    def launch(*args, **kwargs):
        return original([sys.executable, str(child)], **kwargs)
    monkeypatch.setattr(protocol.subprocess, "Popen", launch)
    events = []
    transport = protocol.Stdio(Path(sys.executable), directory, 0.15, lambda *args: events.append(args))
    started = time.monotonic()
    try:
        with pytest.raises((EOFError, TimeoutError)):
            transport.receive()
    finally:
        transport.close()
    assert time.monotonic() - started < 3 and transport.process.poll() is not None
    assert protocol.redacted({"apiKey": "secret", "Authorization": "Bearer abc", "text": "sk-secret"}) == {
        "apiKey": "[REDACTED]", "Authorization": "[REDACTED]", "text": "[REDACTED]"}


def test_synthetic_stdio_wire_end_to_end_reads_files(frozen, monkeypatch):
    """A real subprocess transports fixture RPCs; it is not a Codex/model invocation."""
    child = frozen["root"] / "synthetic_server.py"
    child.write_text('''import json, sys
def send(message):
    print(json.dumps(message), flush=True)
for line in sys.stdin:
    message = json.loads(line)
    method, params = message.get("method"), message.get("params", {})
    if method == "initialize":
        send({"id": message["id"], "result": {"userAgent": "synthetic"}})
    elif method == "thread/start":
        send({"id": message["id"], "result": {"model": params["model"], "reasoningEffort": "medium",
             "approvalPolicy": "never", "sandbox": {"type": "readOnly"},
             "thread": {"id": "fixture-thread", "sessionId": "fixture-session", "turns": [], "ephemeral": True}}})
        send({"method": "thread/started", "params": {"thread": {"id": "fixture-thread"}}})
    elif method == "turn/start":
        send({"id": message["id"], "result": {"turn": {"id": "fixture-turn"}}})
        for i, tool in enumerate(["inspect_interpolation", "inspect_image_allocation"]):
            send({"id": f"tool-{i}", "method": "item/tool/call", "params": {
                 "threadId": "fixture-thread", "turnId": "fixture-turn", "callId": f"call-{i}",
                 "tool": tool, "arguments": {"evidence_ids": ["seed_generation", "input_image_00"]}}})
    elif message.get("id") == "tool-1":
        send({"method": "turn/completed", "params": {"threadId": "fixture-thread", "turn": {
             "id": "fixture-turn", "status": "completed"}}})
''')
    original = subprocess.Popen
    def launch(*args, **kwargs):
        return original([sys.executable, str(child)], **kwargs)
    monkeypatch.setattr(protocol.subprocess, "Popen", launch)
    run = prepared(frozen, "wire")
    transport = protocol.Stdio(Path(sys.executable), run.output, 10, run.protocol)
    result = run.drive(transport, synthetic=True)
    assert result["status"] == "RECORDED" and result["actual_tool_calls"] == 2
    events = [json.loads(line) for line in (run.output / "journal.jsonl").read_text().splitlines()]
    assert sum(e["kind"] == "action_finished" for e in events) == 2
    assert any(e["kind"] == "protocol" and e["message"].get("method") == "initialize" for e in events)
    assert all(e["response"]["success"] for e in events if e["kind"] == "action_finished")
