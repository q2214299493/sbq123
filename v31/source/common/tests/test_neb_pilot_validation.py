from __future__ import annotations

from pathlib import Path

import pytest

from scripts.neb_agent import pilot_validation


def _scheduler() -> dict:
    return {
        "schema_version": 1,
        "document_kind": "scheduler_job_evidence",
        "stage": "neb_pilot",
        "scheduler": "LSF",
        "server_alias": "sunboquan-codex",
        "job_id": "123",
        "status": "DONE",
        "checked_at": "2026-07-23T00:00:00Z",
        "source_command": "ssh sunboquan-codex bjobs -a 123",
        "query": {"argv": ["ssh", "host"], "returncode": 0, "stdout": "123 u DONE", "stderr": "", "stdout_sha256": "a" * 64},
    }


def _calculation(path: Path, outputs: bool) -> None:
    path.mkdir()
    nsw = 1 if outputs else 300
    (path / "INCAR").write_text(
        f"IMAGES=2\nNELM=200\nEDIFF=1e-5\nNSW={nsw}\nMAGMOM=2*2.4\n",
        encoding="ascii",
    )
    (path / "KPOINTS").write_text("Gamma\n", encoding="ascii")
    (path / "POTCAR.spec").write_text("Fe\n", encoding="ascii")
    (path / "script.lsf").write_text("NP=2\n", encoding="ascii")
    (path / "path_generation_report.json").write_text('{"path":"same"}', encoding="ascii")
    for index in range(4):
        image = path / f"{index:02d}"
        image.mkdir()
        (image / "POSCAR").write_text(f"POSCAR {index}", encoding="ascii")
        if outputs and index in (1, 2):
            (image / "CONTCAR").write_text(f"CONTCAR {index}", encoding="ascii")
            (image / "OSZICAR").write_text(
                "DAV: 1 -1.0 -0.1E-06\n 1 F= -1.0 E0= -1.0\n", encoding="ascii"
            )
            (image / "OUTCAR").write_text(
                "aborting loop because EDIFF is reached\n"
                "number of electron 10.0 magnetization 2.0\n"
                "General timing and accounting informations for this job\n",
                encoding="ascii",
            )


def test_pilot_result_is_rebuilt_from_bound_scheduler_and_vasp_files(
    tmp_path: Path, monkeypatch,
) -> None:
    pilot = tmp_path / "pilot"
    production = tmp_path / "production"
    _calculation(pilot, outputs=True)
    _calculation(production, outputs=False)
    monkeypatch.setattr(pilot_validation, "query_lsf_job", lambda *args, **kwargs: _scheduler())
    monkeypatch.setattr(pilot_validation, "verify_lsf_evidence_live", lambda *args, **kwargs: None)
    result = pilot_validation.build_pilot_result(pilot, production, "123")
    assert result["passed"] is True
    pilot_validation.validate_pilot_result(production / "neb_pilot_result.json", production)
    (pilot / "01" / "OUTCAR").write_text("tampered", encoding="ascii")
    with pytest.raises(ValueError, match="does not match"):
        pilot_validation.validate_pilot_result(production / "neb_pilot_result.json", production)


def test_pilot_reports_adjacent_magnetic_warning_without_rejecting(tmp_path: Path, monkeypatch) -> None:
    pilot = tmp_path / "pilot"
    production = tmp_path / "production"
    _calculation(pilot, outputs=True)
    _calculation(production, outputs=False)
    outcar = pilot / "02" / "OUTCAR"
    outcar.write_text(
        outcar.read_text(encoding="ascii").replace("magnetization 2.0", "magnetization 5.0"),
        encoding="ascii",
    )
    monkeypatch.setattr(pilot_validation, "query_lsf_job", lambda *args, **kwargs: _scheduler())
    monkeypatch.setattr(pilot_validation, "verify_lsf_evidence_live", lambda *args, **kwargs: None)
    result = pilot_validation.build_pilot_result(pilot, production, "123")
    assert result["passed"] is True
    assert result["magnetic_continuity"]["severity"] == "SOFT_WARNING"
    assert result["magnetic_continuity"]["warnings"][0]["left"] == "01"
    assert result["magnetic_continuity"]["warnings"][0]["right"] == "02"
    assert result["magnetic_continuity"]["stops_current_job"] is False
    assert result["magnetic_continuity"]["blocks_ordinary_no_climb_neb"] is False
    assert result["magnetic_continuity"]["proves_magnetic_state_switch"] is False
    pilot_validation.validate_pilot_result(production / "neb_pilot_result.json", production)
