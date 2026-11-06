"""Independent Slurm replica of the twelve unchanged, reviewed ML candidates."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import socket
import time

import yaml

from artifact_io import load_json_object, sha256_file, write_json_exclusive
from aqcat25_handoff import validate_handoff
from device import gpu_admission, model_binding

NAMES = ["05_S1", "05_S2", "06_S1", "06_S2", "07_S1", "09_S1", "11_S1", "12_S1", "13_S1", "14_S1", "18_S1", "18_S2"]
MODEL_SHA = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"
REVIEW_SHA = "abb50499fb05a9caec0c53944fe876ffd3112e9daf2de460ac1b4394798c486f"
PARENT_SHA = "b95896f6da62f52d504c97663b4a30e0b3121872463a73f95ea277f6edaf553d"
HOSTS = {"aqcat_gpu": "MZ73", "buct2_gpu": "pc-G7466-M6"}


def verify_scope(request):
    if (request["execution_mode"] != "slurm" or request["backend"] not in HOSTS
            or [case["name"] for case in request["cases"]] != NAMES
            or request["model"]["sha256"] != MODEL_SHA or request["source_review_sha256"] != REVIEW_SHA
            or request["parent_request_sha256"] != PARENT_SHA):
        raise ValueError("reviewed scope/model/source changed")
    if request["limits"] != {"seed_max_steps": 80, "fmax_eV_per_A": .1, "LBFGS_maxstep_A": .2}:
        raise ValueError("optimizer budget changed")
    if request["resources"] != {"GPU_count": 1, "CPU_count": 4, "memory_GB": 32,
            "wall_seconds": 600, "allocator_MiB": 16384} or request["domain"]["ranking_allowed"]:
        raise ValueError("resource/domain scope changed")
    if request["boundaries"] != {"training": False, "model_promotion": False, "VASP": False, "CPU_fallback": False}:
        raise ValueError("forbidden expansion")
    if request["replica_policy"] != "independent_first_completed_eligible_review" or "arbitration" in request:
        raise ValueError("obsolete first-start permit is forbidden")


def verify(path, expected):
    if sha256_file(path) != expected:
        raise ValueError("request hash changed")
    root = path.parent.resolve()
    request = load_json_object(path)
    verify_scope(request)
    auth = load_json_object(root / "authorization.json")
    if (auth.get("action") != "REPAIR_AND_RUN_INDEPENDENT_GPU_REPLICAS"
            or not auth.get("user_authorized") or auth.get("request_sha256") != expected
            or auth.get("parent_request_sha256") != PARENT_SHA):
        raise ValueError("exact user repair authorization missing")
    boundary = Path("/home/sbq/sbq").resolve()
    if (socket.gethostname() != HOSTS[request["backend"]] or root != Path(request["remote_root"]).resolve()
            or not root.is_relative_to(boundary)):
        raise ValueError("wrong execution host/root")
    for entry in request["artifacts"]:
        target = (root / entry["path"]).resolve()
        if not target.is_relative_to(root) or sha256_file(target) != entry["sha256"]:
            raise ValueError("package artifact changed/escaped")
    for entry in [request["model"], request["cudart"]]:
        target = Path(entry["path"]).resolve()
        if not target.is_relative_to(boundary) or sha256_file(target) != entry["sha256"]:
            raise ValueError("shared immutable runtime/model changed/escaped")
    policy = yaml.safe_load((root / "execution_backends.yaml").read_text(encoding="utf-8"))
    if request["backend"] == "buct2_gpu" and policy["backends"]["buct2_gpu"]["role"] != "candidate_acceleration_only":
        raise ValueError("wrong backend role")
    review = load_json_object(root / "evidence/source_review.json")
    if sha256_file(root / "evidence/source_review.json") != REVIEW_SHA:
        raise ValueError("accepted review changed")
    accepted = {row["name"]: row["structure_sha256"] for row in review["candidates"]}
    for case in request["cases"]:
        if sha256_file(root / case["seed_path"]) != case["seed_sha256"] or case["seed_sha256"] != accepted[case["name"]]:
            raise ValueError("accepted seed changed")
        validate_handoff(root / case["handoff_path"], root=root, schema_path=root / "handoff.schema.json")
    return request, root


def cpu_preflight(path, expected):
    verify(path, expected)
    import torch
    from fairchem.core.common.relaxation.ase_utils import patched_calc  # noqa: F401
    from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
    from ase.optimize import LBFGS
    from archive.fe110_adsorption_validation_20261018.runtime import relax_case  # noqa: F401
    if torch.version.cuda is None or LBFGS.defaults["maxstep"] != .2:
        raise RuntimeError("CUDA runtime/optimizer mismatch")
    torch.zeros(1).add_(1)
    print("PREFLIGHT_PASS:exact12/native imports/CPU tensor; no GPU model execution", flush=True)


def run(path, expected):
    started = time.monotonic()
    request, root = verify(path, expected)
    output = root / "output"
    output.mkdir(exist_ok=False)
    code, error, evidence = 1, None, []

    def interrupted(signum, _frame):
        raise TimeoutError(f"scheduler signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        admission = gpu_admission(expected, HOSTS[request["backend"]], request["cudart"]["path"], evidence)
        write_json_exclusive(output / "gpu_admission.json", admission)
        import torch
        from fairchem.core.common.relaxation.ase_utils import patched_calc
        from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
        from archive.fe110_adsorption_validation_20261018.runtime import relax_case
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(16384 * 1024**2 / total)
        calc = patched_calc(checkpoint_path=request["model"]["path"], is_spin_off=False, is_low_fi=False, cpu=False)
        write_json_exclusive(output / "model_device.json", model_binding(calc, admission))
        records = [relax_case(root, output / "finetune", case, "seed", calc, request["limits"], started + 570)
                   for case in request["cases"]]
        write_json_exclusive(output / "cases.json", {"model_sha256": MODEL_SHA, "cases": records})
        code = 0
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        write_json_exclusive(output / "device_commands.json", {"commands": evidence,
            "environment": {key: os.environ.get(key) for key in
                ("SLURM_JOB_ID", "SLURM_JOB_GPUS", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER")}})
        write_json_exclusive(output / "producer_exit_record.json", {"exit_code": code, "error": error,
            "request_sha256": expected, "scheduler_job_id": os.environ.get("SLURM_JOB_ID"),
            "elapsed_seconds": time.monotonic() - started, "independent_replica": True,
            "training": False, "VASP_submitted": False, "scientific_acceptance": False,
            "evidence_class": "producer_not_scheduler_accounting"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("preflight", "run"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    {"preflight": cpu_preflight, "run": run}[args.phase](args.request, args.sha256)
