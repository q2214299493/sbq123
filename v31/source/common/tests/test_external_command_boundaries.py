from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.neb_agent import submission
from scripts.scheduler_evidence import query_lsf_job


def test_scheduler_query_has_a_finite_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="123 user RUN queue host exec neb Jul 27 00:00\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    evidence = query_lsf_job("123", stage="vfa")
    assert evidence["status"] == "RUN"
    assert evidence["stage"] == "vfa"
    assert captured["timeout"] == 60


def test_scheduler_timeout_cannot_produce_success_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=60)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="live LSF query timed out") as error:
        query_lsf_job("123")
    assert isinstance(error.value.__cause__, subprocess.TimeoutExpired)


def test_scheduler_unknown_status_is_not_treated_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="123 user UNKNOWN queue host exec neb Jul 27 00:00\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="unsupported live LSF status"):
        query_lsf_job("123")


def test_submission_command_timeout_preserves_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=300)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="timed out after 300 seconds") as error:
        submission._run(["ssh", "sunboquan-codex", "true"])
    assert isinstance(error.value.__cause__, subprocess.TimeoutExpired)


def test_submission_timeout_terminates_the_direct_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "child-survived"
    monkeypatch.setattr(submission, "EXTERNAL_COMMAND_TIMEOUT_SECONDS", 0.1)
    command = [
        sys.executable,
        "-c",
        (
            "import pathlib,time;"
            "time.sleep(0.8);"
            f"pathlib.Path({str(sentinel)!r}).write_text('alive')"
        ),
    ]

    with pytest.raises(RuntimeError, match="timed out after 0.1 seconds"):
        submission._run(command)
    time.sleep(1.0)

    assert not sentinel.exists()
