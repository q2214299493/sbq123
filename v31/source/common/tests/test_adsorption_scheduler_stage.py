"""Ordinary adsorption metadata must not be mislabeled as a TS force label."""
import subprocess

import pytest

from scripts import scheduler_evidence as scheduler


@pytest.mark.parametrize("state", ["PEND", "RUN"])
def test_adsorption_stage_uses_unchanged_read_only_query(monkeypatch, state):
    calls = []

    def transport(argv, **kwargs):
        calls.append(argv)
        assert argv == ["ssh", "sunboquan-codex", "bjobs", "-a", "123"]
        assert not kwargs.get("shell", False)
        return subprocess.CompletedProcess(argv, 0, f"JOBID USER STAT\n123 user {state}\n", "")

    monkeypatch.setattr(scheduler.subprocess, "run", transport)
    evidence = scheduler.query_lsf_job("123", stage="adsorption_relaxation")
    assert evidence["stage"] == "adsorption_relaxation"
    assert evidence["status"] == state
    scheduler.validate_stored_lsf_evidence(evidence)
    assert len(calls) == 1
