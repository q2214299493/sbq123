"""BUCT2 replica: exact inputs, real GPU, and a work-issued single-winner permit."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time

import yaml

from artifact_io import load_json_object, sha256_file, write_json_exclusive
from aqcat25_handoff import validate_handoff

NAMES = ["05_S1", "05_S2", "06_S1", "06_S2", "07_S1", "09_S1", "11_S1", "12_S1", "13_S1", "14_S1", "18_S1", "18_S2"]
MODEL_SHA = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"
REVIEW_SHA = "abb50499fb05a9caec0c53944fe876ffd3112e9daf2de460ac1b4394798c486f"
PARENT_SHA = "b95896f6da62f52d504c97663b4a30e0b3121872463a73f95ea277f6edaf553d"
TERMINAL = {"CANCELLED", "FAILED", "COMPLETED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "BOOT_FAIL", "DEADLINE", "REVOKED"}


def verify_scope(request):
    if (request["execution_mode"] != "slurm" or request["backend"] != "buct2_gpu"
            or [c["name"] for c in request["cases"]] != NAMES or request["model"]["sha256"] != MODEL_SHA
            or request["source_review_sha256"] != REVIEW_SHA or request["parent_request_sha256"] != PARENT_SHA):
        raise ValueError("scope/model/source changed")
    if request["limits"] != {"seed_max_steps": 80, "fmax_eV_per_A": .1, "LBFGS_maxstep_A": .2}:
        raise ValueError("optimizer scope changed")
    if request["resources"] != {"GPU_count": 1, "CPU_count": 4, "memory_GB": 32,
            "wall_seconds": 600, "allocator_MiB": 16384} or request["domain"]["ranking_allowed"]:
        raise ValueError("resource/domain scope changed")
    if request["boundaries"] != {"training": False, "model_promotion": False, "VASP": False, "CPU_fallback": False}:
        raise ValueError("forbidden expansion")
    arbitration = request["arbitration"]
    if (arbitration.get("required_before_model") is not True or arbitration.get("permit_wait_seconds") != 120
            or not re.fullmatch(r"[0-9]+", arbitration.get("peer_job_id", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", arbitration.get("peer_request_sha256", ""))
            or not arbitration.get("peer_remote_root", "").startswith("/home/sbq/sbq/")):
        raise ValueError("single-winner guard changed")


def verify(path, expected):
    if sha256_file(path) != expected:
        raise ValueError("request hash changed")
    root = path.parent.resolve()
    request = load_json_object(path)
    verify_scope(request)
    auth = load_json_object(root / "authorization.json")
    if (auth.get("action") != "RUN_SECOND_GPU_REPLICA_KEEP_FIRST" or not auth.get("user_authorized")
            or auth.get("request_sha256") != expected or auth.get("parent_request_sha256") != PARENT_SHA):
        raise ValueError("exact human authorization missing")
    if socket.gethostname() != "pc-G7466-M6" or root != Path(request["remote_root"]).resolve():
        raise ValueError("wrong host/root")
    boundary = Path("/home/sbq/sbq").resolve()
    if not root.is_relative_to(boundary) or not Path(request["model"]["path"]).resolve().is_relative_to(root):
        raise ValueError("write/model boundary escaped")
    for entry in request["artifacts"]:
        target = (root / entry["path"]).resolve()
        if not target.is_relative_to(root) or sha256_file(target) != entry["sha256"]:
            raise ValueError("package artifact changed/escaped")
    policy = yaml.safe_load((root / "execution_backends.yaml").read_text(encoding="utf-8"))
    if policy["backends"]["buct2_gpu"]["role"] != "candidate_acceleration_only":
        raise ValueError("wrong backend role")
    if sha256_file(Path(request["model"]["path"])) != MODEL_SHA or sha256_file(root / "evidence/source_review.json") != REVIEW_SHA:
        raise ValueError("checkpoint or accepted review changed")
    accepted = {r["name"]: r["structure_sha256"] for r in load_json_object(root / "evidence/source_review.json")["candidates"]}
    for case in request["cases"]:
        if sha256_file(root / case["seed_path"]) != case["seed_sha256"] or case["seed_sha256"] != accepted[case["name"]]:
            raise ValueError("accepted seed changed")
        validate_handoff(root / case["handoff_path"], root=root, schema_path=root / "handoff.schema.json")
    return request, root


def cpu_preflight(path, expected):
    request, root = verify(path, expected)
    import torch
    from fairchem.core.common.relaxation.ase_utils import patched_calc  # noqa: F401
    from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
    from ase.optimize import LBFGS
    from archive.fe110_adsorption_validation_20261018.runtime import relax_case  # noqa: F401
    if torch.version.cuda is None or LBFGS.defaults["maxstep"] != .2:
        raise RuntimeError("CUDA runtime/native optimizer mismatch")
    torch.zeros(1).add_(1)
    print("CPU_PREFLIGHT_PASS:exact12/native imports/CPU tensor;no GPU/model execution", flush=True)
    return request, root


def gpu_admission(expected):
    job = os.environ.get("SLURM_JOB_ID", "")
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    selected = os.environ.get("SLURM_JOB_GPUS", visible)
    if not job.isdigit() or not visible or "," in visible or not selected or "," in selected:
        raise ValueError("one real allocated GPU required")
    raw = subprocess.check_output(["scontrol", "show", "job", "-o", job], timeout=15).decode()
    if "JobState=RUNNING" not in raw or f"Comment={expected}" not in raw or "NodeList=pc-G7466-M6" not in raw:
        raise ValueError("scheduler/request/node binding failed")
    info = subprocess.check_output(["nvidia-smi", "-i", selected,
        "--query-gpu=uuid,name,memory.total,memory.free", "--format=csv,noheader,nounits"], timeout=15).decode()
    rows = [line for line in info.splitlines() if line.strip()]
    if len(rows) != 1 or float(rows[0].split(",")[-1]) < 20000:
        raise ValueError("allocated GPU free memory below20GiB admission")
    processes = subprocess.check_output(["nvidia-smi", "-i", selected,
        "--query-compute-apps=pid", "--format=csv,noheader,nounits"], timeout=15).decode().strip()
    if processes:
        raise ValueError("another compute process present;sharing not authorized for this replica")
    return {"scheduler_job_id": job, "CUDA_VISIBLE_DEVICES": visible, "SLURM_JOB_GPUS": selected,
        "checked_at": datetime.now(timezone.utc).isoformat(), "nvidia_smi": rows[0]}


def validate_permit(permit, expected, job, arbitration):
    if (permit.get("action") != "RUN_EXACT_GPU_BATCH" or permit.get("winner_job_id") != job
            or permit.get("request_sha256") != expected or permit.get("peer_job_id") != arbitration["peer_job_id"]
            or permit.get("peer_request_sha256") != arbitration["peer_request_sha256"]
            or permit.get("peer_terminal_state") not in TERMINAL):
        raise ValueError("missing or mismatched single-winner permit")


def await_permit(root, expected, job, arbitration, seconds=120):
    deadline = time.monotonic() + seconds
    path = root / "winner_permit.json"
    while time.monotonic() < deadline:
        if path.exists():
            validate_permit(load_json_object(path), expected, job, arbitration)
            return sha256_file(path)
        time.sleep(2)
    raise TimeoutError("no work-issued single-winner permit;model was not loaded")


def native_cuda_binding(calculator, admission):
    model = getattr(calculator, "model", None)
    if model is None:
        model = calculator.trainer.model
    device = next(model.parameters()).device
    if device.type != "cuda":
        raise RuntimeError("model is not actually onCUDA;no CPU fallback")
    job = os.environ.get("SLURM_JOB_ID", "")
    if not job.isdigit() or job != admission["scheduler_job_id"]:
        raise ValueError("model and native job binding differ")
    uuid = admission["nvidia_smi"].split(",", 1)[0].strip()
    if not uuid.startswith("GPU-"):
        raise ValueError("NVML physical UUID missing")
    return {"model_device": str(device), "physical_gpu_uuid": uuid, "execution_mode": "slurm",
            "scheduler_job_id": job, "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "")}


def run(path, expected):
    started = time.monotonic()
    request, root = verify(path, expected)
    output = root / "output"
    output.mkdir(exist_ok=False)
    code, error, permit_sha = 1, None, None
    def interrupted(signum, _frame):
        raise TimeoutError(f"scheduler signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        admission = gpu_admission(expected)
        write_json_exclusive(output / "gpu_ready.json", {**admission, "request_sha256": expected, "model_loaded": False})
        permit_sha = await_permit(root, expected, admission["scheduler_job_id"], request["arbitration"])
        gpu_admission(expected)
        import torch
        from fairchem.core.common.relaxation.ase_utils import patched_calc
        from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
        from archive.fe110_adsorption_validation_20261018.runtime import relax_case
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("one CUDA device required;no CPU fallback")
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(16384 * 1024**2 / total)
        calc = patched_calc(checkpoint_path=request["model"]["path"], is_spin_off=False, is_low_fi=False, cpu=False)
        write_json_exclusive(output / "model_device.json", native_cuda_binding(calc, admission))
        records = [relax_case(root, output / "finetune", case, "seed", calc, request["limits"], started + 570)
                   for case in request["cases"]]
        write_json_exclusive(output / "cases.json", {"model_sha256": MODEL_SHA, "cases": records})
        code = 0
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        write_json_exclusive(output / "producer_exit_record.json", {"exit_code": code, "error": error,
            "request_sha256": expected, "scheduler_job_id": os.environ.get("SLURM_JOB_ID"),
            "elapsed_seconds": time.monotonic() - started, "winner_permit_sha256": permit_sha,
            "training": False, "VASP_submitted": False, "scientific_acceptance": False,
            "evidence_class": "producer_not_scheduler_accounting"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("preflight", "run"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    {"preflight": cpu_preflight, "run": run}[args.phase](args.request, args.sha256)
