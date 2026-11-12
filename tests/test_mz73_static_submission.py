from __future__ import annotations

import subprocess
import sys
from functools import partial
from pathlib import Path

import pytest
import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent import mz73_static, submission
from scripts.registry_schema import migrate_registry
from scripts.ts_strategy_engine.execution_evidence import TRUSTED_ARTIFACTS, execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution
from scripts.ts_strategy_engine.learning_store import history_token, save_event


NAME = "paper_chco_aqcat25_ft512_20261112_r000_label"
HOST = mz73_static.BACKEND_ID
ACTION = "SUBMIT_DIAGNOSTIC_VASP"
POTCAR_HASH = "a" * 64
CONFIG = Path(__file__).resolve().parents[1] / "configs/execution_backends.yaml"


def make_inputs(workdir: Path, backend: dict) -> None:
    workdir.mkdir()
    for name, text in {
        "INCAR": "NSW=0\nIBRION=-1\nNPAR=1\nNCORE=1\nKPAR=1\nISPIN=2\nENCUT=450\n",
        "KPOINTS": "test-only KPOINTS\n", "POSCAR": "test-only POSCAR\n", "POTCAR.spec": "Fe C O H\n",
        mz73_static.LAUNCHER: mz73_static.render_launcher(backend),
    }.items():
        (workdir / name).write_text(text, encoding="ascii", newline="\n")
    write_json(workdir / mz73_static.PAPER_REQUEST, {
        "document_kind": "paper_sequential_DFT_request", "calculation": "exact_structure_static_single_point",
        "requires_exact_structure_hash_gate": True, "requires_authoritative_execution_gate": True,
        "protocol_sha256": "0" * 64, "candidate_structure_sha256": sha256_file(workdir / "POSCAR"),
        "search_checkpoint_sha256": "1" * 64,
        "contract_sha256": backend["reviewed_contract"]["contract_sha256"],
        "compatibility_sha256": backend["reviewed_contract"]["compatibility_sha256"],
    })


def prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, dict, dict]:
    """Build a real gate with explicit test-only authorization; no remote calls."""
    backend = mz73_static.load_mz73_static_backend(NAME)
    workdir = tmp_path / NAME
    make_inputs(workdir, backend)
    database = tmp_path / "learning.sqlite3"
    migrate_registry(database)
    real_preflight = partial(submission.preflight, learning_database=database)
    monkeypatch.setattr(submission, "preflight", real_preflight)
    report = real_preflight(workdir, "diagnostic_static", host=HOST)
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
        source = workdir / ("submission_preflight.json" if name == "preflight" else name + ".json")
        write_json(source, evidence[name])
        evidence["source_bindings"][name] = {"path": str(source), "sha256": sha256_file(source)}
    approval = workdir / "test_authorization.txt"
    approval.write_text("Test-only permission for this exact fixture; never authorizes a real calculation.")
    auth = {
        "schema_version": 1, "document_kind": "user_execution_authorization", "action": ACTION,
        "calculation_kind": "diagnostic_static", "authorized_at": "2026-11-12T00:00:00Z",
        "source": {"path": str(approval), "sha256": sha256_file(approval)},
        "target": {"server_alias": HOST, "remote_dir": backend["remote_root"] + "/" + NAME},
        "workdir_identity": workdir_identity(workdir), "bundle_sha256": report["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(evidence),
        "potcar": {"source": "/home/sbq/sbq/approved/POTCAR", "sha256": POTCAR_HASH,
                   "spec_sha256": report["files"]["POTCAR.spec"]},
    }
    auth_path = workdir / "user_execution_authorization.json"
    write_json(auth_path, auth)
    evidence["authorization"] = auth
    evidence["source_bindings"]["authorization"] = {"path": str(auth_path), "sha256": sha256_file(auth_path)}
    decision = decide_execution(
        evidence["geometry"], evidence["analysis"], evidence["thresholds"], climb=False, path_reviewed=True,
        preflight=report, authorization=auth, source_bindings=evidence["source_bindings"],
    )
    assert decision["ALLOWED_ACTIONS"] == [ACTION], decision.get("execution_authorization_error")
    decision_path = tmp_path / "decision.json"
    write_json(decision_path, decision)
    return workdir, decision_path, report, backend


def launch(workdir: Path, gate: Path, backend: dict, **changes):
    arguments = {
        "host": HOST, "remote_dir": backend["remote_root"] + "/" + workdir.name,
        "potcar_source": "/home/sbq/sbq/approved/POTCAR", "potcar_sha256": POTCAR_HASH, "action": ACTION,
    }
    arguments.update(changes)
    return submission.submit(workdir, gate, **arguments)


def test_mz73_preflight_binds_real_script_and_only_parallel_overrides(tmp_path, monkeypatch):
    workdir, _, report, backend = prepare(tmp_path, monkeypatch)
    assert report["experimental_backend"] == HOST
    assert report["scheduler"] == "Slurm" and report["cores"] == 1
    assert report["resources"]["gpus"] == report["resources"]["mpi_ranks"] == 1
    assert report["resources"]["cpus_per_task"] == 4
    assert report["gpu_parallel_overrides"] == {"NPAR": 1, "NCORE": 1, "KPAR": 1}
    assert report["backend_config_sha256"] == sha256_file(CONFIG)
    assert report["files"]["script.sbatch"] == sha256_file(workdir / "script.sbatch")
    assert report["files"][mz73_static.PAPER_REQUEST] == report["paper_dft_request"]["request_sha256"]
    assert "script.lsf" not in report["files"]
    assert "ENCUT=450" in (workdir / "INCAR").read_text()
    assert "--bind-to none -np 1 " + backend["vasp_executable"] in mz73_static.render_launcher(backend)


def test_mz73_preflight_requires_the_bound_paper_DFT_request(tmp_path, monkeypatch):
    workdir, _, _, _ = prepare(tmp_path, monkeypatch)
    (workdir / mz73_static.PAPER_REQUEST).unlink()
    report = submission.preflight(workdir, "diagnostic_static", host=HOST)
    assert not report["passed"] and "missing:" + mz73_static.PAPER_REQUEST in report["errors"]


def test_mz73_preflight_rejects_a_request_for_another_candidate(tmp_path, monkeypatch):
    workdir, _, _, _ = prepare(tmp_path, monkeypatch)
    path = workdir / mz73_static.PAPER_REQUEST
    request = load_json_object(path)
    request["candidate_structure_sha256"] = "f" * 64
    write_json(path, request)
    report = submission.preflight(workdir, "diagnostic_static", host=HOST)
    assert not report["passed"]
    assert any(error.startswith("invalid_paper_DFT_request:") for error in report["errors"])


@pytest.mark.parametrize("replacement", ["--gres=gpu:2", "--ntasks=2", "--cpus-per-task=8", "--mem=32G", "--requeue"])
def test_mz73_launcher_cannot_expand_bound_resources(tmp_path, monkeypatch, replacement):
    workdir, _, _, _ = prepare(tmp_path, monkeypatch)
    launcher = workdir / "script.sbatch"
    launcher.write_text(launcher.read_text() + "\n#SBATCH " + replacement + "\n", encoding="ascii")
    report = submission.preflight(workdir, "diagnostic_static", host=HOST)
    assert not report["passed"]
    assert any(error.startswith("invalid_mz73_launcher:") for error in report["errors"])


@pytest.mark.parametrize("key", ["NPAR", "NCORE", "KPAR"])
def test_mz73_parallel_overrides_are_explicitly_required(tmp_path, monkeypatch, key):
    workdir, _, _, _ = prepare(tmp_path, monkeypatch)
    incar = workdir / "INCAR"
    incar.write_text(incar.read_text().replace(key + "=1", key + "=4"), encoding="ascii")
    report = submission.preflight(workdir, "diagnostic_static", host=HOST)
    assert not report["passed"] and "mz73_static_requires_" + key + "_1" in report["errors"]


@pytest.mark.parametrize("kind", ["ordinary_neb", "neb_pilot", "ci_neb", "dimer", "vfa", "connectivity_relax"])
def test_mz73_backend_refuses_all_other_calculation_kinds(tmp_path, kind):
    with pytest.raises(ValueError, match="diagnostic_static"):
        submission.preflight(tmp_path / NAME, kind, host=HOST)


@pytest.mark.parametrize("controls", ["IMAGES=1", "ICHAIN=2", "LCLIMB=.TRUE."])
def test_static_kind_cannot_hide_NEB_or_DIMER_controls(tmp_path, monkeypatch, controls):
    workdir, _, _, _ = prepare(tmp_path, monkeypatch)
    incar = workdir / "INCAR"
    incar.write_text(incar.read_text() + controls + "\n", encoding="ascii")
    report = submission.preflight(workdir, "diagnostic_static", host=HOST)
    assert not report["passed"]
    assert "mz73_static_forbids_NEB_and_DIMER_controls" in report["errors"]


def test_mz73_backend_does_not_exist_without_explicit_registration(tmp_path):
    payload = yaml.safe_load(CONFIG.read_text())
    del payload["backends"][HOST]
    missing = tmp_path / "backends.yaml"
    missing.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="not explicitly registered"):
        mz73_static.load_mz73_static_backend(NAME, config_path=missing)


@pytest.mark.parametrize("key,value", [("gpus", 2), ("mpi_ranks", 2), ("requeue", True), ("time_limit", "00:31:00")])
def test_mz73_backend_configuration_cannot_expand_resource_scope(tmp_path, key, value):
    payload = yaml.safe_load(CONFIG.read_text())
    payload["backends"][HOST][key] = value
    changed = tmp_path / "backends.yaml"
    changed.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        mz73_static.load_mz73_static_backend(NAME, config_path=changed)


@pytest.mark.parametrize("name", ["job", "paper_chco_aqcat25_ft512_20261112_r002_label"])
def test_wrong_experiment_scope_rejected_before_files_or_network(tmp_path, monkeypatch, name):
    monkeypatch.setattr(submission, "_run", lambda argv: pytest.fail("network must not run"))
    with pytest.raises(ValueError, match="scoped"):
        submission.submit(tmp_path / name, tmp_path / "none.json", HOST, "/tmp/none", "/tmp/POTCAR", POTCAR_HASH, ACTION)


@pytest.mark.parametrize("path", [
    "/tmp/POTCAR", "/home/sbq/sbq-other/POTCAR", "/home/sbq/sbq/../POTCAR",
    "/home/sbq/sbq//POTCAR", "/home/sbq/sbq/a;echo_bad", "/home/ubuntu/hdd/sbq/sbq/POTCAR",
])
def test_mz73_paths_reject_escape_traversal_and_shell_metacharacters(path):
    backend = mz73_static.load_mz73_static_backend(NAME)
    with pytest.raises(ValueError):
        mz73_static.require_mz73_path(backend, path)


@pytest.mark.parametrize("remote", [
    "/home/sbq/sbq/another_case/" + NAME,
    "/home/sbq/sbq/chco_paper_aqcat25_ft512_20261112_v1/labels/another_leaf",
])
def test_scoped_leaf_cannot_target_another_case_root(tmp_path, monkeypatch, remote):
    workdir, gate, _, backend = prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(submission, "_run", lambda argv: pytest.fail("network must not run"))
    with pytest.raises(ValueError, match="exact experiment root"):
        launch(workdir, gate, backend, remote_dir=remote)
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


def test_known_canonical_root_is_allowed_but_symlinks_below_it_are_checked():
    backend = mz73_static.load_mz73_static_backend(NAME)
    target = backend["remote_root"] + "/" + NAME
    expected = "/home/ubuntu/hdd/sbq/sbq/" + target.removeprefix("/home/sbq/sbq/")
    assert mz73_static.canonical_remote_path(backend, target) == expected
    checks = mz73_static.remote_path_checks(backend, target)
    assert 'realpath -e -- /home/sbq/sbq' in checks[0]
    assert expected in checks[1]
    assert "test ! -L /home/sbq/sbq" not in checks
    assert "test ! -L " + target in checks


def test_missing_gate_and_stale_bundle_never_reach_network(tmp_path, monkeypatch):
    workdir, gate, _, backend = prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(submission, "_run", lambda argv: pytest.fail("network must not run"))
    with pytest.raises(FileNotFoundError):
        launch(workdir, tmp_path / "missing.json", backend)
    (workdir / "script.sbatch").write_text("changed", encoding="ascii")
    with pytest.raises(ValueError, match="bundle changed"):
        launch(workdir, gate, backend)
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


def test_missing_action_in_real_gate_refuses_submission(tmp_path, monkeypatch):
    workdir, gate, _, backend = prepare(tmp_path, monkeypatch)
    payload = load_json_object(gate)
    payload["ALLOWED_ACTIONS"] = []
    write_json(gate, payload)
    monkeypatch.setattr(submission, "_run", lambda argv: pytest.fail("network must not run"))
    with pytest.raises((ValueError, PermissionError)):
        launch(workdir, gate, backend)


def test_stale_authorization_source_refuses_submission(tmp_path, monkeypatch):
    workdir, gate, _, backend = prepare(tmp_path, monkeypatch)
    (workdir / "test_authorization.txt").write_text("changed")
    monkeypatch.setattr(submission, "_run", lambda argv: pytest.fail("network must not run"))
    with pytest.raises(ValueError):
        launch(workdir, gate, backend)


def test_mz73_submission_uses_real_ssh_metadata_and_native_sbatch_id(tmp_path, monkeypatch):
    workdir, gate, report, backend = prepare(tmp_path, monkeypatch)
    calls = []

    def remote(argv):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "2468\n" if "sbatch --parsable" in argv[-1] else "", "")

    monkeypatch.setattr(submission, "_run", remote)
    result = launch(workdir, gate, backend)
    assert result["job_id"] == "2468" and result["scheduler"] == "Slurm" and result["server_alias"] == HOST
    assert result["bundle_sha256"] == report["bundle_sha256"]
    submitted = [argv for argv in calls if "sbatch --parsable" in argv[-1]]
    assert len(submitted) == 1
    assert "-p" in submitted[0] and submitted[0][submitted[0].index("-p") + 1] == "36039"
    assert "sbq@10sx4jr711576.vicp.fun" in submitted[0]
    assert "IdentitiesOnly=yes" in submitted[0]
    assert HOST not in submitted[0]
    command = submitted[0][-1]
    assert "--ntasks=1" in command and "--gres=gpu:1" in command and "--no-requeue" in command
    assert "script.sbatch" in command and "bsub script.lsf" not in command
    assert "realpath -m" in command and "sha256sum" in command
    scp = [argv for argv in calls if argv[0] == "scp"]
    assert len(scp) == 1 and "-P" in scp[0]
    assert submission.submission_status(workdir)["status"] == "SUBMITTED"
    with pytest.raises(FileExistsError):
        launch(workdir, gate, backend)
    assert len([argv for argv in calls if "sbatch --parsable" in argv[-1]]) == 1


@pytest.mark.parametrize("stdout", ["Job <2468> is submitted", "2468\n2469\n", "warning\n2468\n", "0\n", "2468;bad;extra\n"])
def test_sbatch_output_is_never_faked_as_LSF_or_multiple_jobs(stdout):
    with pytest.raises(ValueError, match="Slurm job ID"):
        mz73_static.parse_sbatch_job_id(stdout)


def test_sbatch_failure_preserves_unknown_reservation_and_prevents_retry(tmp_path, monkeypatch):
    workdir, gate, _, backend = prepare(tmp_path, monkeypatch)
    calls = []

    def remote(argv):
        if "sbatch --parsable" in argv[-1]:
            calls.append(argv)
            raise RuntimeError("simulated scheduler/transport loss")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(submission, "_run", remote)
    with pytest.raises(RuntimeError, match="transport loss"):
        launch(workdir, gate, backend)
    assert submission.submission_status(workdir)["status"] == submission.UNKNOWN
    before = (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes()
    with pytest.raises(FileExistsError):
        launch(workdir, gate, backend)
    assert before == (workdir / submission.SUBMISSION_ATTEMPT_FILE).read_bytes()
    assert len(calls) == 1


def test_stale_evidence_after_upload_blocks_the_actual_sbatch(tmp_path, monkeypatch):
    workdir, gate, _, backend = prepare(tmp_path, monkeypatch)
    submitted = []

    def remote(argv):
        if argv[0] == "scp":
            (workdir / "test_authorization.txt").write_text("authorization changed during upload")
        if "sbatch --parsable" in argv[-1]:
            submitted.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(submission, "_run", remote)
    with pytest.raises(ValueError):
        launch(workdir, gate, backend)
    assert submitted == []
    assert submission.submission_status(workdir)["status"] == submission.UNKNOWN


def test_explicit_learning_database_is_used_by_all_three_fresh_checks(tmp_path, monkeypatch):
    workdir, gate, report, backend = prepare(tmp_path, monkeypatch)
    database = tmp_path / "learning.sqlite3"
    assert report["learning_database"] == {
        "path": str(database.resolve(strict=True)), "strategy_history_sha256": history_token(database),
    }
    real_preflight = submission.preflight.func
    seen = []

    def observed_preflight(*args, **kwargs):
        seen.append(kwargs.get("learning_database"))
        return real_preflight(*args, **kwargs)

    def remote(argv):
        return subprocess.CompletedProcess(argv, 0, "2468\n" if "sbatch --parsable" in argv[-1] else "", "")

    monkeypatch.setattr(submission, "preflight", observed_preflight)
    monkeypatch.setattr(submission, "_run", remote)
    result = launch(workdir, gate, backend, learning_database=database)
    assert result["job_id"] == "2468"
    assert seen == [database, database, database]


def test_missing_custom_learning_database_cannot_be_created_or_submitted(tmp_path, monkeypatch):
    workdir, gate, _, backend = prepare(tmp_path, monkeypatch)
    missing = tmp_path / "missing.sqlite3"
    monkeypatch.setattr(submission, "_run", lambda argv: pytest.fail("network must not run"))
    with pytest.raises(ValueError, match="registry database not found"):
        launch(workdir, gate, backend, learning_database=missing)
    assert not missing.exists()
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


def test_another_empty_database_does_not_replace_the_reviewed_history_source(tmp_path, monkeypatch):
    workdir, gate, _, backend = prepare(tmp_path, monkeypatch)
    other = tmp_path / "other.sqlite3"
    migrate_registry(other)
    monkeypatch.setattr(submission, "_run", lambda argv: pytest.fail("network must not run"))
    with pytest.raises(ValueError, match="preflight or strategy retry evidence changed"):
        launch(workdir, gate, backend, learning_database=other)
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


def test_changed_real_learning_history_requires_a_fresh_gate_even_with_no_matching_failure(tmp_path, monkeypatch):
    workdir, gate, report, backend = prepare(tmp_path, monkeypatch)
    database = tmp_path / "learning.sqlite3"
    save_event(database, "variant", "test-only-history-change", {"purpose": "test-only history freshness"})
    fresh = submission.preflight(workdir, "diagnostic_static", host=HOST, learning_database=database, write_report=False)
    assert fresh["strategy_retry_check"] == report["strategy_retry_check"]
    assert fresh["learning_database"] != report["learning_database"]
    monkeypatch.setattr(submission, "_run", lambda argv: pytest.fail("network must not run"))
    with pytest.raises(ValueError, match="preflight or strategy retry evidence changed"):
        launch(workdir, gate, backend, learning_database=database)
    assert submission.submission_status(workdir)["status"] == "NOT_RESERVED"


def test_history_change_after_upload_is_checked_in_the_third_verification(tmp_path, monkeypatch):
    workdir, gate, _, backend = prepare(tmp_path, monkeypatch)
    database = tmp_path / "learning.sqlite3"
    submitted = []

    def remote(argv):
        if argv[0] == "scp":
            save_event(database, "variant", "test-only-after-upload", {"purpose": "test-only concurrent history update"})
        if "sbatch --parsable" in argv[-1]:
            submitted.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(submission, "_run", remote)
    with pytest.raises(ValueError, match="preflight or strategy retry evidence changed"):
        launch(workdir, gate, backend, learning_database=database)
    assert submitted == []
    assert submission.submission_status(workdir)["status"] == submission.UNKNOWN


@pytest.mark.parametrize("command", ["preflight", "submit"])
def test_cli_forwards_explicit_learning_database(tmp_path, monkeypatch, command):
    database = tmp_path / "reviewed.sqlite3"
    options = ["--workdir", str(tmp_path / NAME), "--host", HOST, "--learning-database", str(database)]
    if command == "preflight":
        options += ["--kind", "diagnostic_static"]
    else:
        options += ["--decision", str(tmp_path / "gate.json"), "--remote-dir", "/unused-in-mocked-parser-test",
                    "--potcar-source", "/unused-in-mocked-parser-test/POTCAR", "--potcar-sha256", POTCAR_HASH,
                    "--action", ACTION]
    seen = []

    def inspect_arguments(*args, **kwargs):
        seen.append(kwargs["learning_database"])
        return {"passed": True}

    monkeypatch.setattr(sys, "argv", ["submission", command, *options])
    monkeypatch.setattr(submission, command, inspect_arguments)
    submission.main()
    assert seen == [database]
