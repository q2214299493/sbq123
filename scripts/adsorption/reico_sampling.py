"""Bounded random-environment sampling; predictions are not DFT labels."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import write
from ase.optimize import LBFGS

KIND = "adsorption_bounded_random_sampling"


def validate_sampling_scope(request, authorization, request_sha, exception):
    if (authorization.get("request_sha256") != request_sha
            or authorization.get("user_authorized") is not True
            or authorization.get("action") != "RUN_GPU_REICO_BOUNDED_SAMPLING"
            or authorization.get("user_request") != exception["authorizing_user_request"]):
        raise ValueError("missing or stale sampling authorization")
    for key in ("gpu_index", "gpu_uuid", "remote_root", "max_wall_seconds", "limits"):
        if request[key] != exception[key]:
            raise ValueError("sampling scope changed: " + key)
    if (request["execution_mode"] != "direct_no_scheduler" or request["scheduler_job_id"] is not None
            or set(request["models"]) != {"candidate"}
            or request["models"]["candidate"]["sha256"] != exception["candidate_checkpoint_sha256"]):
        raise ValueError("sampling model or execution mode changed")
    rows = request["samples"]
    if (len(rows) != exception["sample_count"]
            or len({r["sample_id"] for r in rows}) != exception["sample_count"]
            or sorted({r["source_name"] for r in rows}) != exception["source_names"]
            or request["source_manifest_sha256"] != exception["source_manifest_sha256"]
            or request["generation_config_sha256"] != exception["generation_config_sha256"]
            or request["geometry_cases"]
            or request["sample_role"] != "screened_untrained_diagnostic_not_independent_heldout"):
        raise ValueError("sampling source membership or role changed")


def geometry_audit(atoms, initial, pair_minimum, limits):
    reasons = []
    if not np.isfinite(atoms.positions).all() or not np.isfinite(atoms.cell).all():
        return {"failures": ["NONFINITE_GEOMETRY"]}
    fixed = sorted(int(i) for c in atoms.constraints for i in c.get_indices())
    if (atoms.get_chemical_symbols() != initial.get_chemical_symbols()
            or fixed != list(range(18)) or not np.array_equal(atoms.pbc, initial.pbc)
            or not np.array_equal(atoms.cell, initial.cell)
            or not np.array_equal(atoms.positions[:18], initial.positions[:18])):
        reasons.append("ORDER_CELL_OR_FIXED_LAYER_CHANGED")
    distances = atoms.get_all_distances(mic=True)
    np.fill_diagonal(distances, np.inf)
    fe_min = float(distances[:45, :45].min())
    if fe_min < limits["minimum_Fe_Fe_A"]:
        reasons.append("SHORT_Fe_Fe_CONTACT")
    minima = {}
    for i in range(45, len(atoms)):
        for j in range(i):
            pair = "-".join(sorted((atoms[i].symbol, atoms[j].symbol)))
            if pair not in pair_minimum:
                raise ValueError("missing pair guard: " + pair)
            value = float(distances[i, j])
            minima[pair] = min(minima.get(pair, np.inf), value)
            if value < pair_minimum[pair] - 1e-10:
                reasons.append("SHORT_CONTACT:" + pair)
    top = float(atoms.positions[:45, 2].max())
    height = float((atoms.positions[45:, 2] - top).min())
    if height < limits["minimum_adsorbate_height_A"]:
        reasons.append("SURFACE_PENETRATION_GUARD")
    z = np.sort(atoms.positions[:, 2] % atoms.cell[2, 2])
    vacuum = float(np.diff(np.r_[z, z[0] + atoms.cell[2, 2]]).max())
    if vacuum < limits["minimum_periodic_vacuum_gap_A"]:
        reasons.append("PERIODIC_VACUUM_GUARD")
    _, movement = find_mic(atoms.positions[45:] - initial.positions[45:], atoms.cell, [True, True, False])
    return {"failures": sorted(set(reasons)), "pair_minima_A": minima,
            "Fe_Fe_minimum_A": fe_min, "minimum_height_above_top_Fe_A": height,
            "periodic_vacuum_gap_A": vacuum, "adsorbate_RMSD_from_seed_A": float(np.sqrt(np.mean(movement**2)))}


class SamplingGuardError(ValueError):
    pass


def sample_case(atoms, directory: Path, limits: dict, pair_minimum: dict, deadline: float):
    """Persist every callback, including a rejected boundary, with restart state."""
    if __package__:
        from archive.fe110_adsorption_validation_20261018.runtime import digest, save
    else:
        from runtime import digest, save
    directory.mkdir(parents=True, exist_ok=False)
    initial = atoms.copy()
    frames = []
    previous = atoms.positions.copy()
    optimizer = LBFGS(atoms, maxstep=limits["maxstep_A"],
                      restart=str(directory / "lbfgs_restart.json"),
                      logfile=str(directory / "optimizer.log"), trajectory=str(directory / "optimization.traj"))

    def observe():
        nonlocal previous
        if time.monotonic() > deadline:
            raise TimeoutError("sampling walltime exhausted")
        step = int(optimizer.nsteps)
        audit = geometry_audit(atoms, initial, pair_minimum, limits)
        largest = float(np.linalg.norm(atoms.positions - previous, axis=1).max())
        if largest > limits["maxstep_A"] + 1e-8:
            audit["failures"].append("STEP_DISPLACEMENT_LIMIT")
        forces = np.asarray(atoms.get_forces(apply_constraint=False))
        finite = forces.shape == (len(atoms), 3) and np.isfinite(forces).all()
        if not finite:
            audit["failures"].append("INVALID_MODEL_FORCES")
        poscar = directory / f"step_{step:03d}.vasp"
        if poscar.exists():
            raise FileExistsError("refusing to overwrite sampled frame")
        write(poscar, atoms, format="vasp", direct=True, sort=False, vasp5=True)
        row = {"step": step, "structure_path": poscar.name, "structure_sha256": digest(poscar),
               "geometry_audit": audit, "max_step_displacement_A": largest,
               "forces_eV_per_A": forces.tolist() if finite else None,
               "ML_movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()) if finite else None,
               "ML_adsorbate_fmax_eV_A": float(np.linalg.norm(forces[45:], axis=1).max()) if finite else None,
               "scientific_acceptance": False}
        save(directory / f"step_{step:03d}.json", row)
        frames.append(row)
        previous = atoms.positions.copy()
        if audit["failures"]:
            raise SamplingGuardError(",".join(audit["failures"]))

    optimizer.attach(observe, interval=1)
    error, converged, fatal = None, False, False
    started = time.monotonic()
    try:
        converged = bool(optimizer.run(fmax=limits["ML_fmax_eV_A"], steps=limits["max_steps"]))
    except (SamplingGuardError, np.linalg.LinAlgError) as exc:
        error = type(exc).__name__ + ": " + str(exc)
    except Exception as exc:
        error, fatal = type(exc).__name__ + ": " + str(exc), True
        raise
    finally:
        record = {"frames": frames, "optimizer_steps": int(optimizer.nsteps),
                  "ML_optimizer_converged": converged, "error": error,
                  "status": "RUNTIME_ERROR_PRESERVED" if fatal else "GUARD_STOP_PRESERVED" if error else "ML_TARGET_REACHED" if converged else "STEP_LIMIT_REACHED",
                  "elapsed_seconds": time.monotonic() - started, "scientific_acceptance": False}
        save(directory / "case_record.json", record)
        optimizer.close()
    return record


def run_sampling(root: Path, request: dict, calculator, deadline: float):
    if __package__:
        from archive.fe110_adsorption_validation_20261018.runtime import digest, load_atoms, local_path
    else:
        from runtime import digest, load_atoms, local_path
    config_path = local_path(root, request["generation_config_path"])
    if digest(config_path) != request["generation_config_sha256"]:
        raise ValueError("generation geometry guards changed")
    guards = json.loads(config_path.read_bytes())["pair_minimum_A"]
    cases = []
    for source in request["samples"]:
        atoms = load_atoms(local_path(root, source["structure_path"]))
        atoms.calc = calculator
        record = sample_case(atoms, root / "output" / "sampling" / source["sample_id"],
                             request["limits"], guards, deadline)
        cases.append({"sample_id": source["sample_id"], "composition": source["composition"],
                      "partition": "train", "source_structure_sha256": source["structure_sha256"], **record})
        print("sampling " + source["sample_id"] + " " + record["status"], flush=True)
    return {"cases": cases, "checkpoint_sha256": request["models"]["candidate"]["sha256"],
            "frames_are_ML_predictions_not_DFT_labels": True, "training_performed": False}
