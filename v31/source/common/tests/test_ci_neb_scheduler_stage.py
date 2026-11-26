"""CI metadata is supported without changing scheduler command authority."""
import subprocess

import pytest

from scripts import scheduler_evidence as scheduler


@pytest.mark.parametrize("stage", ["ordinary_neb", "ci_neb"])
def test_bound_neb_scheduler_stage(monkeypatch, stage):
    calls = []

    def transport(argv, **kwargs):
        calls.append(argv)
        assert argv == ["ssh", "sunboquan-codex", "bjobs", "-a", "123"]
        assert not kwargs.get("shell", False)
        return subprocess.CompletedProcess(argv, 0, "JOBID USER STAT\n123 user PEND\n", "")

    monkeypatch.setattr(scheduler.subprocess, "run", transport)
    evidence = scheduler.query_lsf_job("123", stage=stage)
    assert evidence["stage"] == stage
    assert evidence["status"] == "PEND"
    scheduler.validate_stored_lsf_evidence(evidence)
    assert len(calls) == 1


def test_unsupported_stage_remains_invalid(monkeypatch):
    def transport(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "JOBID USER STAT\n123 user PEND\n", "")

    monkeypatch.setattr(scheduler.subprocess, "run", transport)
    with pytest.raises(ValueError, match="schema validation failed"):
        scheduler.query_lsf_job("123", stage="unknown_stage")
