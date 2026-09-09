"""CLI transport regressions; real transaction gates have separate tests."""
import io
import json
import sys

import pytest

from scripts import registry_write


@pytest.mark.parametrize("command", ["plan", "apply"])
@pytest.mark.parametrize("saved_output", [False, True])
def test_cli_ascii_console_preserves_plan_hash_and_float(
    monkeypatch, tmp_path, command, saved_output
):
    result = {
        "batch_id": "测试²",
        "batch_sha256": "b" * 64,
        "plan_sha256": "a" * 64,
        "value": 400.0,
        "insert_count": 1,
    }
    calls = []
    monkeypatch.setattr(registry_write, "load_registry_batch", lambda _: {})
    monkeypatch.setattr(registry_write, "plan_registry_batch", lambda *_: result)

    def apply(*args, **kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(registry_write, "apply_registry_batch", apply)
    argv = ["registry-write", command, "--manifest", "unused.json"]
    if command == "apply":
        plan = tmp_path / "plan.json"
        approval = tmp_path / "approval.json"
        plan.write_text(json.dumps(result), encoding="utf-8")
        approval.write_text("{}", encoding="utf-8")
        argv += ["--plan", str(plan), "--approval", str(approval),
                 "--confirm-sha256", result["plan_sha256"]]
    output = tmp_path / "课题².json"
    if saved_output:
        argv += ["--output", str(output)]
    monkeypatch.setattr(sys, "argv", argv)
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="ascii")
    monkeypatch.setattr(sys, "stdout", console)
    registry_write.main()
    console.flush()
    summary = json.loads(raw.getvalue().decode("ascii"))
    assert summary["plan_sha256"] == result["plan_sha256"]
    assert summary["batch_sha256"] != summary["plan_sha256"]
    if saved_output:
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload == result
        assert isinstance(payload["value"], float)
    else:
        assert summary == result
    if command == "apply":
        assert len(calls) == 1
        assert calls[0]["confirmed_sha256"] == result["plan_sha256"]
        assert isinstance(calls[0]["plan"]["value"], float)
