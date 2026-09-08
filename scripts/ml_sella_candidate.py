"""Optional, fixed-cell Sella refinement of an ML-NEB peak; predictions only."""
from __future__ import annotations

import math
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any, Callable

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms
from ase.calculators.calculator import Calculator, all_changes

try:
    from scripts.artifact_io import sha256_file, write_json_atomic
    from scripts.aqcat25_ml_neb import _fixed_indices, _write_vasp_atomic
except ModuleNotFoundError:  # Standalone MZ73 deployment.
    from artifact_io import sha256_file, write_json_atomic
    from aqcat25_ml_neb import _fixed_indices, _write_vasp_atomic


def validate_settings(settings: dict[str, Any]) -> None:
    required = {"fmax_eV_per_A", "max_steps", "delta0_A"}
    if not isinstance(settings, dict) or set(settings) != required:
        raise ValueError(f"Sella settings require exactly {sorted(required)}")
    for name in ("fmax_eV_per_A", "delta0_A"):
        value = settings[name]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Sella {name} must be finite and positive")
    if type(settings["max_steps"]) is not int or settings["max_steps"] < 1:
        raise ValueError("Sella max_steps must be a positive integer")


def require_sella():
    try:
        from sella import Sella
    except ImportError as exc:
        raise RuntimeError("optional Sella dependency is unavailable; NEB inputs were not run") from exc
    return Sella


class SellaBudgetExhausted(RuntimeError):
    """A bounded search ended before another model evaluation was accepted."""


class BudgetCalculator(Calculator):
    """Bound force evaluations; also check finite-difference trial geometries.

    Wall time is cooperative: an in-flight model call needs a process/scheduler
    timeout to interrupt it. Count attempted energy/force pairs, including failures.
    """
    implemented_properties = ["energy", "forces"]

    def __init__(self, calculator, maximum_evaluations, maximum_wall_seconds, *, geometry_check=None):
        super().__init__()
        self.calculator = calculator
        self.maximum_evaluations = maximum_evaluations
        self.maximum_wall_seconds = maximum_wall_seconds
        self.geometry_check = geometry_check
        self.evaluations = 0
        self.started = time.monotonic()

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        if self.evaluations >= self.maximum_evaluations or time.monotonic() - self.started >= self.maximum_wall_seconds:
            raise SellaBudgetExhausted("Sella evaluation/time budget exhausted")
        if self.geometry_check is not None and self.geometry_check(atoms).get("passed") is not True:
            raise ValueError("Sella trial failed geometry guards before model evaluation")
        super().calculate(atoms, properties, system_changes)
        self.evaluations += 1
        energy = self.calculator.get_potential_energy(atoms)
        forces = np.asarray(self.calculator.get_forces(atoms), dtype=float)
        if not math.isfinite(float(energy)) or forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
            raise ValueError("nonfinite or malformed Sella energy/forces")
        if time.monotonic() - self.started >= self.maximum_wall_seconds:
            raise SellaBudgetExhausted("Sella evaluation/time budget exhausted after model evaluation")
        self.results = {"energy": energy, "forces": forces}


def refine_peak(
    seed: Atoms,
    calculator: Any,
    settings: dict[str, Any],
    output: Path,
    *,
    source: dict[str, Any],
    geometry_check: Callable[[Atoms], dict[str, Any]],
) -> dict[str, Any]:
    """Preserve the parent path and last valid iterate, including on branch failure."""
    validate_settings(settings)
    optimizer_class = require_sella()
    if any(not isinstance(item, FixAtoms) for item in seed.constraints):
        raise ValueError("Sella branch currently supports full-atom Selective Dynamics only")
    if len(_fixed_indices(seed)) == len(seed):
        raise ValueError("Sella needs at least one movable atom")
    output.mkdir(parents=True, exist_ok=False)
    atoms = seed.copy()
    atoms.calc = calculator
    fixed = _fixed_indices(seed)
    record = {
        "schema_version": 1,
        "document_kind": "ml_sella_candidate_manifest",
        "method": "sella",  # Standard Sella is not Bond-Aware Sella.
        "source": source,
        "settings": settings,
        "sella_version": version("sella"),
        "runner_sha256": sha256_file(Path(__file__)),
        "status": "running",
        "result_class": "predicted_transition_state_candidate_only",
        "snapshots": [],
        "automatic_submission": False,
        "scientifically_validated_ts": False,
        "model_error_assumed": False,
    }
    manifest_path = output / "candidate_manifest.json"
    last_positions = None

    def save_valid() -> None:
        nonlocal last_positions
        if not np.isfinite(atoms.positions).all():
            raise ValueError("nonfinite Sella positions")
        if (not np.array_equal(atoms.numbers, seed.numbers)
                or not np.array_equal(atoms.pbc, seed.pbc)
                or not np.allclose(atoms.cell, seed.cell, rtol=0, atol=1e-10)
                or not np.allclose(atoms.positions[fixed], seed.positions[fixed], rtol=0, atol=1e-8)):
            raise ValueError("Sella changed atom order, fixed atoms, cell, or PBC")
        geometry = geometry_check(atoms)
        if geometry.get("passed") is not True:
            record["failed_geometry"] = geometry
            raise ValueError("Sella candidate failed the parent path geometry gates")
        energy = float(atoms.get_potential_energy())
        forces = np.asarray(atoms.get_forces(), dtype=float)
        if not math.isfinite(energy) or forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
            raise ValueError("nonfinite or malformed Sella energy/forces")
        forces = forces.copy()
        forces[fixed] = 0.0
        if last_positions is not None and np.array_equal(last_positions, atoms.positions):
            return
        # Sella translates ASE constraints internally. Restore the reviewed mask in exports.
        exported = atoms.copy()
        exported.set_constraint(seed.constraints)
        filename = f"step_{len(record['snapshots']):04d}.vasp"
        _write_vasp_atomic(output / filename, exported)
        row = {"path": filename, "sha256": sha256_file(output / filename),
               "energy_eV": energy, "fmax_eV_per_A": float(np.linalg.norm(forces, axis=1).max()),
               "geometry_passed": True}
        record["snapshots"].append(row)
        record["last_valid_structure"] = row
        last_positions = atoms.positions.copy()
        write_json_atomic(manifest_path, record)

    try:
        save_valid()
        with optimizer_class(atoms, order=1, internal=False, delta0=settings["delta0_A"],
                             trajectory=str(output / "sella.traj"), logfile=str(output / "sella.log")) as optimizer:
            optimizer.attach(save_valid, interval=1)
            converged = bool(optimizer.run(fmax=settings["fmax_eV_per_A"], steps=settings["max_steps"]))
            save_valid()
            record["optimizer_steps"] = int(optimizer.nsteps)
        record["optimizer_converged"] = converged
        record["status"] = "needs_work_review" if converged else "optimizer_not_converged"
    except SellaBudgetExhausted as exc:
        record["status"] = "budget_exhausted"
        record["optimizer_converged"] = False
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
    write_json_atomic(manifest_path, record)
    return record
