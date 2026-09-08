#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from common import (
    EXTERNAL_COMMAND_TIMEOUT_SECONDS,
    last_matching_float,
)


WORKDIR = Path("~/sbq/agent/jobs/convergence/alpha_fe_bulk_smearing_20260623").expanduser()
SOURCE = Path("~/sbq/agent/jobs/convergence/fe_bulk_fe110_slab_20260618/alpha_fe_bulk/reference").expanduser()
LSF = Path("~/vasp541std.lsf").expanduser()
SUBMISSION_ATTEMPT_FILE = "submission_attempt.json"
SUBMISSION_RECORD_FILE = "submitted.jobid"
CASES = [
    ("ISMEAR_m5_TETRA", -5, 0.05),
    ("ISMEAR_0_SIGMA_0p05", 0, 0.05),
    ("ISMEAR_0_SIGMA_0p10", 0, 0.10),
    ("ISMEAR_0_SIGMA_0p20", 0, 0.20),
    ("ISMEAR_1_SIGMA_0p10", 1, 0.10),
    ("ISMEAR_1_SIGMA_0p20", 1, 0.20),
    ("ISMEAR_1_SIGMA_0p30", 1, 0.30),
    ("ISMEAR_2_SIGMA_0p20", 2, 0.20),
]


def write_incar(path: Path, ismear: int, sigma: float) -> None:
    path.write_text(
        "SYSTEM = alpha_Fe_bulk_smearing_convergence\n"
        "PREC = Accurate\n"
        "ENCUT = 400\n"
        "EDIFF = 1E-6\n"
        "NELM = 250\n"
        "NELMIN = 5\n"
        "NSW = 0\n"
        "IBRION = -1\n"
        "ISIF = 2\n"
        "GGA = PE\n"
        "ISPIN = 2\n"
        "MAGMOM = 2*2.2\n"
        f"ISMEAR = {ismear}\n"
        f"SIGMA = {sigma:.2f}\n"
        "ALGO = Fast\n"
        "LREAL = .FALSE.\n"
        "LASPH = .TRUE.\n"
        "ADDGRID = .TRUE.\n"
        "NPAR = 2\n"
        "LCHARG = .FALSE.\n"
        "LWAVE = .FALSE.\n",
        encoding="ascii",
    )


def write_kpoints(path: Path) -> None:
    path.write_text(
        "alpha-Fe bulk Gamma 15x15x15\n0\nGamma\n15 15 15\n0 0 0\n",
        encoding="ascii",
    )


def setup() -> None:
    required = [SOURCE / "POSCAR", SOURCE / "POTCAR", LSF]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required files: " + ", ".join(missing))

    WORKDIR.mkdir(parents=True, exist_ok=True)
    for label, ismear, sigma in CASES:
        job_dir = WORKDIR / label
        job_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "POSCAR", job_dir / "POSCAR")
        shutil.copy2(SOURCE / "POTCAR", job_dir / "POTCAR")
        shutil.copy2(LSF, job_dir / "run.lsf")
        write_incar(job_dir / "INCAR", ismear, sigma)
        write_kpoints(job_dir / "KPOINTS")

    (WORKDIR / "README.md").write_text(
        "# alpha-Fe bulk smearing convergence\n\n"
        "Fixed inputs: conventional bcc 2-Fe cell, ENCUT=400 eV, "
        "Gamma 15x15x15, ISPIN=2, MAGMOM=2*2.2.\n"
        "Only ISMEAR and SIGMA vary. ISMEAR=-5 is the dense-mesh static reference.\n",
        encoding="ascii",
    )
    print(f"Set up {len(CASES)} jobs in {WORKDIR}")


def check() -> None:
    errors: list[str] = []
    for label, expected_ismear, expected_sigma in CASES:
        job_dir = WORKDIR / label
        for name in ("POSCAR", "POTCAR", "INCAR", "KPOINTS", "run.lsf"):
            if not (job_dir / name).exists():
                errors.append(f"{label}: missing {name}")
        if not (job_dir / "INCAR").exists():
            continue
        incar = (job_dir / "INCAR").read_text(errors="ignore")
        if f"ISMEAR = {expected_ismear}" not in incar:
            errors.append(f"{label}: incorrect ISMEAR")
        if f"SIGMA = {expected_sigma:.2f}" not in incar:
            errors.append(f"{label}: incorrect SIGMA")
        kpoints = (job_dir / "KPOINTS").read_text(errors="ignore")
        if "15 15 15" not in kpoints:
            errors.append(f"{label}: incorrect k mesh")
        poscar = (job_dir / "POSCAR").read_text(errors="ignore").splitlines()
        if len(poscar) < 7 or poscar[5].split() != ["Fe"] or poscar[6].split() != ["2"]:
            errors.append(f"{label}: unexpected POSCAR species/count")
    if errors:
        raise RuntimeError("Input audit failed:\n" + "\n".join(errors))
    print(f"Input audit passed for {len(CASES)} jobs")


def submit() -> None:
    missing = [
        str(WORKDIR / label / "run.lsf")
        for label, _, _ in CASES
        if not (WORKDIR / label / "run.lsf").is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Submission refused because required run.lsf files are missing: "
            + ", ".join(missing)
        )

    for label, _, _ in CASES:
        job_dir = WORKDIR / label
        marker = job_dir / SUBMISSION_RECORD_FILE
        attempt = job_dir / SUBMISSION_ATTEMPT_FILE
        if marker.exists():
            print(f"{label}: already submitted as {marker.read_text().splitlines()[0]}")
            continue
        if attempt.exists():
            raise RuntimeError(
                "submission retry refused because a previous bsub outcome is "
                f"unresolved; inspect {attempt} and follow SUBMISSION_RECOVERY.md"
            )
        _write_json_atomic(
            attempt,
            {
                "status": "SUBMISSION_OUTCOME_UNRESOLVED",
                "case": label,
                "command": ["bsub", "run.lsf"],
                "working_directory": str(job_dir),
            },
        )
        try:
            proc = subprocess.run(
                ["bsub", "run.lsf"],
                cwd=job_dir,
                text=True,
                capture_output=True,
                check=False,
                timeout=EXTERNAL_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Submission outcome is unresolved because bsub timed out after "
                f"{EXTERNAL_COMMAND_TIMEOUT_SECONDS} seconds for {label}; "
                f"inspect {attempt} and follow SUBMISSION_RECOVERY.md"
            ) from exc
        output = (proc.stdout + proc.stderr).strip()
        match = re.search(r"Job <(\d+)>", output)
        if proc.returncode != 0 or not match:
            raise RuntimeError(
                f"Submission outcome is unresolved for {label}: {output}; "
                f"inspect {attempt} and follow SUBMISSION_RECOVERY.md"
            )
        _write_text_atomic(marker, match.group(1) + "\n" + output + "\n")
        attempt.unlink()
        print(f"{label}: {match.group(1)}")


def _write_text_atomic(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    _write_text_atomic(path, json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def summary() -> None:
    rows: list[dict[str, object]] = []
    tetra_energy = None
    patterns = {
        "toten": re.compile(r"free\s+energy\s+TOTEN\s+=\s+([-0-9.]+)"),
        "sigma0": re.compile(r"energy\(sigma->0\)\s+=\s+([-0-9.]+)"),
        "entropy": re.compile(r"entropy T\*S\s+EENTRO\s+=\s+([-0-9.]+)"),
        "mag": re.compile(r"mag=\s*([-0-9.]+)"),
    }
    for label, ismear, sigma in CASES:
        job_dir = WORKDIR / label
        outcar = job_dir / "OUTCAR"
        oszicar = job_dir / "OSZICAR"
        row: dict[str, object] = {
            "case": label,
            "ismear": ismear,
            "sigma_eV": sigma,
            "finished": bool(outcar.exists() and "General timing and accounting" in outcar.read_text(errors="ignore")),
            "toten_eV": last_matching_float(outcar, patterns["toten"]),
            "sigma0_eV": last_matching_float(outcar, patterns["sigma0"]),
            "entropy_eV": last_matching_float(outcar, patterns["entropy"]),
            "mag_cell_uB": last_matching_float(oszicar, patterns["mag"]),
        }
        if ismear == -5:
            tetra_energy = row["toten_eV"]
        rows.append(row)

    for row in rows:
        energy = row["sigma0_eV"] if row["ismear"] != -5 else row["toten_eV"]
        if energy is not None and tetra_energy is not None:
            row["delta_vs_tetra_meV_atom"] = abs((float(energy) - float(tetra_energy)) / 2 * 1000)
        else:
            row["delta_vs_tetra_meV_atom"] = None
        entropy = row["entropy_eV"]
        row["abs_entropy_meV_atom"] = abs(float(entropy)) / 2 * 1000 if entropy is not None else None

    out = WORKDIR / "alpha_fe_bulk_smearing_summary.csv"
    fields = [
        "case",
        "ismear",
        "sigma_eV",
        "finished",
        "toten_eV",
        "sigma0_eV",
        "delta_vs_tetra_meV_atom",
        "entropy_eV",
        "abs_entropy_meV_atom",
        "mag_cell_uB",
    ]
    with out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(out)
    for row in rows:
        print(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.setup:
        setup()
    if args.check:
        check()
    if args.submit:
        submit()
    if args.summary:
        summary()


if __name__ == "__main__":
    main()
