"""Exact twelve-candidate AQCat batch in a real Slurm GPU allocation only."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
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


def verify_budget(request):
    if request["limits"] != {"seed_max_steps": 80, "fmax_eV_per_A": .1, "LBFGS_maxstep_A": .2}:
        raise ValueError("optimizer scope changed")
    if request["resources"] != {"GPU_count": 1, "CPU_count": 4, "memory_GB": 32,
            "wall_seconds": 600, "allocator_MiB": 16384} or request["domain"]["ranking_allowed"]:
        raise ValueError("resource budget or domain-use boundary changed")
    if request["boundaries"] != {"training": False, "model_promotion": False, "VASP": False, "CPU_fallback": False}:
        raise ValueError("forbidden expansion of GPU stage")


def verify(path: Path, expected: str):
    if sha256_file(path) != expected:
        raise ValueError("request hash changed")
    root = path.parent.resolve()
    request = load_json_object(path)
    auth = load_json_object(root / "authorization.json")
    if (auth.get("action") != "RUN_GPU_ADSORPTION_RELAXATION" or not auth.get("user_authorized")
            or auth.get("request_sha256") != expected or auth.get("source_review_sha256") != REVIEW_SHA):
        raise ValueError("exact human authorization missing")
    if (request["execution_mode"] != "slurm" or [c["name"] for c in request["cases"]] != NAMES
            or request["model"]["sha256"] != MODEL_SHA or request["source_review_sha256"] != REVIEW_SHA):
        raise ValueError("scope, checkpoint or candidate membership changed")
    verify_budget(request)
    if socket.gethostname() != "MZ73" or root != Path(request["remote_root"]).resolve():
        raise ValueError("wrong host or task root")
    boundary = Path("/home/sbq/sbq").resolve()
    if not root.is_relative_to(boundary) or not Path(request["model"]["path"]).resolve().is_relative_to(boundary):
        raise ValueError("task or checkpoint escapes authorized server root")
    for entry in request["artifacts"]:
        target = (root / entry["path"]).resolve()
        if not target.is_relative_to(root) or sha256_file(target) != entry["sha256"]:
            raise ValueError("package artifact changed or escaped")
    policy = yaml.safe_load((root / "execution_backends.yaml").read_text(encoding="utf-8"))
    if "adsorption_candidate_ml_relaxation_and_ranking" not in policy["backends"]["aqcat_gpu"]["allowed"]:
        raise ValueError("backend lacks adsorption authority")
    if sha256_file(Path(request["model"]["path"])) != MODEL_SHA:
        raise ValueError("remote checkpoint changed")
    reviewed = load_json_object(root / "evidence/source_review.json")
    if sha256_file(root / "evidence/source_review.json") != REVIEW_SHA:
        raise ValueError("accepted geometry review changed")
    expected_seeds = {r["name"]: r["structure_sha256"] for r in reviewed["candidates"]}
    for case in request["cases"]:
        if sha256_file(root / case["seed_path"]) != case["seed_sha256"] or case["seed_sha256"] != expected_seeds[case["name"]]:
            raise ValueError("accepted seed changed")
        validate_handoff(root / case["handoff_path"], root=root, schema_path=root / "handoff.schema.json")
    return request, root


def cpu_preflight(path, expected):
    request, root = verify(path, expected)
    for module in ("torch", "ase", "fairchem", "jsonschema"):
        if importlib.util.find_spec(module) is None:
            raise ImportError(module)
    import torch
    if torch.version.cuda is None:
        raise RuntimeError("CPU-only Torch cannot execute this request")
    print("CPU_PREFLIGHT_PASS:12 bound seeds/model/runtime; GPU admission remains inside allocated Slurm job", flush=True)
    return request, root


def gpu_admission(expected):
    job = os.environ.get("SLURM_JOB_ID", "")
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    selected = os.environ.get("SLURM_JOB_GPUS", visible)
    if not job.isdigit() or not visible or "," in visible or not selected or "," in selected:
        raise ValueError("one actual scheduler-allocated GPU required")
    record = subprocess.check_output(["scontrol", "show", "job", "-o", job], timeout=15).decode()
    if "JobState=RUNNING" not in record or f"Comment={expected}" not in record or "NodeList=MZ73" not in record:
        raise ValueError("real Slurm job/request/allocation binding failed")
    info = subprocess.check_output(["nvidia-smi", "-i", selected,
        "--query-gpu=uuid,name,memory.total,memory.free", "--format=csv,noheader,nounits"], timeout=15).decode()
    rows = [line for line in info.splitlines() if line.strip()]
    if len(rows) != 1 or float(rows[0].split(",")[-1]) < 20000:
        raise ValueError("allocated GPU lacks required free memory")
    processes = subprocess.check_output(["nvidia-smi", "-i", selected,
        "--query-compute-apps=pid", "--format=csv,noheader,nounits"], timeout=15).decode().strip()
    if processes:
        raise ValueError("allocated GPU already has a compute process; no sharing/stop authorized")
    return {"scheduler_job_id": job, "CUDA_VISIBLE_DEVICES": visible, "SLURM_JOB_GPUS": selected,
            "nvidia_smi": rows[0], "existing_compute_processes": []}


def run(path, expected):
    request, root = verify(path, expected)
    output = root / "output"
    output.mkdir(exist_ok=False)
    code, error = 1, None
    started = time.time()
    def interrupted(signum, _frame):
        raise TimeoutError(f"scheduler signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        admission = gpu_admission(expected)
        write_json_exclusive(output / "gpu_admission.json", admission)
        import torch
        from fairchem.core.common.relaxation.ase_utils import patched_calc
        from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
        from ase.optimize import LBFGS
        from archive.fe110_adsorption_validation_20261018.runtime import relax_case
        from scripts.adsorption.direct_gpu_batch import cuda_binding
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("one CUDA device required; no CPU fallback")
        if LBFGS.defaults["maxstep"] != .2:
            raise ValueError("native optimizer default changed")
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(16384 * 1024**2 / total)
        calc = patched_calc(checkpoint_path=request["model"]["path"], is_spin_off=False, is_low_fi=False, cpu=False)
        write_json_exclusive(output / "model_device.json", cuda_binding(calc))
        deadline = time.monotonic() + 570
        records = [relax_case(root, output / "finetune", case, "seed", calc, request["limits"], deadline)
                   for case in request["cases"]]
        write_json_exclusive(output / "cases.json", {"model_sha256": MODEL_SHA, "cases": records})
        code = 0
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        write_json_exclusive(output / "producer_exit_record.json", {"exit_code": code, "error": error,
            "request_sha256": expected, "scheduler_job_id": os.environ.get("SLURM_JOB_ID"),
            "elapsed_seconds": time.time() - started, "training": False, "VASP_submitted": False,
            "scientific_acceptance": False, "evidence_class": "producer_not_scheduler_accounting"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("preflight", "run"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    {"preflight": cpu_preflight, "run": run}[args.phase](args.request, args.sha256)
