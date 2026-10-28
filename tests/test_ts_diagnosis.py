"""Synthetic software tests only. No model, scheduler, GPU or VASP execution."""
from __future__ import annotations

from copy import deepcopy
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.ts_strategy_engine import diagnosis_runner as runner, learning_cli, review_app_server, review_live
from scripts.ts_strategy_engine.diagnostic_advice import DiagnosticEvidence, backend_output_schema, load_case, output_schema, validate_output
from scripts.ts_strategy_engine.learning_cases import build_cases
from scripts.ts_strategy_engine.next_review import recommend_next_reviews


@pytest.fixture
def frozen(tmp_path):
    root = tmp_path / "frozen"
    root.mkdir()
    source = root / "source.json"
    write_json(source, {"observed": 1.25, "posthoc": "SECRET_FUTURE_REFERENCE_NOT_FOR_MODEL"})
    manifest = root / "cases.json"
    write_json(manifest, {"schema_version": 2, "cases": [{
        "case_id": "synthetic-event", "group_id": "synthetic-task", "question": "Synthetic evidence gap?",
        "provenance": "synthetic", "public_evidence": [{"evidence_id": "distance", "path": str(source),
        "sha256": sha256_file(source), "pointer": "/observed", "value": 1.25}], "reference": None}]})
    bundle = tmp_path / "bundle"
    build_cases(manifest, root, bundle)
    return load_case(bundle, "synthetic-event")


def generated():
    return {"diagnosis": {"failure_class": "unknown", "causal_claim": None, "causal_status": "unknown",
            "causal_evidence_ids": [], "next_review": "collect_missing_evidence", "evidence_ids": ["distance"]},
        "observations": [{"statement": "Synthetic observed distance is 1.25.", "evidence_ids": ["distance"]}],
        "hypotheses": [], "missing_evidence": ["Matched neighboring frame coordinates"],
        "next_check": {"action": "Manually compare the same atom pair in neighboring frozen frames.",
            "rationale": "One distance cannot distinguish continuity from a branch jump.", "evidence_ids": ["distance"],
            "expected_outcomes": [{"if": "continuous", "then": "request force provenance"},
                                  {"if": "discontinuous", "then": "request mapping review"}]},
        "conditional_proposals": [], "cost": {"status": "unknown", "value": None, "unit": None,
            "basis": "No measured timing evidence", "evidence_ids": []}, "method_sources": [],
        "scientific_scope": "Synthetic software fixture only; no scientific acceptance."}


class SyntheticPeer:
    def __init__(self, run, mode="normal"):
        self.run, self.mode = run, mode
        self.sent, self.messages = [], []

    def rpc(self, method, params):
        self.sent.append((method, deepcopy(params)))
        if method == "initialize":
            return {}
        if method == "thread/start":
            assert len(params["dynamicTools"]) == 1
            tool = params["dynamicTools"][0]
            assert tool["type"] == "function" and tool["deferLoading"] is False
            assert "SECRET_FUTURE" not in json.dumps(params)
            return {"model": params["model"], "reasoningEffort": "medium", "approvalPolicy": "never",
                    "sandbox": {"type": "readOnly"}, "thread": {"id": "thread", "sessionId": "session",
                    "turns": [], "ephemeral": True}}
        assert method == "turn/start"
        assert params["outputSchema"]["properties"]["diagnosis"]["properties"]["next_review"]["enum"]
        assert "SECRET_FUTURE" not in json.dumps(params)
        self.messages = [{"id": "rpc", "method": "item/tool/call", "params": {
            "threadId": "thread", "turnId": "turn", "callId": "call", "tool": "read_frozen_evidence",
            "arguments": {"evidence_ids": ["distance"]}}}]
        if self.mode == "bad_tool":
            self.messages[0]["params"]["tool"] = "shell"
        text = "bad JSON" if self.mode == "bad_json" else json.dumps(generated())
        self.messages.extend([
            {"method": "item/completed", "params": {"threadId": "thread", "turnId": "turn", "item": {
                "type": "agentMessage", "id": "message", "text": text}}},
            {"method": "turn/completed", "params": {"threadId": "thread", "turn": {"id": "turn", "status": "completed"}}},
        ])
        return {"turn": {"id": "turn"}}

    def send(self, message):
        self.sent.append(("response", message))

    def receive(self):
        if not self.messages:
            raise EOFError("synthetic EOF")
        message = self.messages.pop(0)
        self.run.record("received", message)
        return message


def new_run(loaded, output):
    return runner.DiagnosisRun(loaded, output, "synthetic-model", "medium", "2026-09-02T10:19:58Z", 30, 4)


def test_scalar_projection_does_not_expose_sibling_or_private_reference(frozen):
    tool = DiagnosticEvidence(frozen)
    result = tool.execute(tool.NAME, {"evidence_ids": ["distance"]})
    assert "SECRET_FUTURE" not in json.dumps(result)
    assert "source.json" not in json.dumps(result)
    assert tool.read_ids == {"distance"}
    with pytest.raises(ValueError, match="listed"):
        tool.execute(tool.NAME, {"evidence_ids": ["../private.json"]})
    with pytest.raises(ValueError):
        tool.execute("shell", {"evidence_ids": ["distance"]})


def test_synthetic_end_to_end_and_existing_advise_next_projection(frozen, tmp_path):
    run = new_run(frozen, tmp_path / "run")
    peer = SyntheticPeer(run)
    run.drive(peer, synthetic=True)
    receipt = run.finish()
    assert receipt["status"] == "OFFLINE_TEST_GENERATED" and not receipt["new_diagnosis_generated"]
    assert receipt["turn_completed"] and receipt["actual_tool_calls"] == 1
    assert json.loads((run.output / "model-response.txt").read_text()) == generated()
    advice = recommend_next_reviews(run.output / "public.json", run.output / "answers.json", tmp_path / "advice.json",
                                   frozen["public_sha256"])
    assert advice["status"] == "ADVISORY_ONLY_NOT_AUTHORIZED"
    assert (run.output / "review.md").is_file()


@pytest.mark.parametrize("kind", ["unlisted", "unread", "unknown_cost", "unbound_cause", "missing_citation", "invented_source"])
def test_invalid_generation_is_rejected(frozen, kind):
    document, reads = generated(), {"distance"}
    if kind == "unlisted":
        document["next_check"]["evidence_ids"] = ["invented"]
    elif kind == "unread":
        reads = set()
    elif kind == "unknown_cost":
        document["cost"]["value"] = 0
    elif kind == "unbound_cause":
        document["diagnosis"]["causal_claim"] = "invented cause"
    elif kind == "missing_citation":
        document["next_check"]["evidence_ids"] = []
    else:
        document["method_sources"] = ["invented paper"]
    with pytest.raises((ValueError, runner.ValidationError)):
        validate_output(document, frozen, reads)


@pytest.mark.parametrize("mode", ["bad_json", "bad_tool"])
def test_bad_response_never_writes_valid_answers(frozen, tmp_path, mode):
    run = new_run(frozen, tmp_path / "bad")
    with pytest.raises(ValueError):
        run.drive(SyntheticPeer(run, mode), synthetic=True)
    assert not (run.output / "answers.json").exists()
    if mode == "bad_json":
        assert (run.output / "model-response.txt").read_text() == "bad JSON"


def test_tampered_source_and_existing_output_rejected(frozen, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        new_run(frozen, output)
    source = Path(frozen["sources"]["distance"]["path"])
    source.write_text('{"observed": 3}')
    with pytest.raises(ValueError, match="changed"):
        DiagnosticEvidence(frozen).verify()


def test_same_input_reuses_immutable_workspace_without_config_rebind(frozen, tmp_path):
    home = tmp_path / "auth"
    first, second = new_run(frozen, tmp_path / "a"), new_run(frozen, tmp_path / "b")
    first.bind_workspace(home)
    before = (first.workspace / "model_input.json").read_bytes()
    second.bind_workspace(home)
    assert first.workspace == second.workspace
    assert (second.workspace / "model_input.json").read_bytes() == before


def test_same_live_admission_failure_records_first_stage_and_zero_turn(frozen, tmp_path, monkeypatch):
    calls = []
    def blocked(*args, **kwargs):
        calls.append((args, kwargs))
        with review_live.admission_stage(args[3], "initialize"):
            raise EOFError("synthetic startup EOF")
    monkeypatch.setattr(runner, "LiveStdio", blocked)
    monkeypatch.setattr(runner, "executable", lambda _: Path("synthetic-codex"))
    receipt = runner.run_diagnosis(frozen["bundle"], "synthetic-event", tmp_path / "blocked",
        model="synthetic-model", effort="medium", checkpoint="2026-09-02T10:19:58Z", auth_home=tmp_path / "auth", probe_live=True)
    assert len(calls) == 1 and receipt["status"] == "BLOCKED"
    assert receipt["first_failure_stage"] == "initialize" and receipt["model_turns_started"] == 0
    assert receipt["turn_start_attempts"] == 0 and not receipt["new_diagnosis_generated"]
    assert "未生成新诊断" in (tmp_path / "blocked" / "review.md").read_text(encoding="utf-8")


def test_probe_closes_before_turn_start(frozen, tmp_path):
    run = new_run(frozen, tmp_path / "probe")
    peer = SyntheticPeer(run)
    run.drive(peer, synthetic=True, probe_live=True)
    receipt = run.finish(probe_live=True)
    assert not any(method == "turn/start" for method, _ in peer.sent)
    assert receipt["turn_start_attempts"] == receipt["model_turns_started"] == 0
    assert not (run.output / "answers.json").exists()


def test_protocol_command_failure_keeps_stderr_and_exit(tmp_path, monkeypatch):
    def failed(*args, **kwargs):
        return SimpleNamespace(returncode=7, stdout=b"", stderr=b"synthetic protocol configuration failure")
    monkeypatch.setattr(review_app_server.subprocess, "run", failed)
    with pytest.raises(ValueError, match="exit=7"):
        review_app_server.verify_protocol(Path("synthetic-codex"), tmp_path / "protocol", 10)
    command = load_json_object(tmp_path / "protocol" / "command-01.json")
    assert command["exit_code"] == 7 and command["stderr"] == "synthetic protocol configuration failure"


def test_cli_has_distinct_generation_and_probe_modes():
    args = learning_cli.parser().parse_args(["diagnose", "--bundle", "bundle", "--case-id", "id", "--checkpoint",
        "2026-09-02T10:19:58Z", "--output-dir", "out", "--model", "synthetic-model", "--effort", "medium", "--auth-home", "auth"])
    assert not args.probe_live
    assert not learning_cli.parser().parse_args(["workflow-run-review", "--store", "store", "--request", "request",
        "--output-dir", "out", "--model", "synthetic-model", "--effort", "medium"]).execute


def test_protocol_admission_and_launch_share_isolated_environment(tmp_path, monkeypatch):
    home = tmp_path / "isolated-auth"
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key-not-to-inherit")
    captured = []
    def fail(*args, **kwargs):
        captured.append(kwargs["env"])
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"synthetic local failure")
    monkeypatch.setattr(review_app_server.subprocess, "run", fail)
    with pytest.raises(ValueError):
        review_app_server.verify_protocol(Path("synthetic-codex"), tmp_path / "protocol", 10, auth_home=home)
    assert captured[0] == review_app_server.child_environment(home)
    assert captured[0]["CODEX_HOME"] == str(home) and "OPENAI_API_KEY" not in captured[0]


def test_stderr_preserves_original_bytes_and_omits_sensitive_raw():
    raw = "拒绝访问。".encode("gbk")
    captured = review_app_server.stderr_capture(raw)
    assert base64.b64decode(captured["raw_base64"]) == raw
    secret = review_app_server.stderr_capture(b"Authorization: Bearer synthetic.fixture")
    assert secret["raw_base64"] is None and "synthetic.fixture" not in json.dumps(secret)


def test_native_probe_reuses_only_the_exact_safe_canary(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    def native(command, **kwargs):
        allowed = command[-1].endswith("read-canary.txt")
        return SimpleNamespace(returncode=0 if allowed else 1, stdout=b"SAFE_READ_CANARY" if allowed else b"", stderr=b"")
    monkeypatch.setattr(review_live.subprocess, "run", native)
    if not hasattr(review_live.subprocess, "CREATE_NO_WINDOW"):
        monkeypatch.setattr(review_live.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    for name in ("first", "second"):
        directory = tmp_path / name
        directory.mkdir()
        result = review_live.native_probe(Path("synthetic-codex"), tmp_path / "auth", workspace, directory, 10)
        assert result["passed"]
    (workspace / "read-canary.txt").write_text("different")
    directory = tmp_path / "third"
    directory.mkdir()
    with pytest.raises(ValueError, match="unexpected content"):
        review_live.native_probe(Path("synthetic-codex"), tmp_path / "auth", workspace, directory, 10)


def test_tool_binding_retransmission_and_conflict(frozen, tmp_path):
    run = new_run(frozen, tmp_path / "tools")
    run.thread_id, run.turn_id = "thread", "turn"
    params = {"threadId": "thread", "turnId": "turn", "callId": "same", "tool": "read_frozen_evidence",
              "arguments": {"evidence_ids": ["distance"]}}
    assert run._tool(params) == run._tool(deepcopy(params))
    assert len(run.calls) == 1
    with pytest.raises(ValueError, match="conflicting"):
        run._tool({**params, "arguments": {"evidence_ids": ["invented"]}})
    with pytest.raises(ValueError, match="identity"):
        run._tool({**params, "turnId": "other"})


def test_probe_report_does_not_call_a_synthetic_fixture_real(frozen, tmp_path):
    run = new_run(frozen, tmp_path / "probe-report")
    run.drive(SyntheticPeer(run), synthetic=True, probe_live=True)
    receipt = run.finish(probe_live=True)
    assert receipt["status"] == "OFFLINE_TEST_ADMITTED_NO_TURN" and receipt["model_turns_started"] == 0
    assert "未发送 turn/start" in (run.output / "review.md").read_text(encoding="utf-8")


def test_explicit_file_store_preserves_all_permissions_and_rejects_silent_migration(tmp_path):
    home, workspace = tmp_path / "auth", tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    keyring = review_live.configure(home, workspace, [])
    original = (home / "config.toml").read_bytes()
    file_config = review_live.settings(home.resolve(), workspace.resolve(), [], credential_store="file")
    assert file_config == {**keyring, "cli_auth_credentials_store": "file"}
    with pytest.raises(ValueError, match="different configuration"):
        review_live.configure(home, workspace, [], credential_store="file")
    assert (home / "config.toml").read_bytes() == original


def test_file_bootstrap_requires_explicit_matching_store(tmp_path):
    home, workspace = tmp_path / "auth", tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    (home / "config.toml").write_text('cli_auth_credentials_store="file"\n')
    with pytest.raises(ValueError, match="different configuration"):
        review_live.configure(home, workspace, [])
    configured = review_live.configure(home, workspace, [], credential_store="file")
    assert configured["cli_auth_credentials_store"] == "file"
    assert configured["permissions"][review_live.MODEL_PROFILE]["filesystem"][home.as_posix()] == "deny"


@pytest.mark.parametrize("client_code,expected", [(1, "HOST_LOGIN_NOT_VISIBLE_TO_NATIVE_CLIENT"),
                                                 (0, "CLI_AUTH_VISIBLE_BUT_ACCOUNT_RPC_EMPTY")])
def test_auth_probe_distinguishes_logged_in_host_from_rpc_empty(tmp_path, monkeypatch, client_code, expected):
    home, workspace = tmp_path / "auth", tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    (home / "config.toml").write_text('cli_auth_credentials_store="keyring"\n')
    calls = []
    def status(command, **kwargs):
        calls.append(command)
        code = client_code if "sandbox" in command else 0
        return SimpleNamespace(returncode=code, stdout=b"", stderr=b"Windows error code 5" if code else b"Logged in using ChatGPT")
    monkeypatch.setattr(review_live.subprocess, "run", status)
    proof = review_live.auth_visibility_probe(Path("synthetic-codex"), home, workspace, tmp_path, 10)
    assert proof["status"] == expected and not proof["permissions_changed"]
    assert proof["model_turns_started"] == 0 and len(calls) == 2
    assert all(command[-2:] == ["login", "status"] for command in calls)
    assert load_json_object(tmp_path / "auth-visibility-probe.json") == proof


def test_blocked_report_does_not_ask_logged_in_user_to_log_in_again(frozen, tmp_path):
    run = new_run(frozen, tmp_path / "visibility-report")
    run.first_failure_stage = "chatgpt_authentication"
    run.problem = "Synthetic native-client keyring access denial"
    run.permission_evidence = {"auth_visibility": {"status": "HOST_LOGIN_NOT_VISIBLE_TO_NATIVE_CLIENT"}}
    receipt = run.finish()
    assert receipt["model_turns_started"] == 0
    report = (run.output / "review.md").read_text(encoding="utf-8")
    assert "宿主已登录" in report and "不要重复要求登录" in report


def test_cli_defaults_to_keyring_without_file_store_fallback():
    args = learning_cli.parser().parse_args(["diagnose", "--bundle", "bundle", "--case-id", "id", "--checkpoint",
        "2026-09-02T10:19:58Z", "--output-dir", "out", "--model", "synthetic-model", "--effort", "medium", "--auth-home", "auth"])
    assert args.credential_store == "keyring"


def test_nonexecuting_startup_status_does_not_enable_capabilities(frozen, tmp_path):
    run = new_run(frozen, tmp_path / "metadata-notifications")
    run.thread_id = "thread"
    run._notification("remoteControl/status/changed", {"status": "disabled"})
    run._notification("warning", {"threadId": "thread", "message": "Code Mode is unavailable because code-mode host is disabled."})
    assert len(run.backend_warnings) == 1 and not run.calls and not run.turn_completed
    with pytest.raises(ValueError, match="remote-control"):
        run._notification("remoteControl/status/changed", {"status": "connected"})
    with pytest.raises(ValueError, match="mismatch"):
        run._notification("warning", {"threadId": "other", "message": "wrong thread"})


def test_user_input_echo_is_data_and_must_match_reserved_prompt(frozen, tmp_path):
    run = new_run(frozen, tmp_path / "echo")
    item = {"type": "userMessage", "id": "input", "content": [{"type": "text",
            "text": json.dumps(run.prompt, ensure_ascii=False), "text_elements": []}]}
    run._item_event("item/started", item)
    run._item_event("item/completed", item)
    assert not run.messages and not run.calls
    item["content"][0]["text"] = "unreserved extra instructions"
    with pytest.raises(ValueError, match="reserved frozen input"):
        run._item_event("item/started", item)


def test_commentary_is_retained_and_only_declared_final_answer_is_parsed(frozen, tmp_path):
    run = new_run(frozen, tmp_path / "phases")
    peer = SyntheticPeer(run)
    original = peer.rpc
    def rpc(method, params):
        result = original(method, params)
        if method == "turn/start":
            peer.messages.insert(0, {"method": "item/completed", "params": {"threadId": "thread", "turnId": "turn",
                "item": {"type": "agentMessage", "id": "commentary", "phase": "commentary", "text": "Synthetic progress text"}}})
            peer.messages[-2]["params"]["item"]["phase"] = "final_answer"
        return result
    peer.rpc = rpc
    run.drive(peer, synthetic=True)
    receipt = run.finish()
    assert receipt["status"] == "OFFLINE_TEST_GENERATED" and receipt["model_messages_received"] == 2
    assert "Synthetic progress text" in (run.output / "model-response.txt").read_text()
    assert json.loads((run.output / "model-final.txt").read_text()) == generated()


def test_turn_metadata_is_observed_without_granting_actions(frozen, tmp_path):
    run = new_run(frozen, tmp_path / "turn-metadata")
    run.thread_id, run.turn_id = "thread", "turn"
    run._notification("turn/moderationMetadata", {"threadId": "thread", "turnId": "turn", "metadata": {}})
    assert not run.turn_completed and not run.calls
    with pytest.raises(ValueError, match="mismatch"):
        run._notification("turn/moderationMetadata", {"threadId": "thread", "turnId": "other", "metadata": {}})


def test_data_only_read_view_stays_stable_when_prompt_presentation_changes(frozen, tmp_path):
    first, second = new_run(frozen, tmp_path / "first-view"), new_run(frozen, tmp_path / "second-view")
    second.prompt["instructions"].append("Synthetic presentation-only change")
    first.bind_workspace(tmp_path / "auth")
    second.bind_workspace(tmp_path / "auth")
    assert first.workspace == second.workspace
    view = load_json_object(first.workspace / "model_input.json")
    assert set(view) == {"checkpoint", "public"}
    assert view["public"] == frozen["public"] and "SECRET_FUTURE" not in json.dumps(view)


def test_portable_backend_hint_keeps_full_host_validation(frozen):
    host = output_schema()
    hint = backend_output_schema()
    assert host["properties"]["diagnosis"]["properties"]["evidence_ids"]["uniqueItems"]
    assert "uniqueItems" not in hint["properties"]["diagnosis"]["properties"]["evidence_ids"]
    assert hint["properties"]["diagnosis"]["properties"]["next_review"] == host["properties"]["diagnosis"]["properties"]["next_review"]
    document = generated()
    document["next_check"]["evidence_ids"] = ["distance", "distance"]
    with pytest.raises(runner.ValidationError):
        validate_output(document, frozen, {"distance"})


class FrozenContextPeer(SyntheticPeer):
    def rpc(self, method, params):
        self.sent.append((method, deepcopy(params)))
        if method == "initialize":
            return {}
        if method == "thread/start":
            assert params["dynamicTools"] == []
            return {"model": params["model"], "reasoningEffort": "medium", "approvalPolicy": "never",
                    "sandbox": {"type": "readOnly"}, "thread": {"id": "thread", "sessionId": "session",
                    "turns": [], "ephemeral": True}}
        assert method == "turn/start"
        self.messages = [
            {"method": "item/completed", "params": {"threadId": "thread", "turnId": "turn", "item": {
                "type": "agentMessage", "id": "final", "phase": "final_answer", "text": json.dumps(generated())}}},
            {"method": "turn/completed", "params": {"threadId": "thread", "turn": {"id": "turn", "status": "completed"}}}]
        return {"turn": {"id": "turn"}}


def test_explicit_context_contract_uses_zero_tools_and_keeps_truthful_receipt(frozen, tmp_path):
    run = runner.DiagnosisRun(frozen, tmp_path / "context", "synthetic-model", "medium", "2026-09-02T10:19:58Z",
                              30, 4, evidence_access="frozen-context")
    run.drive(FrozenContextPeer(run), synthetic=True)
    receipt = run.finish()
    assert receipt["evidence_access"] == "frozen-context" and receipt["actual_tool_calls"] == 0
    assert receipt["status"] == "OFFLINE_TEST_GENERATED" and not receipt["new_diagnosis_generated"]
    assert receipt["source_references_reverified"]
    assert "模型工具调用数为 0" in (run.output / "review.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        run._tool({})


def test_context_contract_still_rejects_changed_original_source(frozen, tmp_path):
    run = runner.DiagnosisRun(frozen, tmp_path / "changed-context", "synthetic-model", "medium", "2026-09-02T10:19:58Z",
                              30, 4, evidence_access="frozen-context")
    Path(frozen["sources"]["distance"]["path"]).write_text('{"observed": 4}')
    with pytest.raises(ValueError, match="changed"):
        run.drive(FrozenContextPeer(run), synthetic=True)
    assert not (run.output / "answers.json").exists()
