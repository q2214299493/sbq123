"""Bounded, one-structure MatRIS/Sella runtime validation; no TS acceptance."""
from __future__ import annotations

import argparse
import os
import socket
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np
from ase.io import read

try:
    from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
    from scripts.aqcat25_ml_neb import _minimum_pair_distance
    from scripts.mlip_same_structure_benchmark import _load_calculator
    from scripts.ml_sella_candidate import BudgetCalculator as BudgetCalculator, refine_peak, require_sella, validate_settings
except ModuleNotFoundError:
    from artifact_io import load_json_object, sha256_file, write_json_atomic
    from aqcat25_ml_neb import _minimum_pair_distance
    from mlip_same_structure_benchmark import _load_calculator
    from ml_sella_candidate import BudgetCalculator as BudgetCalculator, refine_peak, require_sella, validate_settings


def validate_request(path: Path):
    request = load_json_object(path)
    if request.get("document_kind") != "matris_sella_smoke_request" or request.get("execution_authorized") is not True:
        raise ValueError("explicit one-sample smoke authorization is required")
    for key in ("training_authorized", "vasp_authorized", "scientific_acceptance_authorized"):
        if request.get(key) is not False:
            raise ValueError(f"smoke request must set {key} false")
    validate_settings(request["settings"])
    if request["settings"]["max_steps"] > 3:
        raise ValueError("smoke test permits at most three Sella steps")
    for key, maximum in (("maximum_evaluations", 80), ("maximum_wall_seconds", 300)):
        value = request[key]
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"invalid smoke budget: {key}")
    for key in ("minimum_pair_distance_A", "maximum_displacement_A"):
        value = request[key]
        if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
            raise ValueError(f"invalid geometry bound: {key}")
    for key in ("structure", "checkpoint"):
        ref = request[key]
        source = Path(ref["path"])
        if not source.is_absolute():
            source = path.parent / source
        if not source.is_file() or sha256_file(source) != ref["sha256"]:
            raise ValueError(f"smoke {key} hash mismatch")
        request[key] = {**ref, "path": str(source.resolve())}
    return request


def run(request_path: Path, output: Path):
    import torch

    request = validate_request(request_path)
    if socket.gethostname() != "MZ73" or not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("smoke execution requires an allocated Slurm job on MZ73")
    if not torch.cuda.is_available():
        raise RuntimeError("allocated CUDA device unavailable")
    require_sella()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    seed = read(request["structure"]["path"], format="vasp")

    def geometry_check(atoms):
        minimum = _minimum_pair_distance(atoms)
        displacement = float(np.linalg.norm(atoms.positions - seed.positions, axis=1).max())
        return {"passed": minimum >= request["minimum_pair_distance_A"] and displacement <= request["maximum_displacement_A"],
                "minimum_pair_distance_A": minimum, "maximum_displacement_A": displacement,
                "scope": "bounded_runtime_smoke_geometry_only_not_path_validation"}

    if geometry_check(seed)["passed"] is not True:
        raise ValueError("smoke seed failed geometry preflight")
    model = _load_calculator("matris", Path(request["checkpoint"]["path"]), "cuda")
    calculator = BudgetCalculator(model, request["maximum_evaluations"], request["maximum_wall_seconds"])
    torch.cuda.reset_peak_memory_stats()
    record = refine_peak(seed, calculator, request["settings"], output / "sella",
                         source={"request_sha256": sha256_file(request_path),
                                 "checkpoint_sha256": request["checkpoint"]["sha256"],
                                 "seed_structure_sha256": request["structure"]["sha256"],
                                 "validation_only": True}, geometry_check=geometry_check)
    snapshots = record["snapshots"]
    passed = (record["status"] in {"needs_work_review", "optimizer_not_converged"}
              and record.get("optimizer_steps", 0) > 0 and len(snapshots) >= 2)
    result = {"document_kind": "matris_sella_smoke_result", "runtime_smoke_passed": passed,
              "hostname": socket.gethostname(), "gpu_job_id": os.environ["SLURM_JOB_ID"],
              "versions": {name: version(name) for name in ("sella", "ase", "torch")},
              "gpu": torch.cuda.get_device_name(), "checkpoint_sha256": request["checkpoint"]["sha256"],
              "checkpoint_unchanged": sha256_file(Path(request["checkpoint"]["path"])) == request["checkpoint"]["sha256"],
              "seed_structure_sha256": request["structure"]["sha256"],
              "request_sha256": sha256_file(request_path), "optimizer_status": record["status"],
              "optimizer_steps": record.get("optimizer_steps"), "model_evaluations": calculator.evaluations,
              "elapsed_seconds": time.monotonic() - started,
              "peak_gpu_allocated_MiB": torch.cuda.max_memory_allocated() / 1024**2,
              "initial_fmax_eV_per_A": snapshots[0]["fmax_eV_per_A"] if snapshots else None,
              "last_fmax_eV_per_A": snapshots[-1]["fmax_eV_per_A"] if snapshots else None,
              "valid_snapshot_count": len(snapshots), "error": record.get("error"),
              "training_performed": False, "VASP_performed": False, "scientifically_validated_ts": False}
    write_json_atomic(output / "smoke_result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        validate_request(args.request)
        require_sella()
        print("hash-bound request and Sella import preflight passed")
        return
    result = run(args.request, args.output)
    print(f"runtime_smoke_passed={result['runtime_smoke_passed']}")
    raise SystemExit(0 if result["runtime_smoke_passed"] else 1)


if __name__ == "__main__":
    main()
