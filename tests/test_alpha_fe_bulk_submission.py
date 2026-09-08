from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.convergence import setup_alpha_fe_bulk_smearing as alpha
from scripts.neb_agent import submission


def _prepared_workdir(tmp_path: Path, monkeypatch) -> Path:
    workdir = tmp_path / "jobs"
    cases = [
        ("case_a", -5, 0.05),
        ("case_b", 0, 0.10),
    ]
    for label, _, _ in cases:
        job_dir = workdir / label
        job_dir.mkdir(parents=True)
        (job_dir / "run.lsf").write_text("#!/bin/sh\n", encoding="ascii")
    monkeypatch.setattr(alpha, "WORKDIR", workdir)
    monkeypatch.setattr(alpha, "CASES", cases)
    return workdir


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        ["bsub", "run.lsf"],
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_existing_success_marker_prevents_duplicate_submit(
    tmp_path: Path, monkeypatch
) -> None:
    workdir = _prepared_workdir(tmp_path, monkeypatch)
    for label, _, _ in alpha.CASES:
        (workdir / label / alpha.SUBMISSION_RECORD_FILE).write_text(
            "123\nJob <123> is submitted\n",
            encoding="ascii",
        )
    calls: list[object] = []
    monkeypatch.setattr(alpha.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    alpha.submit()

    assert calls == []


def test_unresolved_attempt_prevents_submit(tmp_path: Path, monkeypatch) -> None:
    workdir = _prepared_workdir(tmp_path, monkeypatch)
    attempt = workdir / "case_a" / alpha.SUBMISSION_ATTEMPT_FILE
    attempt.write_text("{}", encoding="utf-8")
    calls: list[object] = []
    monkeypatch.setattr(alpha.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(RuntimeError, match="retry refused") as error:
        alpha.submit()

    assert str(attempt) in str(error.value)
    assert "SUBMISSION_RECOVERY.md" in str(error.value)
    assert calls == []


def test_success_writes_original_marker_and_removes_attempt(
    tmp_path: Path, monkeypatch
) -> None:
    workdir = _prepared_workdir(tmp_path, monkeypatch)
    calls: list[dict[str, object]] = []

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        return _completed(stdout="Job <321> is submitted\n")

    monkeypatch.setattr(alpha.subprocess, "run", fake_run)
    alpha.submit()

    for label, _, _ in alpha.CASES:
        job_dir = workdir / label
        assert (job_dir / alpha.SUBMISSION_RECORD_FILE).read_text(
            encoding="ascii"
        ) == "321\nJob <321> is submitted\n"
        assert not (job_dir / alpha.SUBMISSION_ATTEMPT_FILE).exists()
        assert not list(job_dir.glob(".*.tmp"))
    assert all(
        call["timeout"] == alpha.EXTERNAL_COMMAND_TIMEOUT_SECONDS for call in calls
    )
    assert (
        alpha.EXTERNAL_COMMAND_TIMEOUT_SECONDS
        == submission.EXTERNAL_COMMAND_TIMEOUT_SECONDS
        == 300
    )


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (_completed(returncode=1, stderr="queue rejected"), "queue rejected"),
        (_completed(stdout="accepted without job identifier"), "unresolved"),
    ],
)
def test_failure_keeps_attempt_and_writes_no_success_marker(
    tmp_path: Path, monkeypatch, result, message: str
) -> None:
    workdir = _prepared_workdir(tmp_path, monkeypatch)
    monkeypatch.setattr(alpha, "CASES", alpha.CASES[:1])
    monkeypatch.setattr(alpha.subprocess, "run", lambda *args, **kwargs: result)

    with pytest.raises(RuntimeError, match=message):
        alpha.submit()

    job_dir = workdir / "case_a"
    assert (job_dir / alpha.SUBMISSION_ATTEMPT_FILE).is_file()
    assert not (job_dir / alpha.SUBMISSION_RECORD_FILE).exists()
    assert not list(job_dir.glob(".*.tmp"))


def test_timeout_keeps_attempt_and_writes_no_success_marker(
    tmp_path: Path, monkeypatch
) -> None:
    workdir = _prepared_workdir(tmp_path, monkeypatch)
    monkeypatch.setattr(alpha, "CASES", alpha.CASES[:1])

    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(alpha.subprocess, "run", time_out)
    with pytest.raises(RuntimeError, match="timed out"):
        alpha.submit()

    job_dir = workdir / "case_a"
    assert (job_dir / alpha.SUBMISSION_ATTEMPT_FILE).is_file()
    assert not (job_dir / alpha.SUBMISSION_RECORD_FILE).exists()


def test_missing_input_refuses_before_any_submit(tmp_path: Path, monkeypatch) -> None:
    workdir = _prepared_workdir(tmp_path, monkeypatch)
    (workdir / "case_b" / "run.lsf").unlink()
    calls: list[object] = []
    monkeypatch.setattr(alpha.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(FileNotFoundError, match="Submission refused"):
        alpha.submit()

    assert calls == []
    assert not any(workdir.rglob(alpha.SUBMISSION_ATTEMPT_FILE))


def test_setup_preserves_original_scientific_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "POSCAR").write_text(
        "Fe\n1\n1 0 0\n0 1 0\n0 0 1\nFe\n2\nDirect\n0 0 0\n.5 .5 .5\n",
        encoding="ascii",
    )
    (source / "POTCAR").write_text("potcar\n", encoding="ascii")
    lsf = tmp_path / "template.lsf"
    lsf.write_text("#!/bin/sh\n", encoding="ascii")
    workdir = tmp_path / "generated"
    monkeypatch.setattr(alpha, "SOURCE", source)
    monkeypatch.setattr(alpha, "LSF", lsf)
    monkeypatch.setattr(alpha, "WORKDIR", workdir)
    monkeypatch.setattr(alpha, "CASES", [("case", 1, 0.20)])

    alpha.setup()

    job_dir = workdir / "case"
    assert (job_dir / "POSCAR").read_bytes() == (source / "POSCAR").read_bytes()
    assert (job_dir / "POTCAR").read_bytes() == (source / "POTCAR").read_bytes()
    assert (job_dir / "run.lsf").read_bytes() == lsf.read_bytes()
    assert "ISMEAR = 1\nSIGMA = 0.20\n" in (job_dir / "INCAR").read_text(
        encoding="ascii"
    )
    assert (job_dir / "KPOINTS").read_text(encoding="ascii") == (
        "alpha-Fe bulk Gamma 15x15x15\n0\nGamma\n15 15 15\n0 0 0\n"
    )
