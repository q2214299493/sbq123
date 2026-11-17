"""One allocated-GPU, frozen-checkpoint train/development force prediction only."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

MODEL_SHA = "2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0"


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("file escapes execution package")
    return path


def validate_scope(request):
    if request["action"] != "FROZEN_TRAIN_DEVELOPMENT_FORCES_ONLY" or request["model"]["sha256"] != MODEL_SHA:
        raise ValueError("wrong action or frozen checkpoint")
    if request["forbidden_work"] != {"training": True, "optimization": True, "DFT": True, "heldout_or_quarantine": True, "model_reselection": True}:
        raise ValueError("scientific boundaries changed")
    if request["max_GPU_count"] != 1 or not 0 < request["producer_seconds"] <= request["max_GPU_seconds"] <= 600:
        raise ValueError("GPU budget changed")
    rows = request["samples"]
    if len(rows) != 614 or len({r["sample_id"] for r in rows}) != 614 or Counter(r["partition"] for r in rows) != {"train": 536, "development": 78}:
        raise ValueError("not exactly536 train+78 development;protected samples forbidden")


def verify(path, expected_sha, remote=False):
    if digest(path) != expected_sha:
        raise ValueError("request hash mismatch")
    root = path.parent.resolve()
    request = json.loads(path.read_text(encoding="utf-8"))
    validate_scope(request)
    approval = json.loads((root / "authorization.json").read_text(encoding="utf-8"))
    if approval["request_sha256"] != expected_sha or approval["action"] != request["action"] or approval["user_authorized"] is not True:
        raise ValueError("missing current execution authorization")
    for row in request["artifacts"]:
        if digest(inside(root, row["path"])) != row["sha256"]:
            raise ValueError("bound input changed: " + row["path"])
    if remote:
        if socket.gethostname().split(".")[0] != request["hostname"] or root != Path(request["remote_root"]).resolve():
            raise ValueError("host or execution root mismatch")
        boundary = Path("/home/sbq/sbq").resolve()
        if str(boundary) != request["canonical_remote_boundary"] or not root.is_relative_to(boundary):
            raise ValueError("canonical write boundary mismatch")
        if not Path(request["model"]["path"]).resolve().is_relative_to(boundary) or digest(request["model"]["path"]) != MODEL_SHA:
            raise ValueError("existing remote checkpoint differs from frozen model")
        for item in request["native_source_files"]:
            native = Path(item["path"]).resolve()
            if not native.is_relative_to(boundary) or digest(native) != item["sha256"]:
                raise ValueError("native AQCat25 source binding changed")
    return request, root


def allocated_gpu(assigned):
    if not assigned or "," in assigned or not (assigned.isdigit() or assigned.startswith("GPU-")):
        raise ValueError("one native Slurm GPU assignment required")
    text = subprocess.check_output(["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,memory.free,utilization.gpu", "--format=csv,noheader,nounits"], text=True, timeout=15)
    rows = list(csv.reader(text.strip().splitlines(), skipinitialspace=True))
    if not rows or any(len(r) != 6 for r in rows):
        raise RuntimeError("incomplete allocated NVML snapshot")
    selected = rows if len(rows) == 1 else [r for r in rows if assigned in r[:2]]
    if len(selected) != 1:
        raise RuntimeError("cannot resolve allocated physical UUID")
    index, uuid, model, total, free, utilization = selected[0]
    processes = subprocess.check_output(["nvidia-smi", "-i", uuid, "--query-compute-apps=pid,gpu_uuid", "--format=csv,noheader,nounits"], text=True, timeout=15).strip()
    if processes or int(free) < 20000 or int(utilization) > 5:
        raise RuntimeError("allocated GPU occupied or insufficient free memory")
    return {"index": int(index), "uuid": uuid, "model": model, "total_MiB": int(total), "free_MiB": int(free), "utilization_percent": int(utilization), "Slurm_assignment": assigned}


def environment_preflight(request, root):
    import torch
    from fairchem.core.common.relaxation.ase_utils import patched_calc
    from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
    if not callable(patched_calc) or any(importlib.util.find_spec(name) is None for name in ("ase", "e3nn", "torch_geometric", "torch_scatter")):
        raise RuntimeError("native inference dependencies missing")
    save(root / "environment_preflight.json", {"status": "PASS_NATIVE_IMPORTS_MODEL_NOT_LOADED", "request_sha256": digest(root / "request.json"),
         "torch": torch.__version__, "compiled_CUDA": torch.version.cuda, "CUDA_initialized": torch.cuda.is_initialized(), "samples": len(request["samples"]), "inference_or_training_started": False})


def predict(request, root, output, gpu, deadline):
    import numpy as np
    import torch
    from ase.io import read
    from fairchem.core.common.relaxation.ase_utils import patched_calc
    from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("one allocated CUDA device required;no CPU fallback")
    if float(torch.ones(8, device="cuda:0").sum().item()) != 8:
        raise RuntimeError("CUDA kernel preflight failed")
    torch.set_num_threads(4)
    torch.manual_seed(42)
    calc = patched_calc(checkpoint_path=request["model"]["path"], is_spin_off=False, is_low_fi=False, cpu=False)
    parameter = next(calc.trainer.model.parameters())
    if parameter.device.type != "cuda":
        raise RuntimeError("model parameters are not on CUDA")
    save(output / "GPU_binding.json", {"request_sha256": digest(root / "request.json"), "scheduler_job_id": os.environ["SLURM_JOB_ID"],
         "checkpoint_sha256": MODEL_SHA, "GPU": gpu, "torch": torch.__version__, "CUDA": torch.version.cuda,
         "model_parameter_device": str(parameter.device), "model_parameter_dtype": str(parameter.dtype), "native_physical_force_normalization": "patched_calc;not manually reapplied"})
    frames = output / "frames"
    frames.mkdir(exist_ok=False)
    result = []
    for row in request["samples"]:
        if time.monotonic() > deadline:
            raise TimeoutError("bounded force prediction deadline exhausted")
        path = inside(root, row["structure_path"])
        if digest(path) != row["structure_sha256"]:
            raise ValueError("geometry changed before prediction")
        atoms = read(path, format="vasp")
        fixed = sorted(int(i) for constraint in atoms.constraints for i in constraint.get_indices())
        if fixed != list(range(18)) or atoms.get_chemical_symbols() != row["symbols"]:
            raise ValueError("fixed-mask or atom-order mismatch")
        positions, cell = atoms.positions.copy(), atoms.cell.array.copy()
        atoms.set_tags(np.zeros(len(atoms), dtype=int))
        atoms.info.update(is_spin_off=False, is_low_fi=False)
        atoms.calc = calc
        forces = atoms.get_forces(apply_constraint=False)
        if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all() or not np.array_equal(positions, atoms.positions) or not np.array_equal(cell, atoms.cell.array):
            raise ValueError("invalid forces or coordinates changed")
        record = {"sample_id": row["sample_id"], "structure_sha256": row["structure_sha256"], "predicted_forces_eV_per_A": forces.tolist()}
        save(frames / (row["sample_id"] + ".json"), record)
        result.append(record)
        if len(result) == 1:
            save(output / "first_frame_check.json", {"input_hash": row["structure_sha256"], "coordinates_unchanged": True, "finite_native_physical_forces": True, "GPU_binding_sha256": digest(output / "GPU_binding.json")})
        if len(result) % 25 == 0 or len(result) == 614:
            print(json.dumps({"predicted": len(result), "total": 614}), flush=True)
    if digest(request["model"]["path"]) != MODEL_SHA:
        raise ValueError("frozen checkpoint changed during inference")
    save(output / "predictions614.json", {"checkpoint_sha256": MODEL_SHA, "samples": result,
         "request_sha256": digest(root / "request.json"), "GPU_binding_sha256": digest(output / "GPU_binding.json"), "training_or_optimization": False})


def run(request, root):
    job_id = os.environ.get("SLURM_JOB_ID", "")
    if not job_id.isdigit():
        raise ValueError("native Slurm allocation required")
    output = Path(os.environ["RUN_ROOT"]).resolve()
    if not output.is_relative_to(root) or not output.is_dir():
        raise ValueError("output directory escapes execution root")
    started, start = datetime.now(timezone.utc).isoformat(), time.monotonic()
    code, error = 1, None
    try:
        gpu = allocated_gpu(os.environ.get("SLURM_JOB_GPUS", os.environ.get("CUDA_VISIBLE_DEVICES", "")))
        os.environ["CUDA_VISIBLE_DEVICES"] = gpu["uuid"]
        predict(request, root, output, gpu, start + request["producer_seconds"])
        code = 0
    except Exception as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        save(output / "producer_exit.json", {"scheduler_job_id": job_id, "producer_exit_code": code, "error": error,
             "started_UTC": started, "finished_UTC": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.monotonic() - start,
             "completed_frames": len(list((output / "frames").glob("*.json"))), "request_sha256": digest(root / "request.json"),
             "not_scheduler_terminal_evidence": True, "training": False, "DFT": False, "optimization": False, "model_promotion": False})


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("verify", "environment", "run"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    request, root = verify(args.request, args.request_sha256, remote=args.action != "verify")
    if args.action == "environment":
        environment_preflight(request, root)
    elif args.action == "run":
        preflight = json.loads((root / "environment_preflight.json").read_text(encoding="utf-8"))
        if preflight["request_sha256"] != args.request_sha256 or preflight["status"] != "PASS_NATIVE_IMPORTS_MODEL_NOT_LOADED":
            raise ValueError("missing current native environment preflight")
        def stop(signum, frame):
            raise TimeoutError("producer signal " + str(signum))
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        run(request, root)
    else:
        print(json.dumps({"status": "PASS_FROZEN614_INPUTS", "request_sha256": args.request_sha256}))


if __name__ == "__main__":
    main()
