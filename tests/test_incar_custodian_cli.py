from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "fe-vasp-incar-custodian" / "scripts" / "incar_custodian.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def write_neb_incar(path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                "GGA = PE",
                "ENCUT = 400",
                "ISPIN = 2",
                "IBRION = 3",
                "POTIM = 0",
                "LCLIMB = .FALSE.",
                "NELM = 200",
                "EDIFF = 1E-5",
                "ISYM = 0",
            )
        )
        + "\n",
        encoding="ascii",
    )


@pytest.mark.parametrize("mode_flag", [(), ("--read-only",), ("--dry-run",)])
def test_parse_errors_read_only_never_writes(
    tmp_path: Path, mode_flag: tuple[str, ...]
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "OUTCAR").write_text("BRMIX: very serious problems\n", encoding="ascii")

    result = run_cli("--mode", "parse-errors", "--workdir", str(run_dir), *mode_flag)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["read_only"] is True
    assert payload["artifacts_written"] == []
    assert not (run_dir / "vasp_error_report.json").exists()


def test_tune_read_only_prints_recommendation_without_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    incar = run_dir / "INCAR"
    write_neb_incar(incar)

    result = run_cli(
        "--mode",
        "tune",
        "--workdir",
        str(run_dir),
        "--incar",
        str(incar),
        "--calculation-type",
        "pre_NEB",
        "--surface-family",
        "metal_fe",
        "--material",
        "Fe110",
        "--failure-type",
        "scf_failure",
        "--read-only",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "INCAR_RECOMMENDED"
    assert payload["read_only"] is True
    assert payload["recommended_incar"] is None
    assert payload["candidate_output"].endswith("INCAR.recommended")
    assert payload["changes"]["NELM"]["new"] == 300
    assert payload["artifacts_written"] == []
    assert sorted(path.name for path in run_dir.iterdir()) == ["INCAR"]


def test_write_artifacts_is_explicit_and_markdown_is_windows_utf8(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    incar = run_dir / "INCAR"
    write_neb_incar(incar)

    result = run_cli(
        "--mode",
        "tune",
        "--workdir",
        str(run_dir),
        "--incar",
        str(incar),
        "--calculation-type",
        "pre_NEB",
        "--surface-family",
        "metal_fe",
        "--material",
        "Fe110",
        "--failure-type",
        "scf_failure",
        "--write-artifacts",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "INCAR_RECOMMENDED"
    expected = {
        "INCAR",
        "INCAR.recommended",
        "incar_change.json",
        "incar_change_report.md",
        "incar_validation.json",
    }
    assert {path.name for path in run_dir.iterdir()} == expected

    payload = json.loads((run_dir / "incar_change.json").read_text(encoding="utf-8"))
    assert payload["read_only"] is False
    assert payload["recommended_incar"].endswith("INCAR.recommended")
    assert len(payload["artifacts_written"]) == 4

    report = run_dir / "incar_change_report.md"
    assert report.read_bytes().startswith(b"\xef\xbb\xbf")
    decoded = report.read_text(encoding="utf-8-sig")
    assert "# INCAR 调参建议" in decoded
    assert "本报告未提交或运行 VASP。" in decoded
