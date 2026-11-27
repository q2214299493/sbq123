"""One hash-bound fixed-reserved-set force comparison;no fitting or relaxation."""
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

from scripts.adsorption.direct_gpu_batch import cuda_binding, environment, gpu_available
from scripts.adsorption.direct_force_training import make_runtime_directories, stop_owned_group, wait_bounded
from scripts.adsorption.force_finetune import load_manifest, local_path
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

MODELS = {"baseline", "control", "new512"}
MODULE = "scripts.adsorption.fixed_force_comparison"


def validate_scope(request, approval, exception, digest):
    if approval.get("user_authorized") is not True or approval.get("request_sha256") != digest or approval.get("action") != "RUN_FROZEN_FORCE_COMPARISON":
        raise ValueError("missing exact force-comparison authorization")
    for key in ["remote_root", "gpu_index", "gpu_uuid", "gpu_sharing", "max_wall_seconds", "sample_ids", "model_checkpoint_sha256"]:
        if request[key] != exception[key]:
            raise ValueError("comparison scope changed: " + key)
    if request["models"].keys() != MODELS or {k: v["sha256"] for k, v in request["models"].items()} != request["model_checkpoint_sha256"]:
        raise ValueError("frozen checkpoint set changed")
    if request["execution_mode"] != "direct_no_scheduler" or request["scheduler_job_id"] is not None:
        raise ValueError("scheduler emulation forbidden")
    if approval["user_request"] != exception["authorizing_user_request"] or request["prediction_count"] != 159:
        raise ValueError("human scope or prediction budget changed")
    if request["scientific_boundaries"] != {"training": False, "relaxation": False, "model_reselection": False, "model_promotion": False}:
        raise ValueError("fixed force comparison cannot train,optimize or reselect")


def verify(path, remote=False):
    root = path.parent.resolve()
    request = load_json_object(path)
    approval = load_json_object(root / "authorization.json")
    policy = local_path(root, request["policy"]["path"])
    if sha256_file(policy) != request["policy"]["sha256"]:
        raise ValueError("comparison policy changed")
    exception = yaml.safe_load(policy.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["direct_execution_exceptions"][request["exception_id"]]
    validate_scope(request, approval, exception, sha256_file(path))
    for artifact in request["artifacts"]:
        if sha256_file(local_path(root, artifact["path"])) != artifact["sha256"]:
            raise ValueError("comparison artifact changed")
    manifest_path = root / "data/training_manifest.json"
    if sha256_file(manifest_path) != request["training_manifest_sha256"]:
        raise ValueError("frozen training manifest changed")
    manifest = load_manifest(manifest_path)
    rows = manifest["splits"]["heldout"]
    if len(rows) != 53 or [r["sample_id"] for r in rows] != request["sample_ids"]:
        raise ValueError("fixed reserved set changed")
    frozen = load_json_object(root / "evidence/candidate_summary.json")
    if frozen["candidate_sha256"] != request["models"]["new512"]["sha256"] or frozen["heldout_inference_run"] is not False:
        raise ValueError("candidate was not frozen before this comparison")
    if remote:
        boundary = Path("/home/sbq/sbq").resolve()
        if socket.gethostname() != "MZ73" or root != Path(request["remote_root"]).resolve() or str(boundary) != exception["canonical_remote_boundary"] or not root.is_relative_to(boundary):
            raise ValueError("unauthorized comparison host/root")
        for model in request["models"].values():
            if not Path(model["path"]).resolve().is_relative_to(boundary) or sha256_file(Path(model["path"])) != model["sha256"]:
                raise ValueError("remote frozen checkpoint changed")
    return request, root, rows


def worker(path):
    request, root, rows = verify(path, remote=True)
    output = root / "output"
    started = datetime.now(timezone.utc).isoformat()
    code, error = 1, None
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != request["gpu_uuid"]:
            raise ValueError("physical CUDA device not bound")
        gpu_available(request)
        import torch
        from fairchem.core.common.relaxation.ase_utils import patched_calc
        from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401
        from archive.fe110_adsorption_validation_20261018.runtime import predict_heldout
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(request["gpu_sharing"]["max_training_memory_MiB"] * 1024**2 / total, device=0)
        deadline = time.monotonic() + request["max_wall_seconds"]
        for name, model in request["models"].items():
            calc = patched_calc(checkpoint_path=model["path"], is_spin_off=False, is_low_fi=False, cpu=False)
            write_json_exclusive(output / (name + "_device.json"), cuda_binding(calc))
            predictions = predict_heldout(root / "data", rows, calc, deadline)
            write_json_exclusive(output / (name + "_forces.json"), {"checkpoint_sha256": model["sha256"], "samples": predictions})
            del calc
            gc.collect()
            torch.cuda.empty_cache()
        code = 0
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        write_json_exclusive(output / "producer_exit_record.json", {"exit_code": code, "error": error,
            "request_sha256": sha256_file(path), "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(), "training_performed": False, "geometry_optimized": False, "model_reselected": False,
            "heldout_frames": 53, "prediction_count": 159, "scheduler_job_id": None})


def controller(path):
    import fcntl
    request, root, _ = verify(path, remote=True)
    child, code, error = None, 1, None
    output = root / "output"
    def interrupted(signum, _):
        raise InterruptedError("comparison signal " + str(signum))
    for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP]:
        signal.signal(sig, interrupted)
    try:
        affinity = sorted(os.sched_getaffinity(0))[:4]
        os.sched_setaffinity(0, affinity)
        locks = Path("/home/sbq/sbq/aqcat25_ts_pilot/direct_gpu_locks")
        locks.mkdir(exist_ok=True)
        with (locks / (request["gpu_uuid"] + ".lock")).open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            gpu_available(request)
            env = environment(root, request)
            env["PYTHONPATH"] = str(root / "runtime") + ":" + env["PYTHONPATH"]
            make_runtime_directories(root, env)
            with (output / "prediction.log").open("xb") as log:
                child = subprocess.Popen([sys.executable, "-m", MODULE, "worker", "--request", str(path)],
                    env=env, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                write_json_exclusive(output / "started.json", {"pid": child.pid, "request_sha256": sha256_file(path), "CPU_affinity": affinity})
                code = wait_bounded(child, request["max_wall_seconds"], 32)
            if code:
                raise RuntimeError("fixed comparison producer failed")
    except BaseException as exc:
        code, error = 1, type(exc).__name__ + ": " + str(exc)
    finally:
        stop_owned_group(child)
        write_json_exclusive(output / "controller_exit_record.json", {"exit_code": code, "error": error,
            "request_sha256": sha256_file(path), "scheduler_job_id": None, "finished_at": datetime.now(timezone.utc).isoformat()})


def launch(path):
    request, root, _ = verify(path, remote=True)
    gpu_available(request)
    output = root / "output"
    output.mkdir(exist_ok=False)
    write_json_exclusive(root / "launch_marker.json", {"request_sha256": sha256_file(path)})
    env = environment(root, request)
    env["PYTHONPATH"] = str(root / "runtime") + ":" + env["PYTHONPATH"]
    make_runtime_directories(root, env)
    with (output / "controller.log").open("xb") as log:
        child = subprocess.Popen([sys.executable, "-m", MODULE, "controller", "--request", str(path)],
            env=env, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    receipt = {"request_sha256": sha256_file(path), "pid": child.pid, "scheduler_job_id": None}
    write_json_exclusive(root / "launch_receipt.json", receipt)
    print(receipt, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "launch", "controller", "worker"])
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "preflight":
        request, _, rows = verify(args.request, remote=True)
        gpu_available(request)
        print({"status": "PASS_FROZEN53_THREE_MODEL_PREFLIGHT", "frames": len(rows), "predictions": 159}, flush=True)
    else:
        {"launch": launch, "controller": controller, "worker": worker}[args.action](args.request)
