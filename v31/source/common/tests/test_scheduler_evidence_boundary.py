from __future__ import annotations

import ast
import copy
import json
import subprocess
from pathlib import Path

import pytest

from scripts import scheduler_evidence as scheduler
from scripts.artifact_io import sha256_text
from scripts.ts_strategy_engine import active_learning_cli as cli
from scripts.ts_strategy_engine.execution_path_rules import require_job_id


INVALID_IDS = [
    "123; bkill 456 #", "123 && bsub job.lsf", "123 | bkill 456",
    "123\nbkill 456", "$(bkill 456)", "`bkill 456`", "123 456",
    "-1", "0", "abc", "", " \t ", "01", "9" * 21, "１２３",
]


@pytest.fixture
def transport(monkeypatch):
    calls = []

    def fake(argv, **kwargs):
        calls.append(argv)
        assert argv[:4] == ["ssh", "sunboquan-codex", "bjobs", "-a"]
        assert require_job_id(argv[4]) == argv[4]
        assert kwargs["timeout"] == scheduler.LSF_QUERY_TIMEOUT_SECONDS
        assert not kwargs.get("shell", False)
        return subprocess.CompletedProcess(argv, 0, f"JOBID USER STAT\n{argv[4]} user DONE\n", "")

    monkeypatch.setattr(scheduler.subprocess, "run", fake)
    return calls


@pytest.mark.parametrize("job_id", INVALID_IDS)
def test_malformed_api_identity_never_reaches_transport(transport, job_id):
    with pytest.raises(ValueError, match="invalid LSF job id"):
        scheduler.query_lsf_job(job_id)
    assert transport == []


@pytest.mark.parametrize("job_id", INVALID_IDS)
def test_malformed_cli_identity_never_dispatches_or_writes(tmp_path, transport, job_id):
    output = tmp_path / "evidence.json"
    with pytest.raises(ValueError, match="invalid LSF job id"):
        cli.main(["capture-lsf-evidence", "--job-id=" + job_id, "--output", str(output)])
    assert transport == []
    assert not output.exists()


@pytest.mark.parametrize("raw", ["1", "123", "99999999999999999999", " 123 ", 123])
def test_numeric_api_query_preserves_read_only_evidence(transport, raw):
    evidence = scheduler.query_lsf_job(raw)
    normalized = str(raw).strip()
    assert transport == [["ssh", "sunboquan-codex", "bjobs", "-a", normalized]]
    assert evidence["job_id"] == normalized
    assert evidence["status"] == "DONE"
    assert evidence["document_kind"] == "scheduler_job_evidence"
    assert evidence["source_command"] == f"ssh sunboquan-codex bjobs -a {normalized}"
    assert evidence["query"]["stdout_sha256"] == sha256_text(evidence["query"]["stdout"])
    scheduler.validate_stored_lsf_evidence(evidence, required_status="DONE")


def test_numeric_cli_writes_same_schema_without_authorization(tmp_path, transport, capsys):
    output = tmp_path / "evidence.json"
    cli.main(["capture-lsf-evidence", "--job-id", "123", "--output", str(output)])
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored == json.loads(capsys.readouterr().out)
    scheduler.validate_stored_lsf_evidence(stored, required_status="DONE")
    assert len(transport) == 1
    assert set(tmp_path.iterdir()) == {output}  # No execution reservation or gate artifact.


@pytest.mark.parametrize("job_id", INVALID_IDS)
def test_self_consistent_bad_stored_identity_cannot_trigger_live_query(transport, job_id):
    evidence = scheduler.query_lsf_job("123")
    transport.clear()
    evidence["job_id"] = job_id
    evidence["query"]["stdout"] = f"{job_id} user DONE\n"
    evidence["query"]["stdout_sha256"] = sha256_text(evidence["query"]["stdout"])
    live_calls = []

    def live(*args, **kwargs):
        live_calls.append(args)
        pytest.fail("invalid stored ID reached live-query callback")

    with pytest.raises(ValueError):
        scheduler.validate_stored_lsf_evidence(evidence, required_status="DONE")
    with pytest.raises(ValueError):
        scheduler.verify_lsf_evidence_live(evidence, required_status="DONE", live_query=live)
    assert transport == live_calls == []


def test_valid_stored_evidence_rechecks_one_live_read_only_query(transport):
    evidence = scheduler.query_lsf_job("123")
    transport.clear()
    current = scheduler.verify_lsf_evidence_live(evidence, required_status="DONE")
    assert current["job_id"] == "123" and current["status"] == "DONE"
    assert len(transport) == 1


def test_live_callback_must_return_valid_bound_identity(transport):
    evidence = scheduler.query_lsf_job("123")
    invalid = copy.deepcopy(evidence)
    invalid["job_id"] = "0"
    invalid["query"]["stdout"] = "0 user DONE\n"
    invalid["query"]["stdout_sha256"] = sha256_text(invalid["query"]["stdout"])
    with pytest.raises(ValueError, match="invalid LSF job id"):
        scheduler.verify_lsf_evidence_live(evidence, required_status="DONE", live_query=lambda *a, **k: invalid)


@pytest.mark.parametrize("job_id", INVALID_IDS)
def test_parser_cannot_treat_malformed_identity_as_expected(job_id):
    with pytest.raises(ValueError, match="invalid LSF job id"):
        scheduler._parse_lsf_bjobs(f"{job_id} user DONE\n", job_id)


def test_stage_metadata_cannot_enter_remote_command(transport):
    # Stage validation remains the schema owner's concern; it is never command text.
    with pytest.raises(ValueError):
        scheduler.query_lsf_job("123", stage="vfa; bkill 456")
    assert transport == [["ssh", "sunboquan-codex", "bjobs", "-a", "123"]]


def test_scheduler_uses_one_canonical_syntax_owner():
    assert scheduler.require_job_id is require_job_id
    root = Path(__file__).resolve().parents[1]
    definitions = []
    for path in (root / "scripts").rglob("*.py"):
        if "__pycache__" not in path.parts:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            definitions.extend(path.relative_to(root).as_posix() for node in ast.walk(tree)
                               if isinstance(node, ast.FunctionDef) and node.name == "require_job_id")
    assert definitions == ["scripts/ts_strategy_engine/execution_path_rules.py"]
    tree = ast.parse(Path(scheduler.__file__).read_text(encoding="utf-8"))
    assert not any(isinstance(node, ast.Import) and any(a.name == "re" for a in node.names)
                   for node in ast.walk(tree))
