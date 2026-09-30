from __future__ import annotations

import os
import hashlib
import shutil
import subprocess
import tarfile
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent import submission
from scripts.registry_schema import migrate_registry
from scripts.ts_strategy_engine.execution_evidence import (
    TRUSTED_ARTIFACTS, execution_evidence_sha256, workdir_identity,
)
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.ts_strategy_engine.execution_path_rules import require_local_input

HOST = "sunboquan-codex"
POTCAR = "a" * 64
ACTION = "SUBMIT_DIAGNOSTIC_VASP"


def authorize_evidence(workdir: Path, evidence: dict, *, action: str = ACTION) -> dict:
    """Test-only explicit authorization fixture; never used by production code."""
    source = workdir / "approval.txt"
    source.write_text("Test fixture: approve this exact execution scope", encoding="utf-8")
    report = evidence.get("preflight", {})
    auth = {
        "schema_version": 1, "document_kind": "user_execution_authorization",
        "action": action, "calculation_kind": report.get("kind"),
        "authorized_at": "2026-09-09T00:00:00Z",
        "source": {"path": str(source), "sha256": sha256_file(source)},
        "target": {"server_alias": HOST, "remote_dir": "~/sbq/" + workdir.name},
        "workdir_identity": workdir_identity(workdir),
        "bundle_sha256": report.get("bundle_sha256", "a" * 64),
        "evidence_sha256": execution_evidence_sha256(evidence),
    }
    if action in {"STOP_JOB", "CONTINUE_JOB"}:
        auth.update(job_id=evidence["scheduler"]["job_id"], allowed_scheduler_statuses=["PEND", "RUN"])
        auth["target"]["job_id"] = auth["job_id"]
    else:
        auth["potcar"] = {
            "source": "~/sbq/POTCAR", "sha256": POTCAR,
            "spec_sha256": report["files"]["POTCAR.spec"],
        }
    path = workdir / "user_execution_authorization.json"
    write_json(path, auth)
    evidence["authorization"] = auth
    evidence["source_bindings"]["authorization"] = {"path": str(path), "sha256": sha256_file(path)}
    return decide_execution(
        evidence["geometry"], evidence["analysis"], evidence["thresholds"],
        climb=evidence["climb"], path_reviewed=evidence["path_reviewed"],
        **{key: evidence.get(key) for key in (
            "preflight", "path_quality", "validation", "scheduler", "authorization", "source_bindings",
        )},
    )


def prepare_submission(tmp_path: Path, monkeypatch) -> tuple[Path, Path, dict]:
    workdir = tmp_path / "job"
    workdir.mkdir()
    contents = {"INCAR": "NSW=0\nIBRION=-1\n", "KPOINTS": "KPOINTS",
                "POTCAR.spec": "Fe C O", "script.lsf": "NP=1\n", "POSCAR": "test structure"}
    for name, content in contents.items():
        (workdir / name).write_text(content, encoding="ascii")
    database = tmp_path / "learning.sqlite3"
    migrate_registry(database)
    real_preflight = partial(submission.preflight, learning_database=database)
    monkeypatch.setattr(submission, "preflight", real_preflight)
    report = real_preflight(workdir, "diagnostic_static")
    assert report["passed"]
    evidence = decide_execution(
        {"status": "PASS"}, {"status": "NO_OUTPUT", "images": []}, {"test": True},
        climb=False, path_reviewed=True, preflight=report,
    )["EVIDENCE"]
    for name in ("geometry", "analysis", "thresholds", "preflight"):
        if name in TRUSTED_ARTIFACTS:
            kind, producer = TRUSTED_ARTIFACTS[name]
            evidence[name].update(document_kind=kind, producer=producer, source_files=[{
                "path": str(workdir / "INCAR"), "sha256": sha256_file(workdir / "INCAR"),
            }])
        path = workdir / ("submission_preflight.json" if name == "preflight" else name + ".json")
        write_json(path, evidence[name])
        evidence["source_bindings"][name] = {"path": str(path), "sha256": sha256_file(path)}
    decision = authorize_evidence(workdir, evidence)
    assert decision["ALLOWED_ACTIONS"] == [ACTION], decision.get("execution_authorization_error")
    path = tmp_path / "decision.json"
    write_json(path, decision)
    return workdir, path, report


def launch(workdir: Path, decision: Path, **kwargs):
    values = dict(host=HOST, remote_dir="~/sbq/" + workdir.name, potcar_source="~/sbq/POTCAR",
                  potcar_sha256=POTCAR, action=ACTION)
    values.update(kwargs)
    return submission.submit(workdir, decision, **values)


def verify_mock_upload(workdir: Path, argv, *, stdin=None):
    """Consume tar only in terminal mocks; forwarding wrappers use the sandbox."""
    assert argv[:2] == ["ssh", HOST]
    if stdin is None:
        assert "submission-reservation" in argv[-1]
        return
    assert "tar --keep-old-files --no-same-owner -xf -" in argv[-1]
    files = load_json_object(workdir / "submission_preflight.json")["files"]
    with tarfile.open(fileobj=stdin, mode="r:") as archive:
        assert {member.name for member in archive.getmembers()} == {f"{workdir.name}/{name}" for name in files}
        for name, digest in files.items():
            assert hashlib.sha256(archive.extractfile(f"{workdir.name}/{name}").read()).hexdigest() == digest


@pytest.mark.parametrize("remote", [
    "~/sbq/../job", "~/sbq/x/../../job", "/tmp/job", "/home/user/sbq/job",
    "~/other/job", "~/sbq//job", "~/sbq/./job", "~/sbq/job;echo_bad", "~/sbq",
])
def test_invalid_remote_path_rejected_before_network(tmp_path, monkeypatch, remote):
    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    monkeypatch.setattr(submission, "_run", lambda argv, *, stdin=None: pytest.fail("network must not run"))
    with pytest.raises(ValueError):
        launch(workdir, decision, remote_dir=remote)
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


@pytest.mark.parametrize("digest", ["", "hash", "a" * 63, "g" * 64, "a" * 64 + ";touch bad", "$(echo bad)"])
def test_invalid_digest_rejected_before_network(tmp_path, monkeypatch, digest):
    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    monkeypatch.setattr(submission, "_run", lambda argv, *, stdin=None: pytest.fail("network must not run"))
    with pytest.raises(ValueError, match="SHA-256"):
        launch(workdir, decision, potcar_sha256=digest)


@pytest.mark.parametrize("job_id", ["../123", "123;echo bad", "-1", "0", "123\n", "1[2]"])
def test_invalid_job_id_rejected_before_shell(tmp_path, monkeypatch, job_id):
    monkeypatch.setattr(submission, "_run", lambda argv, *, stdin=None: pytest.fail("network must not run"))
    with pytest.raises(ValueError, match="job id"):
        submission.stop_job(tmp_path / "missing.json", HOST, job_id, tmp_path / "stop.json")


@pytest.mark.parametrize("name", ["INCAR", "POSCAR", "POTCAR.spec", "script.lsf"])
def test_modified_bundle_rejected(tmp_path, monkeypatch, name):
    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    (workdir / name).write_text("changed", encoding="ascii")
    monkeypatch.setattr(submission, "_run", lambda argv, *, stdin=None: pytest.fail("network must not run"))
    with pytest.raises(ValueError, match="bundle changed"):
        launch(workdir, decision)


@pytest.mark.parametrize("name", ["analysis.json", "geometry.json", "thresholds.json", "approval.txt",
                                   "submission_preflight.json", "user_execution_authorization.json"])
def test_stale_evidence_rejected(tmp_path, monkeypatch, name):
    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    (workdir / name).write_text("{}", encoding="ascii")
    monkeypatch.setattr(submission, "_run", lambda argv, *, stdin=None: pytest.fail("network must not run"))
    with pytest.raises((ValueError, KeyError)):
        launch(workdir, decision)


def test_potcar_identity_cannot_be_substituted(tmp_path, monkeypatch):
    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    monkeypatch.setattr(submission, "_run", lambda argv, *, stdin=None: pytest.fail("network must not run"))
    with pytest.raises(ValueError, match="POTCAR"):
        launch(workdir, decision, potcar_sha256="b" * 64)
    with pytest.raises(ValueError, match="POTCAR"):
        launch(workdir, decision, potcar_source="~/sbq/other/POTCAR")


def test_concurrent_submitters_have_one_reservation_and_one_submit(tmp_path, monkeypatch):
    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    barrier = threading.Barrier(2)
    real_write = submission.write_json_exclusive
    receipts = []

    def reserve(path, payload):
        if path.name == submission.SUBMISSION_ATTEMPT_FILE:
            barrier.wait(timeout=10)
        return real_write(path, payload)

    def remote(argv, *, stdin=None):
        verify_mock_upload(workdir, argv, stdin=stdin)
        if "bsub script.lsf" in argv[-1]:
            receipts.append("submitted")
        return subprocess.CompletedProcess(argv, 0, "Job <123> is submitted", "")

    monkeypatch.setattr(submission, "write_json_exclusive", reserve)
    monkeypatch.setattr(submission, "_run", remote)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(launch, workdir, decision) for _ in range(2)]
    successes = [future.result() for future in futures if future.exception() is None]
    errors = [future.exception() for future in futures if future.exception() is not None]
    assert len(successes) == len(errors) == 1
    assert "reservation already exists" in str(errors[0])
    assert receipts == ["submitted"]
    assert submission.submission_status(workdir)["status"] == "SUBMITTED"


def test_crash_after_submit_is_unknown_and_never_retried(tmp_path, monkeypatch):
    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    real_write = submission.write_json_exclusive
    calls = []

    def crash_on_receipt(path, payload):
        if path.name == submission.SUBMISSION_RECORD_FILE:
            raise OSError("simulated process loss before receipt")
        return real_write(path, payload)

    def remote(argv, *, stdin=None):
        verify_mock_upload(workdir, argv, stdin=stdin)
        if "bsub script.lsf" in argv[-1]:
            calls.append("submitted")
        return subprocess.CompletedProcess(argv, 0, "Job <123> is submitted", "")

    monkeypatch.setattr(submission, "_run", remote)
    monkeypatch.setattr(submission, "write_json_exclusive", crash_on_receipt)
    with pytest.raises(OSError, match="process loss"):
        launch(workdir, decision)
    reservation = (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes()
    assert submission.submission_status(workdir)["status"] == submission.UNKNOWN
    with pytest.raises(RuntimeError, match="retry refused"):
        launch(workdir, decision)
    assert calls == ["submitted"]
    assert (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes() == reservation


def test_stale_evidence_after_upload_prevents_bsub(tmp_path, monkeypatch):
    workdir, decision, report = prepare_submission(tmp_path, monkeypatch)
    sandbox = RemoteSandbox(tmp_path)
    digest = bind_sandbox_potcar(workdir, decision, report, sandbox)
    calls = []
    injections = []

    def remote(argv, *, stdin=None):
        calls.append(argv)
        result = sandbox.run(argv, stdin=stdin)
        if stdin is not None:
            assert "tar --keep-old-files --no-same-owner -xf -" in argv[-1]
            assert sha256_file(sandbox.home / "sbq/job/INCAR") == report["files"]["INCAR"]
            (workdir / "analysis.json").write_text("{}", encoding="ascii")
            injections.append("after successful tar upload")
        return result

    monkeypatch.setattr(submission, "_run", remote)
    with pytest.raises(ValueError, match="execution decision authority fields do not match its evidence"):
        launch(workdir, decision, potcar_sha256=digest)
    assert injections == ["after successful tar upload"]
    assert not any("bsub script.lsf" in argv[-1] for argv in calls)
    assert not (sandbox.home / "submissions").exists()
    assert submission.submission_status(workdir)["status"] == submission.UNKNOWN
    reservation = (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes()
    call_count = len(calls)
    with pytest.raises(FileExistsError, match="submission record"):
        launch(workdir, decision, potcar_sha256=digest)
    assert len(calls) == call_count
    assert (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes() == reservation


def test_tar_stdin_preserves_bytes_paths_and_manifest_before_dispatch(tmp_path, monkeypatch):
    workdir = tmp_path / "job"
    workdir.mkdir()
    contents = {"INCAR": b"NSW=0\r\n", "00/POSCAR": b"endpoint\r\n\xff\x00",
                "01/POSCAR": b"image\r\n\x80", "script.lsf": b"NP=1\n"}
    for name, data in contents.items():
        path = workdir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (workdir / "unrequested.md").write_bytes(b"exclude")
    files = {name: sha256_file(workdir / name) for name in contents}
    sandbox = RemoteSandbox(tmp_path)
    uploads = []

    def remote(argv, *, stdin=None):
        result = sandbox.run(argv, stdin=stdin)
        if stdin is not None:
            assert "tar --keep-old-files --no-same-owner -xf -" in argv[-1]
            uploads.append("extracted")
        return result

    monkeypatch.setattr(submission, "_run", remote)
    submission._upload_manifest_files(HOST, "~/sbq", workdir, files)
    assert uploads == ["extracted"]
    uploaded = sandbox.home / "sbq/job"
    assert {p.relative_to(uploaded).as_posix() for p in uploaded.rglob("*") if p.is_file()} == set(files)
    for name, data in contents.items():
        assert (uploaded / name).read_bytes() == data
        assert sha256_file(uploaded / name) == files[name]
    assert not (sandbox.home / "submissions").exists()
    command = submission._remote_shell([
        *submission._remote_bundle_checks("~/sbq/job", files), "cd ~/sbq/job", "bsub script.lsf",
    ])
    result = remote(["ssh", HOST, command])
    assert result.stdout.strip() == "Job <123> is submitted"
    assert (sandbox.home / "submissions").read_text().splitlines() == ["submitted"]


@pytest.mark.parametrize("failure", ["transport", "unpack"])
def test_failed_tar_upload_prevents_dispatch_and_retry(tmp_path, monkeypatch, failure):
    workdir, decision, report = prepare_submission(tmp_path, monkeypatch)
    sandbox = RemoteSandbox(tmp_path)
    digest = bind_sandbox_potcar(workdir, decision, report, sandbox)
    uploads = []
    calls = []

    def remote(argv, *, stdin=None):
        calls.append(argv)
        if stdin is not None:
            assert "tar --keep-old-files --no-same-owner -xf -" in argv[-1]
            uploads.append(failure)
            if failure == "transport":
                raise RuntimeError("simulated upload transport failure")
            with tempfile.TemporaryFile() as invalid:
                invalid.write(b"not a tar archive")
                invalid.seek(0)
                return sandbox.run(argv, stdin=invalid)
        return sandbox.run(argv, stdin=stdin)

    monkeypatch.setattr(submission, "_run", remote)
    message = "simulated upload transport failure" if failure == "transport" else "tar:.*not look like a tar archive"
    with pytest.raises(RuntimeError, match=message):
        launch(workdir, decision, potcar_sha256=digest)
    assert uploads == [failure]
    assert not any("bsub script.lsf" in argv[-1] for argv in calls)
    assert not (sandbox.home / "submissions").exists()
    assert submission.submission_status(workdir)["status"] == submission.UNKNOWN
    reservation = (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes()
    call_count = len(calls)
    with pytest.raises(FileExistsError, match="submission record"):
        launch(workdir, decision, potcar_sha256=digest)
    assert len(calls) == call_count
    assert (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes() == reservation


def test_local_symlink_escape_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("outside", encoding="ascii")
    link = root / "INCAR"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"OS cannot create test symlinks: {exc}")
    with pytest.raises(ValueError, match="symlink"):
        require_local_input(root, "INCAR")


class RemoteSandbox:
    """Execute the real generated shell in a disposable HOME with a fake bsub."""
    def __init__(self, tmp_path: Path):
        self.bash = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
        if not Path(self.bash).is_file():
            pytest.skip("Bash unavailable for remote shell integration")
        self.home = tmp_path / "remote-home"
        (self.home / "sbq").mkdir(parents=True)
        (self.home / "bin").mkdir()
        stub = self.home / "bin" / "bsub"
        stub.write_text('#!/usr/bin/env bash\nprintf "submitted\\n" >> "$HOME/submissions"\nprintf "Job <123> is submitted\\n"\n', encoding="ascii")
        stub.chmod(0o700)
        self.env = {**os.environ, "HOME": self.posix(self.home)}

    @staticmethod
    def posix(path: Path) -> str:
        value = path.resolve().as_posix()
        return "/" + value[0].lower() + value[2:] if os.name == "nt" else value

    def run(self, argv, *, stdin=None):
        assert argv[:2] == ["ssh", HOST]
        command = 'export PATH="' + self.posix(self.home / "bin") + ':$PATH"; ' + argv[2]
        completed = subprocess.run([self.bash, "-c", command], env=self.env,
                                   stdin=stdin,
                                   text=True, encoding="utf-8", errors="replace",
                                   capture_output=True, timeout=15)
        if completed.returncode:
            raise RuntimeError("sandbox remote verification failed: " + completed.stderr)
        return completed


def bind_sandbox_potcar(workdir, decision, report, sandbox):
    # Bind a real test POTCAR, then regenerate the explicit scope and decision.
    potcar = sandbox.home / "sbq" / "POTCAR"
    potcar.write_text("test potential", encoding="ascii")
    digest = sha256_file(potcar)
    payload = load_json_object(decision)
    auth = payload["EVIDENCE"]["authorization"]
    auth["potcar"]["sha256"] = digest
    auth_path = workdir / "user_execution_authorization.json"
    write_json(auth_path, auth)
    evidence = payload["EVIDENCE"]
    evidence["source_bindings"]["authorization"]["sha256"] = sha256_file(auth_path)
    regenerated = decide_execution(evidence["geometry"], evidence["analysis"], evidence["thresholds"],
                                   climb=False, path_reviewed=True, preflight=report,
                                   authorization=auth, source_bindings=evidence["source_bindings"])
    write_json(decision, regenerated)
    return digest


@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("corruption", [None, "INCAR", "POSCAR", "POTCAR", "source_POTCAR", "extra"])
def test_full_remote_manifest_verified_immediately_before_bsub(tmp_path, monkeypatch, reuse, corruption):
    workdir, decision, report = prepare_submission(tmp_path, monkeypatch)
    sandbox = RemoteSandbox(tmp_path)
    digest = bind_sandbox_potcar(workdir, decision, report, sandbox)
    potcar = sandbox.home / "sbq" / "POTCAR"
    remote_dir = sandbox.home / "sbq" / "job"
    if reuse:
        remote_dir.mkdir()
        for name in report["files"]:
            shutil.copy2(workdir / name, remote_dir / name)

    def corrupt_then_run(argv, *, stdin=None):
        if "bsub script.lsf" in argv[-1] and corruption:
            target = (
                potcar if corruption == "source_POTCAR"
                else remote_dir / ("WAVECAR" if corruption == "extra" else corruption)
            )
            target.write_text("corrupted", encoding="ascii")
        return sandbox.run(argv, stdin=stdin)

    monkeypatch.setattr(submission, "_run", corrupt_then_run)
    if corruption:
        with pytest.raises(RuntimeError, match="verification failed"):
            launch(workdir, decision, reuse_uploaded=reuse, potcar_sha256=digest)
        assert not (sandbox.home / "submissions").exists()
        assert submission.submission_status(workdir)["status"] == submission.UNKNOWN
    else:
        assert launch(workdir, decision, reuse_uploaded=reuse, potcar_sha256=digest)["job_id"] == "123"
        assert (sandbox.home / "submissions").read_text().splitlines() == ["submitted"]


def test_remote_symlink_escape_rejected_by_real_shell(tmp_path):
    sandbox = RemoteSandbox(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (sandbox.home / "sbq" / "escape").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"OS cannot create shell symlink: {exc}")
    check = subprocess.run([sandbox.bash, "-c", "test -L ~/sbq/escape"], env=sandbox.env)
    assert check.returncode == 0
    with pytest.raises(RuntimeError):
        sandbox.run(["ssh", HOST, submission._remote_shell(submission._remote_path_checks("~/sbq/escape/job"))])


def test_boolean_review_is_scientific_readiness_only():
    decision = decide_execution({"status": "PASS"}, {"status": "NO_OUTPUT"}, {},
                                climb=False, path_reviewed=True,
                                preflight={"kind": "ordinary_neb", "passed": True})
    assert decision["scientific_readiness"]["eligible_actions"] == ["SUBMIT_VASP"]
    assert decision["ALLOWED_ACTIONS"] == []
    assert decision["execution_authorization"] is None


def test_current_authorized_gate_and_stale_state(tmp_path, monkeypatch):
    workdir, path, _ = prepare_submission(tmp_path, monkeypatch)
    decision = load_json_object(path)
    require_action(path, ACTION, decision["state_sha256"])
    with pytest.raises(ValueError, match="stale"):
        require_action(path, ACTION, "b" * 64)
    with pytest.raises(PermissionError):
        require_action(path, "START_DIMER", decision["state_sha256"])



@pytest.mark.parametrize("name,digest", [("../INCAR", "a" * 64), ("/INCAR", "a" * 64),
                                        ("INCAR", "$(echo bad)"), ("INCAR", "g" * 64)])
def test_remote_manifest_rejects_invalid_paths_and_digests(monkeypatch, name, digest):
    monkeypatch.setattr(submission, "_run", lambda argv, *, stdin=None: pytest.fail("network must not run"))
    with pytest.raises(ValueError):
        submission._verify_remote_bundle(HOST, "~/sbq/job", {name: digest})


@pytest.mark.parametrize("relative", ["../INCAR", "/tmp/INCAR", "C:/INCAR", "x/../../INCAR", "x/./INCAR"])
def test_local_input_traversal_rejected(tmp_path, relative):
    with pytest.raises(ValueError):
        require_local_input(tmp_path, relative)


def test_staging_detects_mutation_during_copy(tmp_path, monkeypatch):
    workdir, _, report = prepare_submission(tmp_path, monkeypatch)
    original = submission.shutil.copy2

    def corrupt_copy(source, target):
        original(source, target)
        Path(target).write_text("changed during staging", encoding="ascii")

    monkeypatch.setattr(submission.shutil, "copy2", corrupt_copy)
    monkeypatch.setattr(submission, "_run", lambda argv, *, stdin=None: pytest.fail("upload must not run"))
    with pytest.raises(ValueError, match="staged submission bundle changed"):
        submission._upload_manifest_files(HOST, "~/sbq", workdir, report["files"])


def test_preexisting_remote_reservation_blocks_other_checkout(tmp_path, monkeypatch):
    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    sandbox = RemoteSandbox(tmp_path)
    reserved = sandbox.home / "sbq" / "job.submission-reservation"
    reserved.mkdir()
    (reserved / "reservation_id").write_text("another-checkout", encoding="ascii")
    monkeypatch.setattr(submission, "_run", sandbox.run)
    with pytest.raises(RuntimeError, match="verification failed"):
        launch(workdir, decision, reuse_uploaded=True)
    assert (reserved / "reservation_id").read_text() == "another-checkout"
    assert not (sandbox.home / "submissions").exists()


def test_hard_process_death_after_bsub_keeps_unknown_reservation(tmp_path, monkeypatch):
    import sys

    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    script = """
import os, sys, subprocess
from functools import partial
from pathlib import Path
from scripts.neb_agent import submission
sys.path.insert(0, str(Path(submission.__file__).resolve().parents[2] / 'tests'))
from test_execution_lifecycle import verify_mock_upload
workdir, decision, database = map(Path, sys.argv[1:])
submission.preflight = partial(submission.preflight, learning_database=database)
def remote(argv, *, stdin=None):
    verify_mock_upload(workdir, argv, stdin=stdin)
    if 'bsub script.lsf' in argv[-1]:
        (workdir / 'mock_scheduler_accepted').write_text('123')
        os._exit(91)
    return subprocess.CompletedProcess(argv, 0, '', '')
submission._run = remote
submission.submit(workdir, decision, 'sunboquan-codex', '~/sbq/job', '~/sbq/POTCAR', 'a'*64, 'SUBMIT_DIAGNOSTIC_VASP')
"""
    process = subprocess.run([sys.executable, "-B", "-c", script, str(workdir), str(decision),
                              str(tmp_path / "learning.sqlite3")], capture_output=True, text=True, timeout=30)
    assert process.returncode == 91, process.stderr
    assert (workdir / "mock_scheduler_accepted").read_text() == "123"
    assert not (workdir / submission.SUBMISSION_RECORD_FILE).exists()
    assert submission.submission_status(workdir)["status"] == submission.UNKNOWN
    reservation = (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes()
    monkeypatch.setattr(submission, "_run", lambda argv, *, stdin=None: pytest.fail("retry must not run"))
    with pytest.raises(RuntimeError, match="UNKNOWN_NEEDS_RECONCILIATION"):
        launch(workdir, decision)
    assert (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes() == reservation


def test_scoped_stop_authorization_and_live_status_guard(tmp_path, monkeypatch):
    from scripts.scheduler_evidence import query_lsf_job

    workdir, path, _ = prepare_submission(tmp_path, monkeypatch)
    evidence = load_json_object(path)["EVIDENCE"]
    stdout = "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n123 user PEND queue host - job Sep 9 00:00\n"
    with monkeypatch.context() as context:
        context.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout, ""))
        scheduler = query_lsf_job("123", stage="neb_pilot")
    scheduler_path = workdir / "scheduler.json"
    write_json(scheduler_path, scheduler)
    evidence["scheduler"] = scheduler
    evidence["source_bindings"]["scheduler"] = {"path": str(scheduler_path), "sha256": sha256_file(scheduler_path)}
    decision = authorize_evidence(workdir, evidence, action="STOP_JOB")
    assert decision["ALLOWED_ACTIONS"] == ["STOP_JOB"], decision["execution_authorization_error"]
    write_json(path, decision)
    calls = []

    def remote(argv, *, stdin=None):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout if "bjobs" in argv else "Job <123> is terminated", "")

    monkeypatch.setattr(submission, "_run", remote)
    result = submission.stop_job(path, HOST, "123", tmp_path / "stopped.json")
    assert result["prior_status"] == "PEND"
    assert calls[-1] == ["ssh", HOST, "bkill", "123"]
    calls.clear()
    stdout = stdout.replace(" PEND ", " RUN ")
    with pytest.raises(ValueError, match="changed from PEND to RUN"):
        submission.stop_job(path, HOST, "123", tmp_path / "not_stopped.json")
    assert all("bkill" not in argv for argv in calls)
