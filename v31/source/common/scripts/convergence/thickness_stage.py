"""Thickness payload input/result checks and atomic structure handoff; no executor.

Uses the existing VASP and POSCAR owners. Requires only the core package (NumPy),
not ASE, pymatgen, Sella or an environment-specific scientific toolchain.
"""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np

from scripts.convergence.common import extract_toten
from scripts.neb_agent.utils_structure import read_poscar
from scripts.neb_agent.utils_vasp import parse_outcar
from scripts.scientific_validation import finite_array, finite_number, integer_number
from scripts.vasp_result_gate import read_incar_values

ATTEMPT = ".thickness-attempt"
PRIOR_ATTEMPTS = {ATTEMPT, "submission_attempt.json", "submission_record.json", "submitted.jobid"}
OUTPUTS = {"OUTCAR", "CONTCAR", "OSZICAR", "vasprun.xml", "vasp.out", "WAVECAR",
           "CHG", "CHGCAR", "DOSCAR", "EIGENVAL", "IBZKPT", "PCDAT", "XDATCAR", "REPORT"}


def contained(root: Path, path: Path) -> Path:
    """Reject symlinks, including dangling links, before any read or write."""
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"path escapes selected workdir: {path}")
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError(f"symlink not permitted in thickness workdir: {part}")
        if part == root:
            break
    return path


def pristine(root: Path, directories: list[Path], *, attempt: bool = True, machinefile: bool = False) -> None:
    for directory in directories:
        contained(root, directory)
        if directory.exists() and not directory.is_dir():
            raise ValueError(f"not a stage directory: {directory}")
        for path in directory.iterdir() if directory.exists() else ():
            contained(root, path)
            if path.name in OUTPUTS | (set() if machinefile else {"nodelist"}) | (PRIOR_ATTEMPTS if attempt else set()):
                raise ValueError(f"existing execution evidence; use a new workdir or reviewed recovery: {path}")


def structure(path: Path):
    try:
        result = read_poscar(path)
        finite_array(result.cell.tolist(), "cell", shape=(3, 3))
        finite_array(result.frac.tolist(), "coordinates", shape=(result.atom_count, 3))
        finite_number(abs(np.linalg.det(result.cell)), "cell volume", positive=True)
        if (not result.counts or len(result.symbols) != len(result.counts)
                or any(n <= 0 for n in result.counts) or set(result.symbols) != {"Fe"}):
            raise ValueError("expected positive Fe atom counts")
        if result.selective and any(len(row) != 3 or set(row) - {"T", "F"} for row in result.flags):
            raise ValueError("invalid Selective Dynamics flags")
        return result
    except (IndexError, OSError, TypeError, np.linalg.LinAlgError) as exc:
        raise ValueError(f"invalid thickness structure: {path}") from exc


def inputs(root: Path, directory: Path, stage: str, *, machinefile: bool = False) -> None:
    pristine(root, [directory], attempt=False, machinefile=machinefile)
    for name in ["INCAR", "POSCAR", "KPOINTS", "POTCAR"]:
        path = contained(root, directory / name)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing/non-file stage input: {path}")
    structure(directory / "POSCAR")
    incar = read_incar_values(directory / "INCAR")
    nsw, ibrion = (integer_number(incar.get(key), key) for key in ["NSW", "IBRION"])
    if (stage == "static" and (nsw != 0 or ibrion != -1)) or (stage == "relax" and nsw <= 0):
        raise ValueError("stage does not match INCAR calculation type")


def result_status(directory: Path, stage: str) -> dict:
    """Current file evidence only; no scheduler or scientific acceptance claim."""
    parsed = parse_outcar(directory / "OUTCAR")
    complete = (parsed.get("normal_completion") and parsed.get("final_target_complete")
                and parsed.get("final_target_explicit_convergence") and not parsed.get("fatal_keywords"))
    if stage == "relax":
        complete = complete and parsed.get("reached_required_accuracy")
    return {"output_status": "COMPLETE" if complete else "INCOMPLETE_OR_FAILED",
            "scientific_acceptance": False}


def validate_result(root: Path, directory: Path, stage: str) -> None:
    contained(root, directory / "OUTCAR")
    if result_status(directory, stage)["output_status"] != "COMPLETE":
        raise ValueError(f"{stage}: current OUTCAR lacks applicable completion/convergence or has fatal evidence")
    if extract_toten(directory / "OUTCAR") is None:
        raise ValueError(f"{stage}: current TOTEN missing")


def handoff(root: Path) -> None:
    source = contained(root, root / "relax/CONTCAR")
    target = contained(root, root / "static/POSCAR")
    validate_result(root, root / "relax", "relax")
    inputs(root, root / "static", "static")
    current, initial = structure(source), structure(root / "relax/POSCAR")
    if (current.labels != initial.labels or current.selective != initial.selective
            or current.flags != initial.flags or not np.allclose(current.cell, initial.cell)):
        raise ValueError("CONTCAR identity/cell/Selective Dynamics mismatch")
    data = source.read_bytes()
    descriptor, name = tempfile.mkstemp(prefix=".POSCAR-handoff-", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        contained(root, target)
        os.replace(temporary, target)
        if target.read_bytes() != data:
            raise ValueError("structure handoff byte verification failed")
    finally:
        temporary.unlink(missing_ok=True)  # Only this function's unpublished temporary file.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["preflight", "inputs", "result", "handoff"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--kind", choices=["chain", "static"], default="chain")
    parser.add_argument("--stage", choices=["relax", "static"], default="static")
    args = parser.parse_args()
    root = args.root.absolute()
    directory = root / args.stage if args.kind == "chain" else root
    try:
        contained(root, root)
        if args.operation == "preflight":
            stages = [(root / "relax", "relax"), (root / "static", "static")] if args.kind == "chain" else [(root, "static")]
            pristine(root, [root], attempt=False)
            for path, stage in stages:
                inputs(root, path, stage)
        elif args.operation == "inputs":
            # nodelist is owned by this attempt at the standalone root.
            inputs(root, directory, args.stage, machinefile=args.kind == "static")
        elif args.operation == "result":
            validate_result(root, directory, args.stage)
        else:
            handoff(root)
    except (OSError, ValueError) as exc:
        parser.exit(65, f"THICKNESS_STAGE_REJECTED: {exc}\n")


if __name__ == "__main__":
    main()
