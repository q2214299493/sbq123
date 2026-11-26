from __future__ import annotations

import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.convergence import setup_alpha_fe_bulk_smearing as alpha
from scripts.neb_agent import submission
from scripts.ts_strategy_engine.execution_gate import decide_execution
from scripts.vasp_result_gate import read_incar_values
from test_execution_lifecycle import ACTION, HOST, POTCAR, authorize_evidence, prepare_submission


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    workdir, decision, _ = prepare_submission(tmp_path, monkeypatch)
    # A real alpha static input bundle, with synthetic structures/potential metadata.
    alpha.write_incar(workdir / "INCAR", 1, 0.20)
    alpha.write_kpoints(workdir / "KPOINTS")
    (workdir / "POSCAR").write_text("Fe\n1\n1 0 0\n0 1 0\n0 0 1\nFe\n2\nDirect\n0 0 0\n.5 .5 .5\n")
    (workdir / "POTCAR.spec").write_text("Fe (synthetic test identity)\n")
    report = submission.preflight(workdir, "diagnostic_static")
    evidence = load_json_object(decision)["EVIDENCE"]
    evidence["preflight"] = report
    for name in ("geometry", "analysis", "thresholds", "preflight"):
        if "source_files" in evidence[name]:
            evidence[name]["source_files"][0]["sha256"] = sha256_file(workdir / "INCAR")
        path = workdir / ("submission_preflight.json" if name == "preflight" else name + ".json")
        write_json(path, evidence[name])
        evidence["source_bindings"][name] = {"path": str(path), "sha256": sha256_file(path)}
    write_json(decision, authorize_evidence(workdir, evidence))
    monkeypatch.setattr(alpha, "WORKDIR", tmp_path)
    monkeypatch.setattr(alpha, "CASES", [(workdir.name, 1, 0.20)])
    manifest = tmp_path / "reviewed-handoffs.json"
    write_json(manifest, {workdir.name: {
        "workdir": str(workdir), "decision_path": str(decision), "host": HOST,
        "remote_dir": "~/sbq/" + workdir.name, "potcar_source": "~/sbq/POTCAR",
        "potcar_sha256": POTCAR, "action": ACTION,
    }})
    return workdir, decision, manifest


@pytest.fixture
def fake_remote(monkeypatch):
    dispatches = []

    def remote(argv):
        if "bsub script.lsf" in argv[-1]:
            dispatches.append(argv)
        return subprocess.CompletedProcess(argv, 0, "Job <321> is submitted", "")

    monkeypatch.setattr(submission, "_run", remote)
    return dispatches


def test_alpha_positive_canonical_receipt_and_immutable_reservation(campaign, fake_remote):
    workdir, _, manifest = campaign
    alpha.submit(manifest)
    reservation = load_json_object(workdir / submission.SUBMISSION_ATTEMPT_FILE)
    receipt = submission.submission_status(workdir)
    assert receipt["status"] == "SUBMITTED"
    assert receipt["job_id"] == "321"
    assert receipt["reservation_id"] == reservation["reservation_id"]
    assert receipt["bundle_sha256"] == reservation["bundle_sha256"]
    assert reservation["status"] == submission.UNKNOWN
    assert len(fake_remote) == 1
    assert not (workdir / "submitted.jobid").exists()
    with pytest.raises(FileExistsError, match="submission record"):
        alpha.submit(manifest)
    assert len(fake_remote) == 1


def test_alpha_concurrent_callers_dispatch_once(campaign, fake_remote, monkeypatch):
    workdir, _, manifest = campaign
    barrier = threading.Barrier(2)
    original = submission.write_json_exclusive

    def synchronized_reservation(path, payload):
        if path.name == submission.SUBMISSION_ATTEMPT_FILE:
            barrier.wait(timeout=10)
        return original(path, payload)

    monkeypatch.setattr(submission, "write_json_exclusive", synchronized_reservation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(alpha.submit, manifest) for _ in range(2)]
    errors = [future.exception() for future in futures if future.exception()]
    assert len(errors) == 1
    assert "reservation already exists" in str(errors[0])
    assert len(fake_remote) == 1
    assert submission.submission_status(workdir)["status"] == "SUBMITTED"


def test_alpha_without_authorization_dispatches_zero(campaign, fake_remote):
    workdir, _, _ = campaign
    with pytest.raises(ValueError, match="CANONICAL_EXECUTION_AUTHORIZATION_REQUIRED"):
        alpha.submit()
    assert fake_remote == []
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


def test_alpha_routing_manifest_cannot_replace_execution_authorization(campaign, fake_remote):
    workdir, decision, manifest = campaign
    evidence = load_json_object(decision)["EVIDENCE"]
    write_json(decision, decide_execution(evidence["geometry"], evidence["analysis"], evidence["thresholds"],
                                         climb=False, path_reviewed=True, preflight=evidence["preflight"]))
    with pytest.raises(PermissionError, match="not authorized"):
        alpha.submit(manifest)
    assert fake_remote == []
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


@pytest.mark.parametrize("changed", ["INCAR", "KPOINTS", "script.lsf", "POTCAR.spec", "analysis.json", "approval.txt"])
def test_alpha_stale_bundle_or_evidence_dispatches_zero(campaign, fake_remote, changed):
    workdir, _, manifest = campaign
    (workdir / changed).write_text("modified after review")
    with pytest.raises(ValueError):
        alpha.submit(manifest)
    assert fake_remote == []
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


@pytest.mark.parametrize("failure", ["receipt_loss", "timeout", "missing_job_id", "rejection"])
def test_alpha_uncertain_dispatch_never_retries(campaign, monkeypatch, failure):
    workdir, _, manifest = campaign
    calls = []
    original = submission.write_json_exclusive

    def write_receipt(path, payload):
        if failure == "receipt_loss" and path.name == submission.SUBMISSION_RECORD_FILE:
            raise OSError("simulated crash before receipt")
        return original(path, payload)

    def remote(argv):
        if "bsub script.lsf" in argv[-1]:
            calls.append(argv)
            if failure == "timeout":
                raise subprocess.TimeoutExpired(argv, 300)
            if failure == "rejection":
                raise RuntimeError("fake scheduler rejection")
        output = "accepted without ID" if failure == "missing_job_id" else "Job <321> is submitted"
        return subprocess.CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr(submission, "_run", remote)
    monkeypatch.setattr(submission, "write_json_exclusive", write_receipt)
    with pytest.raises((OSError, RuntimeError, subprocess.TimeoutExpired)):
        alpha.submit(manifest)
    before = (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes()
    assert submission.submission_status(workdir)["status"] == submission.UNKNOWN
    with pytest.raises((RuntimeError, FileExistsError)):
        alpha.submit(manifest)
    assert (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes() == before
    assert len(calls) == 1


@pytest.mark.parametrize("marker", ["submitted.jobid", "submission_attempt.json"])
def test_alpha_legacy_markers_cannot_authorize_or_enable_resubmit(campaign, fake_remote, marker):
    workdir, _, manifest = campaign
    path = workdir / marker
    path.write_text("123\n" if marker.endswith("jobid") else "{}")
    before = path.read_bytes()
    with pytest.raises((ValueError, RuntimeError)):
        alpha.submit(manifest)
    assert fake_remote == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("change", ["missing_decision", "missing_script", "wrong_case", "wrong_workdir", "bad_shape"])
def test_alpha_invalid_handoff_fails_before_dispatch(campaign, fake_remote, change):
    workdir, decision, manifest = campaign
    handoffs = load_json_object(manifest)
    if change == "missing_decision":
        decision.unlink()
    elif change == "missing_script":
        (workdir / "script.lsf").unlink()
    elif change == "wrong_case":
        handoffs["unreviewed"] = handoffs.pop(workdir.name)
    elif change == "wrong_workdir":
        handoffs[workdir.name]["workdir"] = str(workdir.parent)
    else:
        handoffs[workdir.name] = None
    write_json(manifest, handoffs)
    with pytest.raises((ValueError, FileNotFoundError)):
        alpha.submit(manifest)
    assert fake_remote == []
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


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
    assert (job_dir / "script.lsf").read_bytes() == lsf.read_bytes()
    assert not (job_dir / "run.lsf").exists()
    assert (job_dir / "POTCAR.spec").read_text() == f"sha256={sha256_file(source / 'POTCAR')}\n"
    assert "ISMEAR = 1\nSIGMA = 0.20\n" in (job_dir / "INCAR").read_text(
        encoding="ascii"
    )
    assert (job_dir / "KPOINTS").read_text(encoding="ascii") == (
        "alpha-Fe bulk Gamma 15x15x15\n0\nGamma\n15 15 15\n0 0 0\n"
    )
    assert read_incar_values(job_dir / "INCAR") == {
        "SYSTEM": "alpha_Fe_bulk_smearing_convergence", "PREC": "Accurate", "ENCUT": "400",
        "EDIFF": "1E-6", "NELM": "250", "NELMIN": "5", "NSW": "0", "IBRION": "-1", "ISIF": "2",
        "GGA": "PE", "ISPIN": "2", "MAGMOM": "2*2.2", "ISMEAR": "1", "SIGMA": "0.20",
        "ALGO": "Fast", "LREAL": ".FALSE.", "LASPH": ".TRUE.", "ADDGRID": ".TRUE.", "NPAR": "2",
        "LCHARG": ".FALSE.", "LWAVE": ".FALSE.",
    }
    alpha.check()
