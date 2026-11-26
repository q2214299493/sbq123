from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.neb_agent.remote_monitor import (
    normalized_script_payload,
    remote_command,
    run_remote_monitor,
)


def test_normalized_script_payload_removes_carriage_returns(tmp_path: Path) -> None:
    script = tmp_path / "monitor.sh"
    script.write_bytes(b"#!/bin/bash\r\necho ok\r\n\r\n")

    assert normalized_script_payload(script) == b"#!/bin/bash\necho ok\n"


def test_remote_command_quotes_job_directory() -> None:
    assert remote_command("/tmp/a path", 7) == "bash -s -- '/tmp/a path' --detail 7"
    assert remote_command("~/sbq/job") == 'bash -s -- "$HOME"/sbq/job'
    with pytest.raises(ValueError, match="positive"):
        remote_command("/tmp/job", 0)


def test_run_remote_monitor_passes_lf_bytes_to_ssh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "monitor.sh"
    script.write_bytes(b"#!/bin/bash\r\necho ok\r\n")
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_remote_monitor("sunboquan-codex", "/remote/job", script=script) == 0
    assert captured["args"] == (["ssh", "sunboquan-codex", "bash -s -- /remote/job"],)
    assert captured["kwargs"] == {
        "input": b"#!/bin/bash\necho ok\n",
        "check": False,
        "timeout": 60,
    }


def test_run_remote_monitor_reports_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "monitor.sh"
    script.write_bytes(b"#!/bin/bash\n")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=60)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="timed out after 60 seconds"):
        run_remote_monitor("sunboquan-codex", "/remote/job", script=script)


def test_run_remote_monitor_connection_failure_is_not_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "monitor.sh"
    script.write_bytes(b"#!/bin/bash\n")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=255)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_remote_monitor(
        "sunboquan-codex", "/remote/job", script=script
    ) == 255


def test_run_remote_monitor_rejects_unsafe_host() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        run_remote_monitor("host;echo", "/remote/job")
