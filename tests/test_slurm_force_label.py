from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts import slurm_force_label as scheduler
from scripts.neb_agent.mz73_static import canonical_remote_path, load_mz73_static_backend, ssh_argv


WORKDIR = "paper_chco_aqcat25_ft512_20261112_r000_label"
JOB_ID = "13880"


@pytest.fixture
def scope(tmp_path):
    config = tmp_path / "execution_backends.yaml"
    config.write_bytes((Path(__file__).resolve().parents[1] / "configs/execution_backends.yaml").read_bytes())
    backend = load_mz73_static_backend(WORKDIR, config_path=config)
    remote = backend["remote_root"] + "/" + WORKDIR
    return {"job_id": JOB_ID, "remote_dir": remote, "workdir_name": WORKDIR, "config_path": config}


def raw(scope, *, state="COMPLETED", exit_code="0:0", job_id=JOB_ID, canonical=False):
    remote = scope["remote_dir"]
    if canonical:
        backend = load_mz73_static_backend(WORKDIR, config_path=scope["config_path"])
        remote = canonical_remote_path(backend, remote)
    return (f"JobId={job_id} JobName=label UserId=sbq(1024) JobState={state} ExitCode={exit_code} "
            f"Command={remote}/script.sbatch WorkDir={remote} TresPerNode=gres/gpu:1\n")


@pytest.fixture
def transport(monkeypatch, scope):
    calls, answers = [], [raw(scope)]

    def run(argv, **kwargs):
        backend = load_mz73_static_backend(WORKDIR, config_path=scope["config_path"])
        assert argv == ssh_argv(backend, f"scontrol -o show job {JOB_ID}")
        assert kwargs == {"capture_output": True, "check": False, "timeout": scheduler.QUERY_TIMEOUT_SECONDS}
        calls.append(argv)
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, subprocess.CompletedProcess):
            return answer
        return subprocess.CompletedProcess(argv, 0, answer.encode("utf-8"), b"")

    monkeypatch.setattr(scheduler.subprocess, "run", run)
    return calls, answers


def test_capture_preserves_raw_bytes_and_native_state(scope, transport):
    evidence = scheduler.query_slurm_force_label(**scope)
    assert evidence["job_state"] == "COMPLETED" and "status" not in evidence
    assert evidence["query"]["stdout"] == raw(scope)
    assert evidence["query"]["stdout_sha256"] == hashlib.sha256(raw(scope).encode()).hexdigest()
    assert evidence["result_class"] == "scheduler_state_only"
    scheduler.validate_stored_slurm_force_label(evidence, **scope)
    assert len(transport[0]) == 1


def test_cached_completion_requires_one_fresh_same_job_query(scope, transport):
    evidence = scheduler.query_slurm_force_label(**scope)
    transport[0].clear()
    live = scheduler.verify_slurm_force_label_live(evidence, **scope)
    assert live["job_id"] == JOB_ID and len(transport[0]) == 1


def test_canonical_workdir_and_script_are_the_same_authorized_identity(scope, transport):
    transport[1][:] = [raw(scope, canonical=True)]
    evidence = scheduler.query_slurm_force_label(**scope)
    scheduler.validate_stored_slurm_force_label(evidence, **scope)


@pytest.mark.parametrize("state,exit_code", [
    ("PENDING", "0:0"), ("RUNNING", "0:0"), ("FAILED", "1:0"),
    ("CANCELLED", "0:15"), ("COMPLETED", "1:0"), ("COMPLETED", "0:9"),
    ("COMPLETED", "00:00"), ("DONE", "0:0"),
])
def test_only_native_completed_zero_exit_is_accepted(scope, transport, state, exit_code):
    transport[1][:] = [raw(scope, state=state, exit_code=exit_code)]
    evidence = scheduler.query_slurm_force_label(**scope)
    assert evidence["job_state"] == state
    with pytest.raises(ValueError, match="COMPLETED"):
        scheduler.validate_stored_slurm_force_label(evidence, **scope)


@pytest.mark.parametrize("change", [
    lambda text: text.replace("JobId=13880", "JobId=13881"),
    lambda text: text.replace("/script.sbatch", "/other.sbatch"),
    lambda text: text.replace("/script.sbatch ", "/script.sbatch --injected "),
    lambda text: text.replace("WorkDir=", "MissingWorkDir="),
    lambda text: text.replace("r000_label", "r001_label"),
    lambda text: text + text,
    lambda text: text.strip() + " JobState=RUNNING\n",
])
def test_raw_job_script_and_directory_identity_are_strict(scope, transport, change):
    transport[1][:] = [change(raw(scope))]
    with pytest.raises(ValueError):
        scheduler.query_slurm_force_label(**scope)


@pytest.mark.parametrize("job_id", ["0", "01", "-1", "１２３", "9" * 21, "13880;scancel 1", "13880\nsbatch x"])
def test_invalid_job_id_never_reaches_ssh(scope, transport, job_id):
    scope["job_id"] = job_id
    with pytest.raises(ValueError):
        scheduler.query_slurm_force_label(**scope)
    assert not transport[0]


@pytest.mark.parametrize("field,value", [
    ("job_id", "13881"), ("job_state", "RUNNING"), ("exit_code", "1:0"),
    ("document_kind", "producer_exit_record"), ("backend_config_sha256", "0" * 64),
    ("workdir_name", "another_label"), ("result_class", "accepted_dft_label"),
])
def test_tampered_cached_metadata_never_reaches_live_query(scope, transport, field, value):
    evidence = scheduler.query_slurm_force_label(**scope)
    evidence[field] = value
    transport[0].clear()
    with pytest.raises(ValueError):
        scheduler.verify_slurm_force_label_live(evidence, **scope)
    assert not transport[0]


@pytest.mark.parametrize("field,value", [
    ("stdout", "JobId=13880 JobState=COMPLETED\n"),
    ("stdout_sha256", "0" * 64), ("argv", ["ssh", "fake", "producer_exit_record.json"]),
    ("returncode", 1),
])
def test_tampered_raw_cache_never_reaches_live_query(scope, transport, field, value):
    evidence = scheduler.query_slurm_force_label(**scope)
    evidence["query"][field] = value
    transport[0].clear()
    with pytest.raises(ValueError):
        scheduler.verify_slurm_force_label_live(evidence, **scope)
    assert not transport[0]


def test_producer_exit_is_never_scheduler_authority(scope, transport):
    producer = {"document_kind": "producer_exit_record", "job_id": JOB_ID, "exit_code": 0}
    with pytest.raises(ValueError):
        scheduler.verify_slurm_force_label_live(producer, **scope)
    assert not transport[0]


def test_stale_completed_cache_is_rejected_when_live_state_changes(scope, transport):
    evidence = scheduler.query_slurm_force_label(**scope)
    transport[1][:] = [raw(scope, state="FAILED", exit_code="1:0")]
    with pytest.raises(ValueError, match="COMPLETED"):
        scheduler.verify_slurm_force_label_live(evidence, **scope)


def test_live_foreign_job_cannot_confirm_completed_cache(scope, transport):
    evidence = scheduler.query_slurm_force_label(**scope)
    transport[1][:] = [raw(scope, job_id="13881")]
    with pytest.raises(ValueError, match="different job"):
        scheduler.verify_slurm_force_label_live(evidence, **scope)


@pytest.mark.parametrize("answer,error", [
    (subprocess.CompletedProcess([], 1, b"", b"Invalid job id specified"), RuntimeError),
    (subprocess.TimeoutExpired("ssh", 20), RuntimeError),
    (subprocess.CompletedProcess([], 0, b"\xff", b""), UnicodeDecodeError),
    ("x" * (scheduler.MAX_STDOUT_BYTES + 1), ValueError),
], ids=["nonzero-query", "query-timeout", "invalid-utf8", "oversized-stdout"])
def test_query_failures_do_not_retry(scope, transport, answer, error):
    transport[1][:] = [answer]
    with pytest.raises(error):
        scheduler.query_slurm_force_label(**scope)
    assert len(transport[0]) == 1


def test_changed_backend_config_invalidates_stored_evidence(scope, transport):
    evidence = scheduler.query_slurm_force_label(**scope)
    scope["config_path"].write_bytes(scope["config_path"].read_bytes() + b"\n")
    transport[0].clear()
    with pytest.raises(ValueError, match="configuration mismatch"):
        scheduler.verify_slurm_force_label_live(evidence, **scope)
    assert not transport[0]


def test_self_consistent_raw_tampering_still_needs_live_confirmation(scope, transport):
    evidence = scheduler.query_slurm_force_label(**scope)
    evidence["query"]["stdout"] = raw(scope).replace("r000_label", "r001_label")
    evidence["query"]["stdout_sha256"] = hashlib.sha256(evidence["query"]["stdout"].encode()).hexdigest()
    evidence["remote_dir"] = evidence["remote_dir"].replace("r000_label", "r001_label")
    evidence["command"] = evidence["command"].replace("r000_label", "r001_label")
    transport[0].clear()
    with pytest.raises(ValueError, match="WorkDir"):
        scheduler.verify_slurm_force_label_live(evidence, **scope)
    assert not transport[0]
