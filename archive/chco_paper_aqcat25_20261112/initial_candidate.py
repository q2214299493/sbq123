"""Hash-bound IDPP/BA-Sella prediction only; never performs DFT or training."""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import signal
import sys
import textwrap
from pathlib import Path

import numpy as np
import torch
from ase.calculators.calculator import Calculator, all_changes
from ase.constraints import FixAtoms
from ase.io import Trajectory, read, write
from ase.mep.neb import NEB, idpp_interpolate
from ase.optimize import LBFGS

import aqcat_ts_pilot as pilot
import mlip_same_structure_benchmark as benchmark
from arkimede.workflow import calculations

FT512 = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fixed(atoms):
    if any(not isinstance(c, FixAtoms) for c in atoms.constraints):
        raise ValueError("only complete FixAtoms selective-dynamics masks are supported")
    return sorted({int(i) for c in atoms.constraints for i in c.get_indices()})


def geometry(atoms, reference, request):
    if not np.isfinite(atoms.positions).all() or not np.isfinite(atoms.cell.array).all():
        raise ValueError("nonfinite geometry")
    if fixed(atoms) != request["fixed_indices_zero_based"]:
        raise ValueError("fixed mask changed")
    if not np.array_equal(atoms.cell.array, reference.cell.array):
        raise ValueError("cell changed")
    if atoms.get_chemical_symbols() != reference.get_chemical_symbols() or not np.array_equal(atoms.pbc, reference.pbc):
        raise ValueError("atom identity/order or periodicity changed")
    displacement = np.linalg.norm(atoms.positions - reference.positions, axis=1)
    fixed_shift = float(displacement[fixed(atoms)].max(initial=0))
    if fixed_shift > 1e-8:
        raise ValueError(f"fixed atoms moved {fixed_shift} A")
    distances = atoms.get_all_distances(mic=True)
    np.fill_diagonal(distances, np.inf)
    minimum = float(distances.min())
    if minimum < request["geometry"]["minimum_pair_distance_A"]:
        raise ValueError(f"collision: minimum pair distance {minimum} A")
    warnings = []
    for bond in request["geometry"]["preserved_bonds"]:
        value = distances[tuple(bond["atoms"])]
        if not bond["minimum_A"] <= value <= bond["maximum_A"]:
            raise ValueError(f"preserved bond {bond['name']} outside bounds: {value} A")
        if not bond["soft_minimum_A"] <= value <= bond["soft_maximum_A"]:
            warnings.append(f"{bond['name']} outside soft interval: {value} A")
    return {"minimum_pair_distance_A": minimum, "fixed_shift_max_A": fixed_shift,
            "warnings": warnings,
            "bonds_A": {name: float(distances[tuple(pair)]) for name, pair in
                        request["reaction"]["monitor_pairs"].items()}}


class GuardedCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def __init__(self, inner, reference, request):
        super().__init__()
        self.inner, self.reference, self.request = inner, reference, request
        self.counter, self.failure = 0, None

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        try:
            geometry(atoms, self.reference, self.request)
            super().calculate(atoms, properties, system_changes)
            energy = float(self.inner.get_potential_energy(atoms))
            forces = np.asarray(self.inner.get_forces(atoms), dtype=float)
            if forces.shape != (len(atoms), 3) or not np.isfinite(energy) or not np.isfinite(forces).all():
                raise ValueError("nonfinite predicted energy or forces")
            self.results = {"energy": energy, "forces": forces}
            self.counter += 1
        except Exception as error:
            self.failure = f"{type(error).__name__}: {error}"
            raise


def execute(request, output, report):
    sources = {Path(ref["path"]).resolve(): ref for ref in request["source_files"]}
    artifact = sys.modules.get("artifact_io") or sys.modules.get("scripts.artifact_io")
    required = [__file__, pilot.__file__, benchmark.__file__, artifact.__file__, calculations.__file__]
    if not all(Path(path).resolve() in sources for path in required):
        raise ValueError("source manifest omits an actually loaded implementation")
    for ref in [*sources.values(), request["initial"], request["final"], request["checkpoint"]]:
        if digest(ref["path"]) != ref["sha256"]:
            raise ValueError(f"source/input hash mismatch: {ref['path']}")
    if request["checkpoint"]["sha256"] != FT512:
        raise ValueError("this first-round request requires the frozen FT512 checkpoint")
    tree = ast.parse(textwrap.dedent(inspect.getsource(calculations.run_sella_calculation)))
    if not any(isinstance(node, ast.Dict) and any(
            isinstance(key, ast.Constant) and key.value == "nsteps_per_diag" and
            isinstance(value, ast.Constant) and value.value == 1
            for key, value in zip(node.keys, node.values)) for node in ast.walk(tree)):
        raise ValueError("author's BA-Sella default nsteps_per_diag=1 was not verified")
    initial, final = (read(request[key]["path"], format="vasp") for key in ("initial", "final"))
    report["endpoint_validation"] = pilot.validate_endpoint_pair(initial, final)
    reaction = request["reaction"]
    indices = [*reaction["adsorbate_indices"], *(i for b in reaction["bonds"] for i in b[:2])]
    indices += [i for pair in reaction["monitor_pairs"].values() for i in pair]
    indices += [i for bond in request["geometry"]["preserved_bonds"] for i in bond["atoms"]]
    if any(type(i) is not int or not 0 <= i < len(initial) for i in indices):
        raise ValueError("reaction/geometry atom indices must be valid zero-based integers")
    pilot.validate_reaction_metadata(initial, reaction["bonds"], reaction["adsorbate_indices"])
    if any(len(bond) != 3 or bond[0] == bond[1] or bond[2] not in {"form", "break"}
           for bond in reaction["bonds"]):
        raise ValueError("invalid indexed bond change")
    report["source_endpoint_geometry"] = [geometry(atoms, initial, request) for atoms in (initial, final)]
    images = [initial.copy() for _ in range(9)] + [final.copy()]
    for atoms in images:
        pilot.add_model_context(atoms, reaction["bonds"], reaction["adsorbate_indices"], False, False)
    neb = NEB(images, method="improvedtangent")
    neb.interpolate(method="linear", mic=True, apply_constraint=True)

    class RecordedLBFGS(LBFGS):
        def run(self, fmax=0.01, steps=1000):
            converged = super().run(fmax=fmax, steps=steps)
            report["idpp"] = {"converged": bool(converged), "steps": self.nsteps,
                              "total_images": 10, "optimizer": "LBFGS", "fmax": 0.01,
                              "max_steps": 1000, "mic": True, "all_atoms": True}
            return converged

    idpp_interpolate(neb, optimizer=RecordedLBFGS, fmax=0.01, steps=1000, mic=True,
                     traj=str(output / "idpp_optimizer.traj"), log=str(output / "idpp.log"))
    report["idpp_geometry"] = [geometry(atoms, initial, request) for atoms in images]
    with Trajectory(str(output / "idpp_path.traj"), "w") as trajectory:
        for atoms in images:
            trajectory.write(atoms)
    if not report["idpp"]["converged"]:
        raise RuntimeError("IDPP optimizer budget exhausted")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("exactly one available CUDA device is required; no CPU fallback")
    report["cuda"] = {"available": True, "device_count": 1, "build": torch.version.cuda}
    inner = benchmark._load_calculator("aqcat25", Path(request["checkpoint"]["path"]), "cuda")
    devices = {str(parameter.device) for parameter in inner.trainer.model.parameters()}
    if not devices or any(not device.startswith("cuda:") for device in devices):
        raise RuntimeError(f"model parameters are not entirely on CUDA: {devices}")
    report["model_devices"] = sorted(devices)
    calculator = GuardedCalculator(inner, initial, request)
    guess, index, energies = pilot.select_ts_guess(images, calculator)
    report.update(selected_internal_image=index, predicted_image_energies_eV=energies)
    report["ba_sella"] = {"fmax": 0.01, "min_steps": 10, "max_steps": 1000,
                         "eta": 0.01, "gamma": 0.05, "delta0": 0.05,
                         "dot_prod_thr": 0.5, "nsteps_per_diag": 1}
    candidate = pilot.run_ba_sella(guess, calculator, output, 0.01, 1000, 10)
    report.update(optimizer_status=candidate.info.get("status"), calculator_failure=calculator.failure)
    report["candidate_geometry"] = geometry(candidate, initial, request)
    forces = candidate.get_forces()
    report["predicted_movable_fmax_eV_per_A"] = float(np.linalg.norm(forces, axis=1).max())
    write(output / "predicted_candidate.vasp", candidate, format="vasp", direct=True, sort=False)
    report["optimizer_converged"] = (candidate.info.get("status") == "finished" and
                                     report["predicted_movable_fmax_eV_per_A"] <= 0.01)
    if calculator.failure or not report["optimizer_converged"]:
        raise RuntimeError(calculator.failure or "BA-Sella unfinished: step/force-call budget or optimizer failure")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if digest(args.request) != args.request_sha256:
        raise ValueError("request bytes changed")
    request = json.loads(args.request.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"result_class": "predicted_candidate_only", "scientifically_accepted": False,
              "DFT_performed": False, "training_performed": False, "status": "failed",
              "request_sha256": args.request_sha256,
              "fixed_indices_zero_based": request["fixed_indices_zero_based"]}

    def interrupted(signum, _frame):
        raise TimeoutError(f"interrupted by signal {signum}; no automatic retry")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        execute(request, args.output, report)
        report["status"] = "prediction_completed_pending_review"
    except Exception as error:
        report["failure"] = f"{type(error).__name__}: {error}"
    with (args.output / "candidate_report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return 0 if report["status"] == "prediction_completed_pending_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
