"""Use the existing ASE/AQCat25 relaxation kernel for four bound cases."""

from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import socket
import sys
import time

import numpy as np
from ase.optimize import LBFGS

from runtime import digest, load_atoms, relax_case, save

LIMITS = {"seed_max_steps": 80, "fmax_eV_per_A": 0.1, "LBFGS_maxstep_A": 0.20}


def run(expected, output):
    import torch
    from fairchem.core.common.relaxation import ase_utils

    root = Path(__file__).resolve().parent
    request = root / "request.json"
    if digest(request) != expected:
        raise ValueError("Optimization authorization bytes changed")
    doc = json.loads(request.read_bytes())
    assert doc["action"] == "PAIRWISE_AQCAT25_RELAXATION_ONLY" and doc["canonical_root"] == str(root)
    assert doc["host"] == socket.gethostname() == "MZ73"
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == "-1" and os.environ.get("SLURM_CPUS_PER_TASK") == "8"
    assert os.environ.get("SLURM_JOB_PARTITION") == "cpu" and not os.environ.get("SLURM_JOB_GPUS")
    job = os.environ["SLURM_JOB_ID"]
    assert job.isdecimal() and output.resolve() == (root / ("job_" + job)).resolve()
    assert doc["limit"] == LIMITS and LBFGS.defaults["maxstep"] == LIMITS["LBFGS_maxstep_A"]
    assert set(doc["models"]) == {"545", "580"} and set(doc["starts"]) == {"11_B", "05_cfg2"}
    assert doc["training"] is doc["new_DFT"] is doc["model_promotion"] is False
    for name, checksum in doc["files"].items():
        path = (root / name).resolve()
        assert path.is_relative_to(root) and digest(path) == checksum
    assert digest(Path(sys.executable)) == doc["python_sha256"]
    assert digest(Path(ase_utils.__file__)) == doc["native_calc_sha256"]
    torch.set_num_threads(8)
    torch.manual_seed(42)
    started = time.monotonic()
    deadline = started + 530
    arms = {}
    for model, model_file in doc["models"].items():
        target = output / model
        target.mkdir()
        path = root / model_file
        assert digest(path) == doc["files"][model_file]
        calc = ase_utils.patched_calc(checkpoint_path=str(path), is_spin_off=False, is_low_fi=False, cpu=True)
        native = calc.trainer.model
        parameter = next(native.parameters())
        assert parameter.device.type == "cpu" and parameter.dtype == torch.float32 and not torch.cuda.is_initialized()
        native.eval()
        results = []
        for name, row in doc["starts"].items():
            start = {"name": name, "seed_path": row["path"]}
            atoms = load_atoms(root / row["path"])
            assert atoms[45:].get_chemical_formula() == row["composition"]
            atoms.calc = calc
            check_times = time.monotonic()
            forces = np.asarray(atoms.get_forces(apply_constraint=False))
            assert forces.shape == (len(atoms), 3) and np.isfinite(forces).all()
            print(
                model,
                name,
                "initial fmax",
                np.linalg.norm(forces[18:], axis=1).max(),
                "seconds",
                time.monotonic() - check_times,
                flush=True,
            )
            result = relax_case(root, target, start, "seed", calc, LIMITS, deadline)
            results.append(result)
            print(model, name, result["status"], result["optimizer_steps"], result.get("ML_movable_fmax_eV_A"), flush=True)
        assert digest(path) == doc["files"][model_file]
        arms[model] = results
        del atoms, calc, native, parameter
        gc.collect()
    paths = [p for p in output.rglob("*") if p.is_file() and p.name in ("case_record.json", "POSCAR", "optimizer.log", "optimization.traj")]
    save(
        output / "result.json",
        {
            "job_id": job,
            "request_sha256": expected,
            "results": arms,
            "device": "CPU FP32",
            "torch": str(torch.__version__),
            "produced_files": {p.relative_to(output).as_posix(): digest(p) for p in paths},
            "elapsed_seconds": time.monotonic() - started,
            "cuda_initialized": torch.cuda.is_initialized(),
        },
    )


if __name__ == "__main__":
    run(sys.argv[1], Path(sys.argv[2]))
