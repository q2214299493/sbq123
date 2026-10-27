"""One authorized two-seed/two-checkpoint ML relaxation comparison."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import yaml

from scripts.adsorption.direct_force_training import make_runtime_directories, stop_owned_group, wait_bounded
from scripts.adsorption.direct_gpu_batch import cuda_binding, environment, gpu_available
from scripts.adsorption.force_finetune import local_path
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

MODULE = "archive.fe110_pair2_20261027.runtime"


def check_scope(request, approval, exception, digest):
    if (approval.get("action") != "RUN_PAIRED_ML_RELAXATION" or approval.get("request_sha256") != digest
            or approval.get("user_authorized") is not True or approval.get("user_request") != exception["authorizing_user_request"]):
        raise ValueError("exact paired-relaxation human authorization missing")
    if request["scope"] != exception["scope"]:
        raise ValueError("paired relaxation scope changed")
    scope = request["scope"]
    if scope["models"].keys() != {"control", "new512"} or [r["name"] for r in scope["cases"]] != ["10_A", "C3_05"]:
        raise ValueError("two frozen models and two preselected seeds required")
    if (scope["limits"] != {"seed_max_steps": 80, "fmax_eV_per_A": 0.1, "LBFGS_maxstep_A": 0.2}
            or scope["max_wall_seconds"] != 600 or scope["CPU_count"] != 4 or scope["memory_GB"] != 32):
        raise ValueError("bounded optimizer/resource contract changed")
    if request["boundaries"] != {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False}:
        raise ValueError("ML comparison cannot fit,promote or submitDFT")
    if request["execution_mode"] != "direct_no_scheduler" or request["scheduler_job_id"] is not None:
        raise ValueError("no simulated scheduler identity")


def verify(path, remote=False):
    root = path.parent.resolve()
    request = load_json_object(path)
    policy = local_path(root, request["policy"]["path"])
    if sha256_file(policy) != request["policy"]["sha256"]:
        raise ValueError("policy changed")
    exception = yaml.safe_load(policy.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["direct_execution_exceptions"][request["exception_id"]]
    check_scope(request, load_json_object(root / "authorization.json"), exception, sha256_file(path))
    for row in request["artifacts"]:
        if sha256_file(local_path(root, row["path"])) != row["sha256"]:
            raise ValueError("paired experiment artifact changed")
    scope = request["scope"]
    for case in scope["cases"]:
        if sha256_file(local_path(root, case["seed_path"])) != case["seed_sha256"]:
            raise ValueError("same-start geometry changed")
    frozen = load_json_object(root / "evidence/frozen_force_comparison.json")
    for name, model in scope["models"].items():
        if model["sha256"] != frozen["model_checkpoint_sha256"][name]:
            raise ValueError("previously frozen checkpoint changed")
    if remote:
        boundary = Path("/home/sbq/sbq").resolve()
        if socket.gethostname() != "MZ73" or root != Path(scope["remote_root"]).resolve() or str(boundary) != exception["canonical_remote_boundary"] or not root.is_relative_to(boundary):
            raise ValueError("wrong host or writable boundary")
        for model in scope["models"].values():
            if not Path(model["path"]).resolve().is_relative_to(boundary) or sha256_file(Path(model["path"])) != model["sha256"]:
                raise ValueError("remote checkpoint changed")
    return request, root, scope


def worker(path):
    request, root, scope = verify(path, remote=True)
    output = root / "output"
    started = datetime.now(timezone.utc).isoformat()
    code, error = 1, None
    try:
        gpu_available(scope)
        if os.environ.get("CUDA_VISIBLE_DEVICES") != scope["gpu_uuid"]:
            raise ValueError("physical GPU not bound")
        import torch
        from ase.optimize import LBFGS
        from fairchem.core.common.relaxation.ase_utils import patched_calc
        from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
        from archive.fe110_adsorption_validation_20261018.runtime import relax_case
        if LBFGS.defaults["maxstep"] != scope["limits"]["LBFGS_maxstep_A"]:
            raise ValueError("native optimizer default changed")
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(scope["gpu_sharing"]["max_training_memory_MiB"] * 1024**2 / total)
        deadline = time.monotonic() + scope["max_wall_seconds"]
        for model_name, model in scope["models"].items():
            calc = patched_calc(checkpoint_path=model["path"], is_spin_off=False, is_low_fi=False, cpu=False)
            write_json_exclusive(output / (model_name + "_device.json"), cuda_binding(calc))
            records = [relax_case(root, output / model_name, case, "seed", calc, scope["limits"], deadline) for case in scope["cases"]]
            write_json_exclusive(output / (model_name + "_cases.json"), {"checkpoint_sha256": model["sha256"], "cases": records})
            del calc
            gc.collect()
            torch.cuda.empty_cache()
        code = 0
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        write_json_exclusive(output / "producer_exit_record.json", {"exit_code": code, "error": error, "pid": os.getpid(),
            "request_sha256": sha256_file(path), "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
            "training_performed": False, "model_promoted": False, "VASP_submitted": False, "scheduler_job_id": None})


def controller(path):
    import fcntl
    request, root, scope = verify(path, remote=True)
    child, code, error = None, 1, None
    def interrupted(signum, _):
        raise InterruptedError("paired comparison interrupted " + str(signum))
    for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP]:
        signal.signal(sig, interrupted)
    try:
        affinity = sorted(os.sched_getaffinity(0))[:scope["CPU_count"]]
        os.sched_setaffinity(0, affinity)
        locks = Path("/home/sbq/sbq/aqcat25_ts_pilot/direct_gpu_locks")
        locks.mkdir(exist_ok=True)
        with (locks / (scope["gpu_uuid"] + ".lock")).open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            gpu_available(scope)
            env = environment(root, scope)
            env["PYTHONPATH"] = str(root / "runtime") + ":" + env["PYTHONPATH"]
            make_runtime_directories(root, env)
            with (root / "output/optimization.log").open("xb") as log:
                child = subprocess.Popen([sys.executable, "-m", MODULE, "worker", "--request", str(path)],
                    cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                write_json_exclusive(root / "output/started.json", {"pid": child.pid, "CPU_affinity": affinity, "request_sha256": sha256_file(path)})
                code = wait_bounded(child, scope["max_wall_seconds"], scope["memory_GB"])
            if code:
                raise RuntimeError("paired optimizer producer failed")
    except BaseException as exc:
        code, error = 1, type(exc).__name__ + ": " + str(exc)
    finally:
        stop_owned_group(child)
        write_json_exclusive(root / "output/controller_exit_record.json", {"exit_code": code, "error": error, "request_sha256": sha256_file(path)})


def launch(path):
    _, root, scope = verify(path, remote=True)
    gpu_available(scope)
    (root / "output").mkdir(exist_ok=False)
    write_json_exclusive(root / "launch_marker.json", {"request_sha256": sha256_file(path)})
    env = environment(root, scope)
    env["PYTHONPATH"] = str(root / "runtime") + ":" + env["PYTHONPATH"]
    make_runtime_directories(root, env)
    with (root / "output/controller.log").open("xb") as log:
        child = subprocess.Popen([sys.executable, "-m", MODULE, "controller", "--request", str(path)],
            cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    receipt = {"pid": child.pid, "request_sha256": sha256_file(path), "scheduler_job_id": None}
    write_json_exclusive(root / "launch_receipt.json", receipt)
    print(receipt, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "launch", "controller", "worker"])
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "preflight":
        _, root, scope = verify(args.request, remote=True)
        gpu_available(scope)
        from ase.optimize import LBFGS
        from archive.fe110_adsorption_validation_20261018.runtime import load_atoms
        if LBFGS.defaults["maxstep"] != 0.2:
            raise ValueError("optimizer default changed")
        for case in scope["cases"]:
            load_atoms(root / case["seed_path"])
        print({"status": "PASS_NATIVE_PAIRED_OPTIMIZATION_PREFLIGHT", "relaxations": 4, "CUDA_initialized": False}, flush=True)
    else:
        {"worker": worker, "controller": controller, "launch": launch}[args.action](args.request)
