from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.artifact_io import sha256_file
from scripts.neb_agent import submission
from scripts.registry_schema import migrate_registry
from scripts.neb_agent.utils_structure import Poscar, write_poscar
from scripts.ts_strategy_engine.dimer_gate import DEFAULT_POLICY


def preflight(workdir: Path, kind: str) -> dict:
    database = workdir / "test_learning.sqlite3"
    migrate_registry(database)
    return submission.preflight(workdir, kind, learning_database=database)


def _common(path: Path, incar: str, cores: int) -> None:
    (path / "INCAR").write_text(incar, encoding="ascii")
    (path / "KPOINTS").write_text("KPOINTS", encoding="ascii")
    (path / "POTCAR.spec").write_text("Fe C O", encoding="ascii")
    (path / "script.lsf").write_text(f"NP={cores}\n", encoding="ascii")


def test_neb_preflight_rejects_nondivisible_mpi_ranks(tmp_path: Path) -> None:
    _common(tmp_path, "IMAGES=5\nLCLIMB=.FALSE.\n", 32)
    for name in (
        "path_generation_report.json",
        "path_geometry_diagnosis.json",
        "path_review.json",
        "dist.dat",
        "movie.xyz",
    ):
        (tmp_path / name).write_text(name, encoding="ascii")
    for index in range(7):
        image = tmp_path / f"{index:02d}"
        image.mkdir()
        (image / "POSCAR").write_text("POSCAR", encoding="ascii")
    report = preflight(tmp_path, "ordinary_neb")
    assert report["passed"] is False
    assert "mpi_ranks_not_divisible_by_IMAGES" in report["errors"]


@pytest.mark.parametrize(
    ("cores", "passed"),
    ((126, False), (108, True)),
)
def test_neb_preflight_requires_per_image_ranks_divisible_by_npar(
    tmp_path: Path, cores: int, passed: bool
) -> None:
    _common(
        tmp_path,
        "IMAGES=9\nLCLIMB=.FALSE.\nNSW=1\nNPAR=4\n",
        cores,
    )
    for name in (
        "path_generation_report.json",
        "path_geometry_diagnosis.json",
        "path_review.json",
        "dist.dat",
        "movie.xyz",
    ):
        (tmp_path / name).write_text(name, encoding="ascii")
    for index in range(11):
        image = tmp_path / f"{index:02d}"
        image.mkdir()
        (image / "POSCAR").write_text("POSCAR", encoding="ascii")

    report = preflight(tmp_path, "neb_pilot")

    assert report["passed"] is passed
    assert (
        "mpi_ranks_per_image_not_divisible_by_NPAR" in report["errors"]
    ) is not passed


def test_neb_pilot_uses_the_same_structural_preflight(tmp_path: Path) -> None:
    _common(tmp_path, "IMAGES=2\nLCLIMB=.FALSE.\nNSW=1\n", 32)
    for name in (
        "path_generation_report.json",
        "path_geometry_diagnosis.json",
        "path_review.json",
        "dist.dat",
        "movie.xyz",
    ):
        (tmp_path / name).write_text(name, encoding="ascii")
    for index in range(4):
        image = tmp_path / f"{index:02d}"
        image.mkdir()
        (image / "POSCAR").write_text("POSCAR", encoding="ascii")
    assert preflight(tmp_path, "neb_pilot")["passed"] is True


def test_production_neb_allows_missing_optional_pilot(tmp_path: Path) -> None:
    _common(tmp_path, "IMAGES=2\nLCLIMB=.FALSE.\nNSW=300\n", 32)
    for name in (
        "path_generation_report.json",
        "path_geometry_diagnosis.json",
        "path_review.json",
        "dist.dat",
        "movie.xyz",
    ):
        (tmp_path / name).write_text(name, encoding="ascii")
    for index in range(4):
        image = tmp_path / f"{index:02d}"
        image.mkdir()
        (image / "POSCAR").write_text("POSCAR", encoding="ascii")
    report = preflight(tmp_path, "ordinary_neb")
    assert report["passed"] is True
    assert "neb_pilot_result.json" not in report["files"]


def test_production_neb_rejects_invalid_supplied_optional_pilot(tmp_path: Path) -> None:
    _common(tmp_path, "IMAGES=2\nLCLIMB=.FALSE.\nNSW=300\n", 32)
    for name in (
        "path_generation_report.json",
        "path_geometry_diagnosis.json",
        "path_review.json",
        "dist.dat",
        "movie.xyz",
    ):
        (tmp_path / name).write_text(name, encoding="ascii")
    for index in range(4):
        image = tmp_path / f"{index:02d}"
        image.mkdir()
        (image / "POSCAR").write_text("POSCAR", encoding="ascii")
    (tmp_path / "neb_pilot_result.json").write_text("{}", encoding="ascii")

    report = preflight(tmp_path, "ordinary_neb")

    assert report["passed"] is False
    assert any(
        error.startswith("ordinary_neb_pilot_validation_failed:")
        for error in report["errors"]
    )


def test_static_diagnostic_preflight(tmp_path: Path) -> None:
    _common(tmp_path, "NSW=0\nIBRION=-1\n", 32)
    (tmp_path / "POSCAR").write_text("POSCAR", encoding="ascii")
    report = preflight(tmp_path, "diagnostic_static")
    assert report["passed"] is True


def test_ci_neb_preflight_requires_climb(tmp_path: Path) -> None:
    _common(tmp_path, "IMAGES=2\nLCLIMB=.FALSE.\n", 32)
    for name in (
        "path_generation_report.json",
        "path_geometry_diagnosis.json",
        "path_review.json",
        "dist.dat",
        "movie.xyz",
    ):
        (tmp_path / name).write_text(name, encoding="ascii")
    for index in range(4):
        image = tmp_path / f"{index:02d}"
        image.mkdir()
        (image / "POSCAR").write_text("POSCAR", encoding="ascii")
    report = preflight(tmp_path, "ci_neb")
    assert report["passed"] is False
    assert "ci_neb_requires_LCLIMB_true" in report["errors"]


def test_dimer_preflight_requires_modecar_and_dimer_incar(tmp_path: Path) -> None:
    _common(tmp_path, "ICHAIN=2\nNSW=200\n", 32)
    structure = Poscar(
        comment="Fe C O",
        cell=np.eye(3) * 10.0,
        symbols=["Fe", "C", "O"],
        counts=[1, 1, 1],
        frac=np.array([[0.0, 0.0, 0.0], [0.2, 0.0, 0.2], [0.4, 0.0, 0.2]]),
        selective=True,
        flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
    )
    for name in ("POSCAR", "PREVIOUS_POSCAR", "NEXT_POSCAR"):
        write_poscar(tmp_path / name, structure)
    (tmp_path / "MODECAR").write_text("0 0 0\n0.707106781187 0 0\n-0.707106781187 0 0\n", encoding="ascii")
    (tmp_path / "dimer_handoff.json").write_text(
        (
            '{"source_sha256":"'
            + sha256_file(tmp_path / "POSCAR")
            + '","previous_sha256":"'
            + sha256_file(tmp_path / "PREVIOUS_POSCAR")
            + '","next_sha256":"'
            + sha256_file(tmp_path / "NEXT_POSCAR")
            + '","modecar_sha256":"'
            + sha256_file(tmp_path / "MODECAR")
            + '","dimer_gate_policy_sha256":"'
            + sha256_file(DEFAULT_POLICY)
            + '","candidate_hard_gate":{"hard_gate_passed":true,"hard_gate_errors":[]},'
            + '"recommended_gate":{"strict_local_energy_maximum":false}}'
        ),
        encoding="ascii",
    )
    (tmp_path / "mode_review.json").write_text(
        '{"status":"accepted","reviewer":"test","reviewed_at":"2026-01-01",'
        '"reaction_atom_indices_zero_based":[1,2],'
        '"reaction_center_continuity":"accepted","periodic_mapping":"accepted",'
        '"adsorption_site_continuity":"accepted","reaction_mechanism_continuity":"accepted",'
        '"mode_assignment":"accepted","target_reaction_event":"C-O dissociation",'
        '"modecar_sha256":"'
        + sha256_file(tmp_path / "MODECAR")
        + '"}',
        encoding="ascii",
    )
    report = preflight(tmp_path, "dimer")
    assert report["passed"] is True
    assert report["dimer_hard_gate_passed"] is True


def test_vfa_preflight_requires_bound_scope_review(tmp_path: Path) -> None:
    _common(tmp_path, "IBRION=5\nNSW=1\nNFREE=2\nPOTIM=0.015\n", 32)
    structure = Poscar(
        comment="Fe C O",
        cell=np.eye(3) * 10.0,
        symbols=["Fe", "C", "O"],
        counts=[1, 1, 1],
        frac=np.array([[0.0, 0.0, 0.0], [0.2, 0.0, 0.2], [0.4, 0.0, 0.2]]),
        selective=True,
        flags=[("F", "F", "F"), ("T", "T", "T"), ("T", "T", "T")],
    )
    write_poscar(tmp_path / "POSCAR", structure)
    handoff = tmp_path / "vfa_handoff.json"
    handoff.write_text(
        '{"frequency_poscar_sha256":"'
        + sha256_file(tmp_path / "POSCAR")
        + '","active_atom_indices_zero_based":[1,2],'
        '"reaction_atom_indices_zero_based":[1,2],'
        '"frequency_method":"finite_difference_partial_hessian",'
        '"active_set_policy":"contract_defined_local",'
        '"active_indices_source":"explicit_reaction_contract_review",'
        '"full_hessian_required":false}',
        encoding="ascii",
    )
    scope = tmp_path / "vfa_scope_review.json"
    scope.write_text(
        '{"status":"accepted_for_partial_hessian","reviewer":"user",'
        '"reviewed_at":"2026-08-05T00:00:00Z",'
        '"active_atom_indices_zero_based":[1,2],'
        '"frequency_method":"finite_difference_partial_hessian",'
        '"active_set_policy":"contract_defined_local",'
        '"active_indices_source":"explicit_reaction_contract_review",'
        '"frequency_poscar_sha256":"'
        + sha256_file(tmp_path / "POSCAR")
        + '","vfa_handoff_sha256":"'
        + sha256_file(handoff)
        + '"}',
        encoding="ascii",
    )
    report = preflight(tmp_path, "vfa")
    assert report["passed"] is True
    assert report["vfa_hard_gate_passed"] is True

    mismatched_scope = scope.read_text(encoding="ascii").replace(
        "explicit_reaction_contract_review", "unbound_manual_indices"
    )
    scope.write_text(mismatched_scope, encoding="ascii")
    assert preflight(tmp_path, "vfa")["passed"] is False
    scope.write_text(
        mismatched_scope.replace(
            "unbound_manual_indices", "explicit_reaction_contract_review"
        ),
        encoding="ascii",
    )

    legacy_handoff = json.loads(handoff.read_text(encoding="ascii"))
    legacy_scope = json.loads(scope.read_text(encoding="ascii"))
    for field in (
        "frequency_method",
        "active_set_policy",
        "active_indices_source",
        "full_hessian_required",
    ):
        legacy_handoff.pop(field, None)
        legacy_scope.pop(field, None)
    legacy_scope["status"] = "accepted_for_diagnostic_frequency"
    handoff.write_text(json.dumps(legacy_handoff), encoding="ascii")
    legacy_scope["vfa_handoff_sha256"] = sha256_file(handoff)
    scope.write_text(json.dumps(legacy_scope), encoding="ascii")
    assert preflight(tmp_path, "vfa")["passed"] is True

    review = scope.read_text(encoding="ascii").replace(
        "accepted_for_diagnostic_frequency", "needs_review"
    )
    scope.write_text(review, encoding="ascii")
    blocked = preflight(tmp_path, "vfa")
    assert blocked["passed"] is False
    assert "vfa_hard_gate:scope_review_accepted" in blocked["errors"]


def test_upload_stages_only_manifest_files(tmp_path: Path, monkeypatch) -> None:
    workdir = tmp_path / "calculation"
    workdir.mkdir()
    (workdir / "INCAR").write_text("required", encoding="ascii")
    (workdir / "unrequested.md").write_text("exclude", encoding="ascii")
    uploaded: list[str] = []

    def inspect_upload(argv: list[str]):
        staged = Path(argv[2])
        uploaded.extend(
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*")
            if path.is_file()
        )

    monkeypatch.setattr(submission, "_run", inspect_upload)
    submission._upload_manifest_files("host", "~/sbq", workdir, {"INCAR": "hash"})
    assert uploaded == ["INCAR"]


def test_stop_job_accepts_gate_bound_pending_job(tmp_path: Path, monkeypatch) -> None:
    decision = {
        "state_sha256": "state",
        "EVIDENCE": {"scheduler": {"job_id": "123", "status": "PEND"}},
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_require(path: Path, action: str, state: str):
        assert path == decision_path
        assert action == "STOP_JOB"
        assert state == "state"

    def fake_load(path: Path):
        assert path == decision_path
        return decision

    def fake_run(argv: list[str]):
        calls.append(argv)
        if "bjobs" in argv:
            return type(
                "Result",
                (),
                {
                    "stdout": (
                        "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
                        "123 user PEND queue host - neb Jul 27 00:00\n"
                    )
                },
            )()
        return type("Result", (), {"stdout": "Job <123> is being terminated"})()

    monkeypatch.setattr(submission, "require_action", fake_require)
    monkeypatch.setattr(submission, "load_json_object", fake_load)
    monkeypatch.setattr(submission, "_run", fake_run)
    record = submission.stop_job(
        decision_path, "sunboquan-codex", "123", tmp_path / "stop.json"
    )
    assert record["prior_status"] == "PEND"
    assert calls[-1] == ["ssh", "sunboquan-codex", "bkill", "123"]


def _mock_submit_dependencies(
    tmp_path: Path,
    monkeypatch,
) -> tuple[Path, Path, dict[str, object]]:
    workdir = tmp_path / "job"
    workdir.mkdir()
    decision_path = tmp_path / "decision.json"
    decision_path.write_text("{}", encoding="utf-8")
    report: dict[str, object] = {
        "kind": "diagnostic_static",
        "passed": True,
        "bundle_sha256": "bundle",
        "files": {},
    }
    decision = {
        "state_sha256": "state",
        "EVIDENCE": {"preflight": {"bundle_sha256": "bundle"}},
    }

    def fake_load(path: Path):
        return report if path.name == "submission_preflight.json" else decision

    monkeypatch.setattr(submission, "load_json_object", fake_load)
    monkeypatch.setattr(submission, "preflight", lambda *args: report)
    monkeypatch.setattr(submission, "require_action", lambda *args: decision)
    monkeypatch.setattr(submission, "_upload_manifest_files", lambda *args: None)
    return workdir, decision_path, report


def test_submit_failure_leaves_unresolved_marker_and_no_success_record(
    tmp_path: Path, monkeypatch
) -> None:
    workdir, decision_path, _ = _mock_submit_dependencies(tmp_path, monkeypatch)
    calls = 0

    def fake_run(argv: list[str]):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("command failed (1): bsub rejected")
        return type("Result", (), {"stdout": ""})()

    monkeypatch.setattr(submission, "_run", fake_run)
    with pytest.raises(RuntimeError, match="bsub rejected"):
        submission.submit(
            workdir,
            decision_path,
            "sunboquan-codex",
            "~/sbq/job",
            "~/sbq/POTCAR",
            "a" * 64,
            "SUBMIT_DIAGNOSTIC_VASP",
        )

    assert (workdir / submission.SUBMISSION_ATTEMPT_FILE).is_file()
    assert not (workdir / submission.SUBMISSION_RECORD_FILE).exists()


def test_unresolved_or_completed_submission_cannot_be_repeated(
    tmp_path: Path, monkeypatch
) -> None:
    workdir, decision_path, _ = _mock_submit_dependencies(tmp_path, monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(submission, "_run", lambda argv: calls.append(argv))

    attempt = workdir / submission.SUBMISSION_ATTEMPT_FILE
    attempt.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="retry refused") as error:
        submission.submit(
            workdir,
            decision_path,
            "sunboquan-codex",
            "~/sbq/job",
            "~/sbq/POTCAR",
            "a" * 64,
            "SUBMIT_DIAGNOSTIC_VASP",
        )
    assert str(attempt) in str(error.value)
    assert "SUBMISSION_RECOVERY.md" in str(error.value)
    attempt.unlink()

    (workdir / submission.SUBMISSION_RECORD_FILE).write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already has a submission record"):
        submission.submit(
            workdir,
            decision_path,
            "sunboquan-codex",
            "~/sbq/job",
            "~/sbq/POTCAR",
            "a" * 64,
            "SUBMIT_DIAGNOSTIC_VASP",
        )
    assert calls == []


def test_successful_submit_replaces_attempt_with_success_record(
    tmp_path: Path, monkeypatch
) -> None:
    workdir, decision_path, _ = _mock_submit_dependencies(tmp_path, monkeypatch)
    calls = 0

    def fake_run(argv: list[str]):
        nonlocal calls
        calls += 1
        stdout = "Job <123> is submitted" if calls == 2 else ""
        return type("Result", (), {"stdout": stdout})()

    monkeypatch.setattr(submission, "_run", fake_run)
    result = submission.submit(
        workdir,
        decision_path,
        "sunboquan-codex",
        "~/sbq/job",
        "~/sbq/POTCAR",
        "a" * 64,
        "SUBMIT_DIAGNOSTIC_VASP",
    )

    assert result["job_id"] == "123"
    assert not (workdir / submission.SUBMISSION_ATTEMPT_FILE).exists()
    assert (workdir / submission.SUBMISSION_RECORD_FILE).is_file()
