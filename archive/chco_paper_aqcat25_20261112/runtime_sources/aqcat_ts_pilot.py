#!/usr/bin/env python3
"""Safe AQCat25 + BA-Sella transition-state pilot.

This script never submits VASP jobs.  It provides three explicit stages:
preflight, calculator, and ts.  Atom indices accepted on the command line are
one-based so that they match POSCAR-style counting used during manual review.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import Trajectory, read, write


def parse_bond(value: str) -> list[object]:
    """Parse ACTION:I:J and convert one-based atom indices to zero-based."""
    parts = value.split(":")
    if len(parts) != 3 or parts[0] not in {"form", "break"}:
        raise argparse.ArgumentTypeError("bond must be form:I:J or break:I:J")
    try:
        i, j = int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bond atom indices must be integers") from exc
    if i < 1 or j < 1 or i == j:
        raise argparse.ArgumentTypeError("bond indices must be distinct positive integers")
    return [i - 1, j - 1, parts[0]]


def parse_indices(value: str) -> list[int]:
    if not value.strip():
        return []
    try:
        result = [int(item) - 1 for item in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("indices must be comma-separated integers") from exc
    if any(index < 0 for index in result):
        raise argparse.ArgumentTypeError("indices must be one-based positive integers")
    return result


def fixed_indices(atoms: Atoms) -> list[int]:
    result: set[int] = set()
    for constraint in atoms.constraints:
        if isinstance(constraint, FixAtoms):
            result.update(int(index) for index in constraint.get_indices())
    return sorted(result)


def validate_endpoint_pair(atoms_is: Atoms, atoms_fs: Atoms) -> dict[str, object]:
    errors: list[str] = []
    if len(atoms_is) != len(atoms_fs):
        errors.append(f"atom count differs: IS={len(atoms_is)}, FS={len(atoms_fs)}")
    if atoms_is.get_chemical_symbols() != atoms_fs.get_chemical_symbols():
        errors.append("chemical symbols or atom ordering differ")
    if not np.allclose(atoms_is.cell.array, atoms_fs.cell.array, atol=1e-6, rtol=0.0):
        errors.append("cell vectors differ")
    if not np.array_equal(atoms_is.pbc, atoms_fs.pbc):
        errors.append("periodic boundary conditions differ")
    fixed_is = fixed_indices(atoms_is)
    fixed_fs = fixed_indices(atoms_fs)
    if fixed_is != fixed_fs:
        errors.append("fixed atom indices differ")
    if errors:
        raise ValueError("endpoint preflight failed:\n- " + "\n- ".join(errors))
    return {
        "natoms": len(atoms_is),
        "symbols": atoms_is.get_chemical_symbols(),
        "fixed_indices_1based": [index + 1 for index in fixed_is],
        "cell": atoms_is.cell.array.tolist(),
        "pbc": atoms_is.pbc.tolist(),
    }


def validate_reaction_metadata(
    atoms: Atoms,
    bonds: list[list[object]],
    adsorbate_indices: list[int],
) -> None:
    if not bonds:
        raise ValueError("at least one --bond form:I:J or break:I:J is required")
    natoms = len(atoms)
    referenced = {int(index) for bond in bonds for index in bond[:2]}
    if any(index >= natoms for index in referenced):
        raise ValueError(f"bond index exceeds atom count ({natoms})")
    if any(index >= natoms for index in adsorbate_indices):
        raise ValueError(f"adsorbate index exceeds atom count ({natoms})")
    fixed = set(fixed_indices(atoms))
    if referenced and referenced.issubset(fixed):
        raise ValueError("all atoms in the specified reaction bonds are fixed")


def add_model_context(
    atoms: Atoms,
    bonds: list[list[object]],
    adsorbate_indices: list[int],
    is_spin_off: bool,
    is_low_fi: bool,
) -> None:
    atoms.info["is_spin_off"] = is_spin_off
    atoms.info["is_low_fi"] = is_low_fi
    atoms.info["bonds_TS"] = bonds
    atoms.info["indices_ads"] = adsorbate_indices


def build_aqcat_calculator(checkpoint: Path, is_spin_off: bool, is_low_fi: bool):
    from fairchem.core.common.relaxation.ase_utils import patched_calc

    return patched_calc(
        checkpoint_path=str(checkpoint),
        is_spin_off=is_spin_off,
        is_low_fi=is_low_fi,
    )


def calculator_smoke_test(atoms: Atoms, calculator) -> dict[str, float]:
    probe = atoms.copy()
    probe.calc = calculator
    energy = float(probe.get_potential_energy())
    forces = np.asarray(probe.get_forces(), dtype=float)
    if not np.isfinite(energy) or not np.all(np.isfinite(forces)):
        raise RuntimeError("AQCat25 returned non-finite energy or forces")
    return {
        "energy_ev": energy,
        "fmax_ev_per_angstrom": float(np.linalg.norm(forces, axis=1).max()),
    }


def build_idpp_path(states: list[Atoms], n_images_per_segment: int) -> list[Atoms]:
    try:
        from ase.mep.neb import NEB, idpp_interpolate
    except ImportError:
        from ase.neb import NEB, idpp_interpolate

    if n_images_per_segment < 3:
        raise ValueError("--n-images-per-segment must be at least 3")
    images: list[Atoms] = []
    for segment, (state_a, state_b) in enumerate(zip(states[:-1], states[1:])):
        segment_images = [state_a.copy()]
        segment_images.extend(state_a.copy() for _ in range(n_images_per_segment - 2))
        segment_images.append(state_b.copy())
        neb = NEB(images=segment_images, method="improvedtangent")
        # The surface includes fixed atoms.  Explicitly applying constraints is
        # required by current ASE and prevents the frozen substrate from moving.
        neb.interpolate(method="linear", mic=True, apply_constraint=True)
        idpp_interpolate(
            images=segment_images,
            fmax=0.05,
            mic=True,
            steps=200,
        )
        if segment:
            segment_images = segment_images[1:]
        images.extend(segment_images)
    return images


def select_ts_guess(images: list[Atoms], calculator) -> tuple[Atoms, int, list[float]]:
    energies: list[float] = []
    for image in images:
        image.calc = calculator
        energies.append(float(image.get_potential_energy()))
    if len(images) < 3:
        raise ValueError("the path has no internal image")
    index = int(np.argmax(energies[1:-1])) + 1
    guess = images[index].copy()
    from arkimede.workflow.transition_states import get_mode_TS_from_images

    guess.info["mode_TS"] = get_mode_TS_from_images(images=images, index_TS=index)
    return guess, index, energies


def run_ba_sella(
    guess: Atoms,
    calculator,
    output_dir: Path,
    fmax: float,
    max_steps: int,
    min_steps: int,
) -> Atoms:
    from arkimede.workflow.calculations import run_sella_calculation

    candidate = guess.copy()
    run_sella_calculation(
        atoms=candidate,
        calc=calculator,
        fmax=fmax,
        max_steps=max_steps,
        min_steps=min_steps,
        max_forcecalls=max(2 * max_steps, max_steps + 50),
        label="aqcat25_ba_sella",
        directory=str(output_dir),
        save_trajs=True,
        copy_atoms=False,
        bonds_TS=candidate.info["bonds_TS"],
        modify_hessian=True,
        dot_prod_thr=0.50,
        opt_kwargs={"eta": 0.01, "gamma": 0.05, "delta0": 0.05},
    )
    return candidate


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["preflight", "calculator", "ts"], default="preflight")
    parser.add_argument("--is", dest="initial", type=Path, required=True, help="IS POSCAR")
    parser.add_argument("--fs", dest="final", type=Path, required=True, help="FS POSCAR")
    parser.add_argument("--waypoint", action="append", type=Path, default=[])
    parser.add_argument("--checkpoint", type=Path, help="AQCat25 model.pt")
    parser.add_argument("--bond", action="append", type=parse_bond, default=[])
    parser.add_argument("--adsorbate-indices", type=parse_indices, default=[])
    parser.add_argument("--is-spin-off", action="store_true")
    parser.add_argument("--is-low-fi", action="store_true")
    parser.add_argument("--n-images-per-segment", type=int, default=10)
    parser.add_argument("--fmax-ml", type=float, default=0.01)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--min-steps", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("aqcat_ts_work"))
    return parser


def main() -> int:
    args = make_parser().parse_args()
    paths = [args.initial, *args.waypoint, args.final]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing structure files: " + ", ".join(missing))

    states = [read(path, format="vasp") for path in paths]
    endpoint_report = validate_endpoint_pair(states[0], states[-1])
    for waypoint in states[1:-1]:
        validate_endpoint_pair(states[0], waypoint)
    validate_reaction_metadata(states[0], args.bond, args.adsorbate_indices)
    for atoms in states:
        add_model_context(
            atoms,
            bonds=args.bond,
            adsorbate_indices=args.adsorbate_indices,
            is_spin_off=args.is_spin_off,
            is_low_fi=args.is_low_fi,
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "stage": args.stage,
        "endpoint_preflight": endpoint_report,
        "bonds_1based": [[int(i) + 1, int(j) + 1, action] for i, j, action in args.bond],
        "adsorbate_indices_1based": [index + 1 for index in args.adsorbate_indices],
        "submitted_vasp": False,
    }

    if args.stage in {"calculator", "ts"}:
        if args.checkpoint is None or not args.checkpoint.is_file():
            raise FileNotFoundError("--checkpoint must point to the AQCat25 model.pt")
        calculator = build_aqcat_calculator(
            args.checkpoint,
            is_spin_off=args.is_spin_off,
            is_low_fi=args.is_low_fi,
        )
        report["calculator"] = calculator_smoke_test(states[0], calculator)

    if args.stage == "ts":
        images = build_idpp_path(states, args.n_images_per_segment)
        for image in images:
            add_model_context(
                image,
                bonds=args.bond,
                adsorbate_indices=args.adsorbate_indices,
                is_spin_off=args.is_spin_off,
                is_low_fi=args.is_low_fi,
            )
        trajectory = Trajectory(str(args.output_dir / "idpp_path.traj"), mode="w")
        for image in images:
            trajectory.write(image)
        trajectory.close()
        guess, index, energies = select_ts_guess(images, calculator)
        add_model_context(
            guess,
            bonds=args.bond,
            adsorbate_indices=args.adsorbate_indices,
            is_spin_off=args.is_spin_off,
            is_low_fi=args.is_low_fi,
        )
        write(args.output_dir / "TS_GUESS.vasp", guess, format="vasp", direct=True, vasp5=True)
        candidate = run_ba_sella(
            guess,
            calculator,
            output_dir=args.output_dir,
            fmax=args.fmax_ml,
            max_steps=args.max_steps,
            min_steps=args.min_steps,
        )
        write(args.output_dir / "TS_CANDIDATE.vasp", candidate, format="vasp", direct=True, vasp5=True)
        candidate.calc = calculator
        candidate_energy = float(candidate.get_potential_energy())
        forces = np.asarray(candidate.get_forces(), dtype=float)
        optimizer_trajectory = args.output_dir / "aqcat25_ba_sella.traj"
        optimizer_steps = max(len(Trajectory(str(optimizer_trajectory), mode="r")) - 1, 0)
        report.update({
            "idpp_images": len(images),
            "ts_guess_image_zero_based": index,
            "path_energies_ev": energies,
            "candidate_status": candidate.info.get("status", "unknown"),
            "candidate_energy_ml_eV": candidate_energy,
            "candidate_fmax_ml_ev_per_angstrom": float(np.linalg.norm(forces, axis=1).max()),
            "optimizer_steps": optimizer_steps,
            "scientifically_validated_ts": False,
        })

    report_path = args.output_dir / "pilot_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
