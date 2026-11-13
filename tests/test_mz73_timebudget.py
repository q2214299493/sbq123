"""Test-only budget decisions; never create or authorize a real calculation."""
from __future__ import annotations

import shutil
import subprocess
import hashlib

import pytest
import yaml

from scripts import slurm_force_label
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json
from scripts.neb_agent import mz73_static, mz73_timebudget as budget, submission
from scripts.registry_schema import migrate_registry
from tests.test_mz73_static_submission import CONFIG, HOST, make_inputs


def reference(path):
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    case = tmp_path / "test_only_case"
    labels = case / "labels"
    labels.mkdir(parents=True)
    original, target = labels / budget.FAILED_LEAF, labels / budget.TIMEOUT_LEAF
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    old_config = config["backends"][HOST]
    from scripts.neb_agent.mz73_continuation import NAMES

    old_config.pop("continuous_active_learning", None)
    old_config["allowed_workdir_names"] = [name for name in old_config["allowed_workdir_names"] if name not in NAMES]
    old_config.pop("time_budget_extension")
    old_config["allowed_workdir_names"].remove(budget.TIMEOUT_LEAF)
    snapshot = case / "backend_at_job13907.yaml"
    snapshot.write_text(yaml.safe_dump(config), encoding="utf-8")
    old = mz73_static.load_mz73_static_backend(original.name, config_path=snapshot)
    backend = mz73_static.load_mz73_static_backend(target.name)
    make_inputs(original, old)
    with (original / "INCAR").open("a", encoding="ascii") as handle:
        handle.write("EDIFF=1e-6\nNELM=200\nLWAVE=False\nLCHARG=False\n")
    (original / "POTCAR").write_bytes(b"test-only POTCAR stand-in")
    request = load_json_object(original / mz73_static.PAPER_REQUEST)
    request["evaluation_index"] = 1
    write_json(original / mz73_static.PAPER_REQUEST, request)
    files = {name: sha256_file(original / name) for name in submission._required_files("diagnostic_static", launcher=mz73_static.LAUNCHER)}
    original_report = {
        "kind": "diagnostic_static", "passed": True, "experimental_backend": HOST, "files": files,
        "bundle_sha256": sha256_json({"kind": "diagnostic_static", "files": files}),
        "backend_config_sha256": sha256_file(snapshot),
    }
    submission.InputBundle.from_preflight(original_report).verify(original)
    write_json(original / "submission_preflight.json", original_report)
    remote = old["remote_root"] + "/" + original.name
    raw = f"JobId=13907 JobState=TIMEOUT ExitCode=0:15 WorkDir={remote} Command={remote}/script.sbatch\n"
    with monkeypatch.context() as transport:
        transport.setattr(slurm_force_label.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, raw.encode(), b""))
        terminal = slurm_force_label.query_slurm_force_label("13907", remote, original.name, config_path=snapshot)
    terminal_path = write_json(original / "slurm_13907.terminal.json", terminal)
    receipt = write_json(original / "submission_record.json", {
        "job_id": "13907", "status": "SUBMITTED", "scheduler": "Slurm", "server_alias": HOST,
        "remote_dir": remote, "bundle_sha256": original_report["bundle_sha256"],
        "gate_decision_sha256": "a" * 64, "potcar_sha256": sha256_file(original / "POTCAR"),
    })
    (original / "OUTCAR").write_text("vasp.6.4.2 running a real electronic cycle fixture\n", encoding="ascii")
    (original / "OSZICAR").write_text("DAV: 41 -100.0 0.018 0.02\n", encoding="ascii")
    (original / "vasp.out").write_text("DAV: 47 -100.0 0.018 0.02\n", encoding="ascii")
    failed_state = write_json(case / "failed_state.immutable.json", {"fixture": "TIMEOUT state raw bytes"})
    reply = case / "test_only_user_reply.txt"
    reply.write_text("TEST ONLY: synthetic explicit budget decision, no real job permission.", encoding="utf-8")
    approval = {
        "document_kind": "user_execution_budget_authorization", "decision": "approved_bounded_DFT_budget",
        "protocol_sha256": request["protocol_sha256"], "failed_job_id": "13907", "backend_id": HOST,
        "observed_hostname": "MZ73", "allowed_workdir_names": budget.SCOPE["allowed_workdir_names"],
        "resources": budget.RESOURCES.copy(), "limits": budget.LIMITS.copy(), "allow_cold_restart": True,
        "automatic_retries": 0, "source": reference(reply),
    }
    approval_path = write_json(case / "test_only_budget_authorization.json", approval)
    sources = {key: reference(path) for key, path in {
        "terminal": terminal_path, "submission": receipt, "OUTCAR": original / "OUTCAR",
        "OSZICAR": original / "OSZICAR", "stdout": original / "vasp.out",
        "failed_state": failed_state, "backend_snapshot": snapshot,
    }.items()}
    review = {
        "document_kind": "paper_timebudget_failure_evidence", "failure_stage": "dft_timeout", "job_id": "13907",
        "scheduler_state": "TIMEOUT", "native_exit_code": "0:15", "vasp_started": True,
        "electronically_converged": False, "accepted_label_count": 0, "dft_label_created": False,
        "training_performed": False, "budget_authorization_artifact_sha256": sha256_file(approval_path),
        **{key: request[key] for key in ("protocol_sha256", "evaluation_index", "candidate_structure_sha256", "search_checkpoint_sha256")},
        "failed_execution": {"job_id": "13907", "bundle_sha256": original_report["bundle_sha256"], "gate_sha256": "a" * 64},
        "source_files": sources,
        "failed_state_artifact_sha256": sources["failed_state"]["sha256"],
        "scheduler_evidence_sha256": sources["terminal"]["sha256"],
        "launcher_log_sha256": sources["stdout"]["sha256"],
    }
    review_path = write_json(case / "timeout_failure_review.json", review)
    target.mkdir()
    for name in ("INCAR", "KPOINTS", "POSCAR", "POTCAR.spec", "POTCAR"):
        shutil.copyfile(original / name, target / name)
    (target / mz73_static.LAUNCHER).write_text(mz73_static.render_launcher(backend), encoding="ascii", newline="\n")
    request.update(execution_budget_authorization=reference(approval_path), timebudget_restart={
        "failed_job_id": "13907", "failed_workdir_name": original.name, "failure_review": reference(review_path),
        "backend_snapshot": reference(snapshot), "no_new_scientific_round": True, "cold_restart": True,
    })
    write_json(target / mz73_static.PAPER_REQUEST, request)
    database = tmp_path / "learning.sqlite3"
    migrate_registry(database)
    monkeypatch.setattr(submission.subprocess, "run", lambda *a, **k: pytest.fail("no actual remote execution permitted"))
    return {"target": target, "original": original, "backend": backend, "request": request,
            "approval": approval, "approval_path": approval_path, "reply": reply,
            "review": review, "review_path": review_path, "database": database}


def validate(fixture):
    return mz73_static.validate_paper_dft_request(fixture["target"], backend=fixture["backend"])


def save_request(fixture):
    write_json(fixture["target"] / mz73_static.PAPER_REQUEST, fixture["request"])


def save_review(fixture):
    write_json(fixture["review_path"], fixture["review"])
    fixture["request"]["timebudget_restart"]["failure_review"] = reference(fixture["review_path"])
    save_request(fixture)


def save_approval(fixture):
    write_json(fixture["approval_path"], fixture["approval"])
    fixture["request"]["execution_budget_authorization"] = reference(fixture["approval_path"])
    fixture["review"]["budget_authorization_artifact_sha256"] = sha256_file(fixture["approval_path"])
    save_review(fixture)


def test_exact_budget_and_timeout_evidence_produce_preflight_evidence_only(prepared):
    original_bytes = {p.name: p.read_bytes() for p in prepared["original"].iterdir() if p.is_file()}
    result = validate(prepared)
    assert result["execution_budget_authorization"]["limits"]["max_dft_jobs"] == 2
    assert result["timebudget_restart"]["failed_job_id"] == "13907"
    assert "ALLOWED_ACTIONS" not in result
    report = submission.preflight(prepared["target"], "diagnostic_static", host=HOST, learning_database=prepared["database"])
    assert report["passed"] and report["resources"]["time_limit"] == "01:00:00"
    assert original_bytes == {p.name: p.read_bytes() for p in prepared["original"].iterdir() if p.is_file()}


def test_base_30minutes_and_two_exact_60minute_overrides():
    assert mz73_static.load_mz73_static_backend("paper_chco_aqcat25_ft512_20261112_r000_label")["time_limit"] == "00:30:00"
    assert mz73_static.load_mz73_static_backend(budget.FAILED_LEAF)["time_limit"] == "00:30:00"
    for name in (budget.TIMEOUT_LEAF, budget.NEXT_LEAF):
        backend = mz73_static.load_mz73_static_backend(name)
        assert backend["time_limit"] == "01:00:00" and backend["automatic_retries"] == 0
        assert "#SBATCH --time=01:00:00" in mz73_static.render_launcher(backend)
        assert "--time=01:00:00" in mz73_static.sbatch_command(backend, backend["remote_root"] + "/" + name)


@pytest.mark.parametrize("missing", ["execution_budget_authorization", "timebudget_restart"])
def test_missing_approval_or_timeout_proof_is_rejected(prepared, missing):
    prepared["request"].pop(missing)
    save_request(prepared)
    with pytest.raises((ValueError, KeyError)):
        validate(prepared)


@pytest.mark.parametrize("key,value", [
    ("document_kind", "budget_proposal"), ("decision", "pending_user_approval"),
    ("protocol_sha256", "f" * 64), ("failed_job_id", "13901"), ("backend_id", "aqcat_gpu"),
    ("observed_hostname", "BUCT2"), ("allow_cold_restart", False), ("automatic_retries", 1),
    ("allowed_workdir_names", [budget.TIMEOUT_LEAF]),
    ("resources", {**budget.RESOURCES, "gpus": 2}), ("resources", {**budget.RESOURCES, "gpus": True}),
    ("resources", {**budget.RESOURCES, "time_limit": "02:00:00"}),
    ("limits", {**budget.LIMITS, "max_dft_jobs": 3}), ("limits", {**budget.LIMITS, "max_training_jobs": 2}),
    ("limits", {**budget.LIMITS, "training_epochs": 101}),
], ids=["kind", "pending", "protocol", "job", "backend", "host", "cold", "retry", "names", "gpu", "boolgpu", "time", "dft", "train", "epochs"])
def test_resealed_unapproved_or_expanded_budget_is_rejected(prepared, key, value):
    prepared["approval"][key] = value
    save_approval(prepared)
    with pytest.raises(ValueError):
        validate(prepared)


def test_approval_binds_the_actual_raw_user_reply(prepared):
    prepared["reply"].write_text("changed raw reply", encoding="utf-8")
    with pytest.raises(ValueError):
        validate(prepared)


@pytest.mark.parametrize("key,value", [
    ("document_kind", "paper_prelaunch_failure_evidence"), ("failure_stage", "mpi_prelaunch"),
    ("scheduler_state", "RUNNING"), ("vasp_started", False), ("electronically_converged", True),
    ("accepted_label_count", 1), ("dft_label_created", True), ("training_performed", True),
    ("job_id", "13901"), ("budget_authorization_artifact_sha256", "f" * 64),
])
def test_resealed_wrong_failure_kind_or_facts_are_rejected(prepared, key, value):
    prepared["review"][key] = value
    save_review(prepared)
    with pytest.raises(ValueError):
        validate(prepared)


@pytest.mark.parametrize("name", ["INCAR", "KPOINTS", "POSCAR", "POTCAR.spec", "POTCAR"])
def test_timebudget_cold_rerun_preserves_all_scientific_inputs(prepared, name):
    with (prepared["target"] / name).open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError):
        validate(prepared)


@pytest.mark.parametrize("name", ["WAVECAR", "CHGCAR"])
def test_timebudget_cold_rerun_cannot_import_restart_files(prepared, name):
    (prepared["target"] / name).write_bytes(b"restart data")
    with pytest.raises(ValueError, match="cannot import"):
        validate(prepared)


def test_timeout_does_not_become_prelaunch_recovery(prepared):
    prepared["request"]["launch_recovery"] = {"failed_job_id": "13901"}
    save_request(prepared)
    with pytest.raises(ValueError):
        validate(prepared)


def test_extended_budget_still_requires_a_fresh_execution_gate(prepared):
    with pytest.raises((ValueError, FileNotFoundError)):
        submission.submit(prepared["target"], prepared["target"] / "missing_gate.json", HOST,
                          prepared["backend"]["remote_root"] + "/" + budget.TIMEOUT_LEAF,
                          "/home/sbq/sbq/private/POTCAR", sha256_file(prepared["target"] / "POTCAR"),
                          "SUBMIT_DIAGNOSTIC_VASP", learning_database=prepared["database"])
    assert not (prepared["target"] / "submission_attempt.json").exists()


def test_second_label_also_requires_the_same_explicit_budget(prepared):
    target = prepared["target"].parent / budget.NEXT_LEAF
    shutil.copytree(prepared["target"], target)
    request = load_json_object(target / mz73_static.PAPER_REQUEST)
    request.pop("timebudget_restart")
    write_json(target / mz73_static.PAPER_REQUEST, request)
    assert mz73_static.validate_paper_dft_request(target)["execution_budget_authorization"]["limits"] == budget.LIMITS
    request.pop("execution_budget_authorization")
    write_json(target / mz73_static.PAPER_REQUEST, request)
    with pytest.raises(ValueError):
        mz73_static.validate_paper_dft_request(target)


def update_source(fixture, key, payload, *, text=False):
    source = fixture["review"]["source_files"][key]
    from pathlib import Path

    path = Path(source["path"])
    if text:
        path.write_text(payload, encoding="utf-8", newline="\n")
    else:
        write_json(path, payload)
    fixture["review"]["source_files"][key] = reference(path)
    aliases = {"terminal": "scheduler_evidence_sha256", "failed_state": "failed_state_artifact_sha256",
               "stdout": "launcher_log_sha256"}
    if key in aliases:
        fixture["review"][aliases[key]] = sha256_file(path)
    save_review(fixture)


def test_empty_reply_is_not_a_new_user_approval(prepared):
    prepared["reply"].write_bytes(b"")
    prepared["approval"]["source"] = reference(prepared["reply"])
    save_approval(prepared)
    with pytest.raises(ValueError, match="nonempty raw user reply"):
        validate(prepared)


def test_native_running_evidence_cannot_be_resealed_as_timeout(prepared):
    path = prepared["original"] / "slurm_13907.terminal.json"
    terminal = load_json_object(path)
    terminal["query"]["stdout"] = terminal["query"]["stdout"].replace("TIMEOUT", "RUNNING")
    terminal["query"]["stdout_sha256"] = hashlib.sha256(terminal["query"]["stdout"].encode()).hexdigest()
    terminal["job_state"] = "RUNNING"
    update_source(prepared, "terminal", terminal)
    with pytest.raises(ValueError, match="native TIMEOUT"):
        validate(prepared)


def test_real_owner_electronic_convergence_blocks_cold_rerun_even_when_review_says_false(prepared):
    update_source(prepared, "OUTCAR", "aborting loop because EDIFF is reached\nGeneral timing and accounting informations for this job:\n", text=True)
    with pytest.raises(ValueError, match="electronically unconverged"):
        validate(prepared)


def test_no_actual_scf_step_is_not_a_dft_timeout(prepared):
    update_source(prepared, "OSZICAR", "", text=True)
    with pytest.raises(ValueError, match="VASP-started"):
        validate(prepared)


@pytest.mark.parametrize("key", ["terminal", "submission", "stdout", "OUTCAR", "OSZICAR", "failed_state", "backend_snapshot"])
def test_timeout_raw_evidence_changes_invalidate_the_request(prepared, key):
    source = prepared["review"]["source_files"][key]
    from pathlib import Path

    with Path(source["path"]).open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError):
        validate(prepared)


def test_expanded_config_scope_cannot_reopen_a_general_60minute_backend(prepared):
    backend = dict(prepared["backend"])
    backend["time_budget_extension"] = {**budget.SCOPE, "time_limit": "02:00:00"}
    with pytest.raises(ValueError):
        budget.validate_budget_scope(backend)


def test_timeout_metadata_cannot_be_borrowed_by_second_label(prepared):
    target = prepared["target"].parent / budget.NEXT_LEAF
    shutil.copytree(prepared["target"], target)
    with pytest.raises(ValueError, match="one fixed leaf"):
        mz73_static.validate_paper_dft_request(target)


def test_execution_source_must_be_the_same_raw_new_budget_reply(prepared):
    evidence = validate(prepared)["execution_budget_authorization"]
    budget.require_budget_execution_source(reference(prepared["reply"]), evidence)
    other = prepared["reply"].with_name("old_30min_reply.txt")
    other.write_bytes(prepared["reply"].read_bytes())
    with pytest.raises(ValueError, match="actual new budget reply"):
        budget.require_budget_execution_source(reference(other), evidence)
    with pytest.raises(ValueError, match="actual new budget reply"):
        budget.require_budget_execution_source({**reference(prepared["reply"]), "sha256": "a" * 64}, evidence)


@pytest.mark.parametrize("key", ["failed_state_artifact_sha256", "scheduler_evidence_sha256", "launcher_log_sha256"])
def test_state_and_physical_failure_cannot_bind_different_raw_artifacts(prepared, key):
    prepared["review"][key] = "f" * 64
    save_review(prepared)
    with pytest.raises(ValueError, match="raw source identities differ"):
        validate(prepared)
