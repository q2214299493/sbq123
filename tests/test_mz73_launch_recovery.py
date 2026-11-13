"""Synthetic local evidence for the one reviewed launch failure; no remote jobs."""
from __future__ import annotations

import shutil
import subprocess
import hashlib
from pathlib import Path

import pytest
import yaml

from scripts import slurm_force_label
from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent import mz73_static, submission
from scripts.registry_schema import migrate_registry
from tests.test_mz73_static_submission import CONFIG, HOST, NAME, make_inputs


RECOVERY = "paper_chco_aqcat25_ft512_20261112_r000_launch_recovery01_label"


def descriptor(path):
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    case = tmp_path / "case"
    labels = case / "labels"
    labels.mkdir(parents=True)
    original, target = labels / NAME, labels / RECOVERY
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    backend_config = config["backends"][HOST]
    from scripts.neb_agent.mz73_continuation import NAMES
    from scripts.neb_agent.mz73_timebudget import TIMEOUT_LEAF

    # This snapshot predates the later timeout and continuous-round approvals.
    backend_config.pop("continuous_active_learning", None)
    backend_config.pop("time_budget_extension", None)
    backend_config["allowed_workdir_names"] = [name for name in backend_config["allowed_workdir_names"]
                                              if name not in NAMES and name != TIMEOUT_LEAF]
    backend_config.pop("launch_recovery")
    backend_config["allowed_workdir_names"].remove(RECOVERY)
    snapshot = case / "backend_at_job13901.yaml"
    snapshot.write_text(yaml.safe_dump(config), encoding="utf-8")
    backend = mz73_static.load_mz73_static_backend(RECOVERY)
    old = mz73_static.load_mz73_static_backend(NAME, config_path=snapshot)
    renderer = mz73_static.render_launcher
    loader = mz73_static.load_mz73_static_backend
    make_inputs(original, old)
    request = load_json_object(original / mz73_static.PAPER_REQUEST)
    request["evaluation_index"] = 1
    write_json(original / mz73_static.PAPER_REQUEST, request)
    (original / "POTCAR").write_bytes(b"test-only proprietary input stand-in")
    old_script = renderer(old).replace(" --bind-to none", "")
    (original / mz73_static.LAUNCHER).write_text(old_script, encoding="ascii", newline="\n")
    database = tmp_path / "learning.sqlite3"
    migrate_registry(database)
    with monkeypatch.context() as old_runtime:
        old_runtime.setattr(mz73_static, "load_mz73_static_backend", lambda *a, **k: loader(NAME, config_path=snapshot))
        old_runtime.setattr(mz73_static, "render_launcher", lambda b: old_script)
        report = submission.preflight(original, "diagnostic_static", host=HOST, learning_database=database)
    assert report["passed"]
    remote = old["remote_root"] + "/" + NAME
    raw = f"JobId=13901 JobState=FAILED ExitCode=131:0 WorkDir={remote} Command={remote}/script.sbatch\n"
    with monkeypatch.context() as transport:
        transport.setattr(slurm_force_label.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, raw.encode(), b""))
        terminal = slurm_force_label.query_slurm_force_label("13901", remote, NAME, config_path=snapshot)
    terminal_path = write_json(original / "slurm_13901.terminal.json", terminal)
    producer = write_json(original / "producer_exit_record.json", {"job_id": "13901", "exit_code": 131})
    stdout = original / "vasp.out"
    stdout.write_text("hwloc_set_cpubind: killed without launching the target application\n", encoding="ascii")
    receipt = write_json(original / "submission_record.json", {
        "status": "SUBMITTED", "job_id": "13901", "scheduler": "Slurm", "server_alias": HOST,
        "remote_dir": remote, "bundle_sha256": report["bundle_sha256"],
        "gate_decision_sha256": "e" * 64, "potcar_sha256": sha256_file(original / "POTCAR"),
    })
    failed_state = write_json(case / "failed_state.immutable.json", {"fixture": "failed state raw bytes"})
    probe_root = case / "mpi_binding_probe_13901"
    probe_root.mkdir()
    probe = write_json(probe_root / "probe.json", {"cuda": True})
    probe_remote = old["remote_root"].rsplit("/", 1)[0] + "/mpi_binding_probe_13901"
    probe_terminal = probe_root / "scontrol.raw.txt"
    probe_terminal.write_text(
        f"JobId=13902 JobState=COMPLETED ExitCode=0:0 WorkDir={probe_remote} Command={probe_remote}/probe.sh\n",
        encoding="ascii",
    )
    sources = {key: descriptor(path) for key, path in {
        "terminal": terminal_path, "stdout": stdout, "producer": producer, "submission": receipt,
        "failed_state": failed_state, "MPI_probe": probe, "MPI_probe_terminal": probe_terminal,
        "backend_snapshot": snapshot,
    }.items()}
    review = {
        "document_kind": "paper_prelaunch_failure_evidence", "job_id": "13901", "native_state": "FAILED",
        "native_exit_code": "131:0", "VASP_started": False, "accepted_label_count": 0,
        "training_performed": False, "failure_stage": "mpi_prelaunch", "vasp_started": False,
        "dft_label_created": False,
        "remote_absence_check": {"command": "test absence of OUTCAR OSZICAR CONTCAR", "returncode": 0},
        "source_files": sources,
        **{key: request[key] for key in ("protocol_sha256", "evaluation_index", "candidate_structure_sha256", "search_checkpoint_sha256")},
        "failed_execution": {"job_id": "13901", "bundle_sha256": report["bundle_sha256"], "gate_sha256": "e" * 64},
        "failed_state_artifact_sha256": sources["failed_state"]["sha256"],
        "scheduler_evidence_sha256": sources["terminal"]["sha256"],
        "launcher_log_sha256": sources["stdout"]["sha256"],
    }
    review_path = write_json(case / "failure_review.v2.json", review)
    target.mkdir()
    for name in ("POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "POTCAR"):
        shutil.copyfile(original / name, target / name)
    (target / mz73_static.LAUNCHER).write_text(renderer(backend), encoding="ascii", newline="\n")
    write_json(target / mz73_static.PAPER_REQUEST, {**request, "launch_recovery": {
        "failed_job_id": "13901", "failed_workdir_name": NAME,
        "failure_review": descriptor(review_path), "backend_snapshot": descriptor(snapshot),
        "no_new_scientific_round": True,
    }})
    monkeypatch.setattr(submission.subprocess, "run", lambda *a, **k: pytest.fail("no remote call permitted"))
    return {"target": target, "original": original, "backend": backend, "review_path": review_path,
            "review": review, "snapshot": snapshot, "database": database, "old_script": old_script}


def validate(fixture):
    return mz73_static.validate_paper_dft_request(fixture["target"], backend=fixture["backend"])


def rebind_review(fixture):
    write_json(fixture["review_path"], fixture["review"])
    path = fixture["target"] / mz73_static.PAPER_REQUEST
    request = load_json_object(path)
    request["launch_recovery"]["failure_review"] = descriptor(fixture["review_path"])
    write_json(path, request)


def test_recovery_binds_frozen_native_failure_and_preserves_original_inputs(recovery):
    frozen = {p.name: p.read_bytes() for p in recovery["original"].iterdir() if p.is_file()}
    result = validate(recovery)
    assert result["launch_recovery"]["failed_job_id"] == "13901"
    assert result["launch_recovery"]["potcar_sha256"] == sha256_file(recovery["target"] / "POTCAR")
    assert "ALLOWED_ACTIONS" not in result and "submission_allowed" not in result
    assert frozen == {p.name: p.read_bytes() for p in recovery["original"].iterdir() if p.is_file()}
    assert "--bind-to none -np 1 " in mz73_static.render_launcher(recovery["backend"])
    assert "--bind-to none" not in recovery["old_script"]


def test_recovery_preflight_is_real_and_requires_new_launcher(recovery):
    report = submission.preflight(recovery["target"], "diagnostic_static", host=HOST, learning_database=recovery["database"])
    assert report["passed"] and report["paper_dft_request"]["launch_recovery"]["failed_job_id"] == "13901"
    (recovery["target"] / mz73_static.LAUNCHER).write_text(recovery["old_script"], encoding="ascii", newline="\n")
    assert not submission.preflight(recovery["target"], "diagnostic_static", host=HOST, learning_database=recovery["database"])["passed"]


@pytest.mark.parametrize("name", ["INCAR", "KPOINTS", "POTCAR.spec", "POTCAR", "POSCAR"])
def test_recovery_rejects_any_changed_scientific_input(recovery, name):
    with (recovery["target"] / name).open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError):
        validate(recovery)


@pytest.mark.parametrize("key,value", [
    ("VASP_started", True), ("vasp_started", True), ("dft_label_created", True),
    ("native_state", "COMPLETED"), ("native_exit_code", "0:0"), ("accepted_label_count", 1),
    ("training_performed", True), ("failure_stage", "vasp_scf"), ("evaluation_index", 2),
    ("candidate_structure_sha256", "a" * 64), ("scheduler_evidence_sha256", "a" * 64),
])
def test_recovery_rejects_resealed_inconsistent_failure_review(recovery, key, value):
    recovery["review"][key] = value
    rebind_review(recovery)
    with pytest.raises(ValueError):
        validate(recovery)


@pytest.mark.parametrize("key", ["terminal", "stdout", "producer", "submission", "failed_state", "MPI_probe", "MPI_probe_terminal", "backend_snapshot"])
def test_recovery_rejects_changed_raw_source(recovery, key):
    with Path(recovery["review"]["source_files"][key]["path"]).open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError):
        validate(recovery)


@pytest.mark.parametrize("name", ["OUTCAR", "OSZICAR", "CONTCAR", "vasprun.xml"])
def test_recovery_refuses_an_original_job_with_vasp_outputs(recovery, name):
    (recovery["original"] / name).write_bytes(b"actual output present")
    with pytest.raises(ValueError, match="VASP outputs"):
        validate(recovery)


def test_recovery_cannot_authorize_submission_without_a_fresh_gate(recovery):
    with pytest.raises((ValueError, FileNotFoundError)):
        submission.submit(recovery["target"], recovery["target"] / "missing_gate.json", HOST,
                          recovery["backend"]["remote_root"] + "/" + RECOVERY,
                          "/home/sbq/sbq/private/POTCAR", sha256_file(recovery["target"] / "POTCAR"),
                          "SUBMIT_DIAGNOSTIC_VASP", learning_database=recovery["database"])
    assert not (recovery["target"] / "submission_attempt.json").exists()


def test_recovery_metadata_is_not_allowed_on_a_scientific_round_leaf(recovery):
    path = recovery["original"] / mz73_static.PAPER_REQUEST
    write_json(path, load_json_object(recovery["target"] / mz73_static.PAPER_REQUEST))
    with pytest.raises(ValueError, match="scientific-round leaf"):
        mz73_static.validate_paper_dft_request(recovery["original"])


def test_recovery_requires_explicit_once_only_backend_registration(recovery):
    backend = dict(recovery["backend"])
    backend["launch_recovery"] = {**backend["launch_recovery"], "maximum_attempts": 2}
    with pytest.raises(ValueError):
        mz73_static._validate_fixed_scope(backend)


def update_source(fixture, key, payload):
    path = Path(fixture["review"]["source_files"][key]["path"])
    write_json(path, payload)
    fixture["review"]["source_files"][key] = descriptor(path)
    aliases = {"terminal": "scheduler_evidence_sha256", "stdout": "launcher_log_sha256",
               "failed_state": "failed_state_artifact_sha256"}
    if key in aliases:
        fixture["review"][aliases[key]] = sha256_file(path)
    rebind_review(fixture)


@pytest.mark.parametrize("key,value", [("job_id", "13903"), ("bundle_sha256", "a" * 64)])
def test_recovery_rejects_wrong_receipt_with_resealed_sources(recovery, key, value):
    path = Path(recovery["review"]["source_files"]["submission"]["path"])
    receipt = load_json_object(path)
    receipt[key] = value
    update_source(recovery, "submission", receipt)
    with pytest.raises(ValueError, match="original submission"):
        validate(recovery)


def test_recovery_rejects_a_successful_original_scheduler_record_even_when_resealed(recovery):
    path = Path(recovery["review"]["source_files"]["terminal"]["path"])
    terminal = load_json_object(path)
    terminal["query"]["stdout"] = terminal["query"]["stdout"].replace("FAILED", "COMPLETED").replace("131:0", "0:0")
    terminal["query"]["stdout_sha256"] = hashlib.sha256(terminal["query"]["stdout"].encode()).hexdigest()
    terminal.update(job_state="COMPLETED", exit_code="0:0")
    update_source(recovery, "terminal", terminal)
    with pytest.raises(ValueError, match="native prelaunch failure"):
        validate(recovery)


def test_recovery_requires_successful_probe_cuda_evidence_even_when_resealed(recovery):
    update_source(recovery, "MPI_probe", {"cuda": False})
    with pytest.raises(ValueError, match="successful CUDA/MPI probe"):
        validate(recovery)


def test_recovery_requires_native_completed_probe_even_when_resealed(recovery):
    path = Path(recovery["review"]["source_files"]["MPI_probe_terminal"]["path"])
    path.write_text(path.read_text().replace("COMPLETED", "FAILED"), encoding="ascii")
    recovery["review"]["source_files"]["MPI_probe_terminal"] = descriptor(path)
    rebind_review(recovery)
    with pytest.raises(ValueError, match="successful CUDA/MPI probe"):
        validate(recovery)


def test_recovery_rejects_evidence_from_another_original_directory(recovery):
    source = Path(recovery["review"]["source_files"]["submission"]["path"])
    other = source.parent.parent / "unrelated_submission.json"
    other.write_bytes(source.read_bytes())
    recovery["review"]["source_files"]["submission"] = descriptor(other)
    rebind_review(recovery)
    with pytest.raises(ValueError, match="another original directory"):
        validate(recovery)


def test_recovery_rejects_changed_original_input_bundle(recovery):
    with (recovery["original"] / mz73_static.LAUNCHER).open("ab") as handle:
        handle.write(b"changed old launcher")
    with pytest.raises(ValueError, match="submission bundle changed"):
        validate(recovery)
