"""Resolve allocated CUDA device zero by physical PCI identity, never Slurm index."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess


def command(argv, evidence):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=15)
    evidence.append({"argv": argv, "exit_code": result.returncode,
                     "stdout": result.stdout[:12000], "stderr": result.stderr[:4000]})
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}; see device evidence")
    return result.stdout


def normalized_pci(value):
    match = re.fullmatch(r"([0-9a-fA-F]{4,8}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])", value)
    if not match:
        raise ValueError("invalid physical PCI address")
    return tuple(int(part, 16) for part in match.groups())


def allocated_identity(cudart_path, evidence):
    import torch

    if not os.environ.get("SLURM_JOB_ID", "").isdigit():
        raise RuntimeError("real Slurm allocation required")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("exactly one actual CUDA device required; no CPU fallback")
    library = ctypes.CDLL(str(cudart_path))
    fn = library.cudaDeviceGetPCIBusId
    fn.argtypes = [ctypes.POINTER(ctypes.c_char), ctypes.c_int, ctypes.c_int]
    fn.restype = ctypes.c_int
    bus = ctypes.create_string_buffer(32)
    status = fn(bus, len(bus), 0)
    if status:
        raise RuntimeError(f"cudaDeviceGetPCIBusId returned {status}")
    pci = bus.value.decode("ascii")
    return query_identity(pci, evidence)


def query_identity(pci, evidence):
    raw = command(["nvidia-smi", "-i", pci,
        "--query-gpu=uuid,pci.bus_id,name,memory.total,memory.free",
        "--format=csv,noheader,nounits"], evidence)
    rows = [row for row in raw.splitlines() if row.strip()]
    if len(rows) != 1:
        raise ValueError("physical device query must return exactly one row")
    fields = [field.strip() for field in rows[0].split(",")]
    if len(fields) != 5 or not fields[0].startswith("GPU-") or normalized_pci(fields[1]) != normalized_pci(pci):
        raise ValueError("CUDA/NVML physical identity mismatch")
    return {"physical_gpu_uuid": fields[0], "pci_bus_id": fields[1],
            "name": fields[2], "total_MiB": float(fields[3]), "free_MiB": float(fields[4]),
            "cuda_logical_device": 0}


def gpu_admission(expected, host, cudart_path, evidence):
    job = os.environ.get("SLURM_JOB_ID", "")
    if not job.isdigit() or socket.gethostname() != host:
        raise ValueError("wrong allocation/host")
    raw = command(["scontrol", "show", "job", "-o", job], evidence)
    fields = dict(re.findall(r"(\w+)=([^\s]+)", raw))
    if fields.get("JobState") != "RUNNING" or fields.get("Comment") != expected or fields.get("NodeList") != host:
        raise ValueError("native scheduler/request binding mismatch")
    identity = allocated_identity(cudart_path, evidence)
    if identity["free_MiB"] < 20000:
        raise ValueError("allocated GPU has less than 20000 MiB free")
    processes = command(["nvidia-smi", "-i", identity["physical_gpu_uuid"],
        "--query-compute-apps=pid", "--format=csv,noheader,nounits"], evidence)
    others = [line.strip() for line in processes.splitlines()
              if line.strip() and line.strip() != str(os.getpid())]
    if others:
        raise ValueError("another compute process present; sharing not authorized")
    return {**identity, "scheduler_job_id": job,
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "SLURM_JOB_GPUS": os.environ.get("SLURM_JOB_GPUS"), "execution_mode": "slurm"}


def model_binding(calculator, admission):
    model = getattr(calculator, "model", None)
    if model is None:
        model = calculator.trainer.model
    devices = {str(parameter.device) for parameter in model.parameters()}
    if not devices or any(device not in {"cuda", "cuda:0"} for device in devices):
        raise RuntimeError("model parameters not exclusively on allocated CUDA zero")
    if os.environ.get("SLURM_JOB_ID") != admission["scheduler_job_id"]:
        raise ValueError("model job binding changed")
    return {**admission, "model_devices": sorted(devices)}


def diagnostic(cudart):
    evidence = []
    result = {"host": socket.gethostname(), "checked_at": datetime.now(timezone.utc).isoformat(),
              "environment": {key: os.environ.get(key) for key in
                  ("SLURM_JOB_ID", "SLURM_JOB_GPUS", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER")},
              "commands": evidence, "model_loaded": False, "optimization_steps": 0}
    code = 1
    try:
        result["identity"] = allocated_identity(cudart, evidence)
        import torch
        tensor = torch.arange(8, device="cuda:0").square()
        torch.cuda.synchronize()
        if tensor.sum().item() != 140:
            raise RuntimeError("CUDA arithmetic failed")
        result["CUDA_kernel"] = "PASS"
        code = 0
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    print(json.dumps(result), flush=True)
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--cudart", type=Path, required=True)
    raise SystemExit(diagnostic(parser.parse_args().cudart))
