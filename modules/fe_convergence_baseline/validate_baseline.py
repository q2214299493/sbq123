#!/usr/bin/env python3
"""Validate the retained alpha-Fe convergence baseline."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FORBIDDEN_NAMES = {
    "POTCAR",
    "OUTCAR",
    "OSZICAR",
    "WAVECAR",
    "CHGCAR",
    "CONTCAR",
    "vasprun.xml",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_poscar(path: Path) -> dict:
    lines = [line.strip() for line in path.read_text(encoding="ascii").splitlines() if line.strip()]
    species = lines[5].split()
    counts = [int(value) for value in lines[6].split()]
    index = 7
    selective = lines[index].lower().startswith("s")
    if selective:
        index += 1
    coordinate_mode = lines[index].lower()
    return {
        "species": species,
        "counts": counts,
        "selective": selective,
        "coordinate_mode": coordinate_mode,
    }


def read_incar(path: Path) -> dict[str, str]:
    values = {}
    for raw_line in path.read_text(encoding="ascii").splitlines():
        line = raw_line.split("#", 1)[0].split("!", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().upper()] = value.strip()
    return values


def read_mesh(path: Path) -> tuple[int, int, int]:
    lines = [line.strip() for line in path.read_text(encoding="ascii").splitlines() if line.strip()]
    return tuple(int(value) for value in lines[3].split()[:3])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_incar(path: Path, expected: dict[str, str]) -> None:
    values = read_incar(path)
    for key, expected_value in expected.items():
        require(values.get(key, "").upper() == expected_value.upper(), f"{path}: expected {key}={expected_value}")


def find_csv_row(path: Path, **matches: str) -> dict[str, str]:
    with path.open(newline="", encoding="ascii") as handle:
        for row in csv.DictReader(handle):
            if all(row.get(key) == value for key, value in matches.items()):
                return row
    raise AssertionError(f"{path}: row not found for {matches}")


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="ascii"))

    systems = manifest["systems"]
    require(set(systems) == {"alpha_fe_bulk"}, "only the alpha-Fe bulk baseline should remain in this module")

    alpha_path = ROOT / systems["alpha_fe_bulk"]["poscar"]
    alpha = read_poscar(alpha_path)
    require(alpha["species"] == ["Fe"] and alpha["counts"] == [2], "alpha-Fe must contain exactly 2 Fe atoms")
    require(not alpha["selective"], "alpha-Fe reference should not use Selective Dynamics")
    require(sha256(alpha_path) == systems["alpha_fe_bulk"]["poscar_sha256"], "alpha-Fe POSCAR hash mismatch")

    alpha_dir = ROOT / "systems" / "alpha_fe_bulk"
    require(read_mesh(alpha_dir / "KPOINTS") == (15, 15, 15), "alpha-Fe KPOINTS mismatch")
    require(read_mesh(alpha_dir / "KPOINTS.encut_sweep") == (21, 21, 21), "alpha-Fe ENCUT-sweep KPOINTS mismatch")

    require_incar(alpha_dir / "INCAR.convergence", {"ENCUT": "400", "EDIFF": "1E-6", "ISMEAR": "1", "SIGMA": "0.20", "NSW": "0"})
    require_incar(alpha_dir / "INCAR.relax", {"ENCUT": "400", "EDIFF": "1E-5", "ISMEAR": "1", "SIGMA": "0.10", "ISIF": "3", "IBRION": "2"})
    require_incar(alpha_dir / "INCAR.static", {"ENCUT": "400", "EDIFF": "1E-6", "ISMEAR": "-5", "NSW": "0"})

    evidence = ROOT / "evidence"
    required_evidence = {
        "alpha_fe_bulk_encut.csv",
        "alpha_fe_bulk_kmesh.csv",
        "alpha_fe_bulk_smearing.csv",
        "selection_summary.csv",
    }
    require(required_evidence <= {path.name for path in evidence.glob("*.csv")}, "one or more alpha-Fe evidence CSV files are missing")
    require(
        not any(path.name.startswith("fe110_") for path in evidence.glob("*.csv")), "old Fe110-labeled surface evidence should not remain"
    )

    alpha_encut = find_csv_row(evidence / "alpha_fe_bulk_encut.csv", encut="400")
    alpha_kmesh = find_csv_row(evidence / "alpha_fe_bulk_kmesh.csv", mesh="15x15x15")
    require(float(alpha_encut["delta_mev_atom"]) <= 1.0, "alpha-Fe ENCUT baseline exceeds threshold")
    require(float(alpha_kmesh["delta_mev_atom"]) <= 1.0, "alpha-Fe k-mesh baseline exceeds threshold")

    forbidden = [path for path in ROOT.rglob("*") if path.is_file() and path.name in FORBIDDEN_NAMES]
    require(not forbidden, f"forbidden repository files found: {forbidden}")

    print("PASS: alpha-Fe convergence baseline is internally consistent")
    print("  alpha-Fe: 2 atoms, ENCUT 400 eV, Gamma 15x15x15")
    print("  old Fe110-labeled surface branch: removed")
    print("  POTCAR and large VASP runtime files: absent")


if __name__ == "__main__":
    main()
