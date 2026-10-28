"""One explicitly authorized two-arm sequence;reuse canonical FT execution."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.adsorption.direct_gpu_batch import gpu_available
from scripts.adsorption.direct_force_training import stop_owned_group, wait_bounded

BASE_PYTHON = "/home/sbq/sbq/ml_ts_acceleration/venv/bin/python"


def verify(path, digest):
    root = path.parent.resolve()
    if sha256_file(path) != digest:
        raise ValueError("sequence request changed")
    request = load_json_object(path)
    auth = load_json_object(root / "sequence_authorization.json")
    if auth.get("user_authorized") is not True or auth.get("request_sha256") != digest or auth.get("action") != "RUN_FE110_SCRATCH512_TWO_ARM_SEQUENCE":
        raise ValueError("current human two-arm authorization missing")
    if request["per_arm_seconds"] != 1800 or request["total_GPU_seconds"] != 3600 or request["arms"] != ["nequip_scratch", "aqcat25_finetune"]:
        raise ValueError("sequence budget or scope changed")
    for item in request["artifacts"]:
        target = (root / item["path"]).resolve()
        if not target.is_relative_to(root) or sha256_file(target) != item["sha256"]:
            raise ValueError("sequence artifact binding failed")
    if socket.gethostname() != "MZ73" or root != Path(request["remote_root"]).resolve() or not root.is_relative_to(Path("/home/sbq/sbq").resolve()):
        raise ValueError("native sequence host/root mismatch")
    return request, root


def environment(root, arm):
    env = os.environ.copy()
    package = root / ("nequip_v2" if arm == "nequip_scratch" else "finetune/control")
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4",
        WANDB_MODE="disabled", PYTHONPATH=str(package / "runtime") + ":/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor")
    return env


def arm_command(root, request, arm, action):
    if arm == "nequip_scratch":
        return [BASE_PYTHON, "-m", "scripts.adsorption.nequip_force_job", action, "--request",
            str(root / "nequip_v2/training_request.json"), "--sha256", request["nequip_request_sha256"]]
    return [BASE_PYTHON, "-m", "scripts.adsorption.direct_force_training", action, "--request",
        str(root / "finetune/direct_request.json"), "--request-sha256", request["finetune_direct_request_sha256"]]


def preflight(path, digest):
    request, root = verify(path, digest)
    gpu_available(request)
    for arm, action in [("nequip_scratch", "verify"), ("aqcat25_finetune", "preflight")]:
        with (root / (arm + "_preflight.log")).open("xb") as log:
            subprocess.run(arm_command(root, request, arm, action), cwd=root, env=environment(root, arm), stdout=log,
                stderr=subprocess.STDOUT, timeout=300, check=True)
    write_json_exclusive(root / "sequence_preflight.json", {"status": "PASS_NATIVE_CURRENT_REQUESTS", "request_sha256": digest, "GPU_training_started": False})


def run(path, digest):
    import fcntl
    request, root = verify(path, digest)
    affinity = sorted(os.sched_getaffinity(0))[:4]
    if len(affinity) != 4:
        raise ValueError("insufficient CPU affinity")
    os.sched_setaffinity(0, affinity)
    result = {"request_sha256": digest, "pid": os.getpid(), "started_utc": datetime.now(timezone.utc).isoformat(), "arms": {}, "checkpoint_promoted": False}
    child = None
    try:
        locks = Path("/home/sbq/sbq/aqcat25_ts_pilot/direct_gpu_locks")
        locks.mkdir(exist_ok=True)
        with (locks / (request["gpu_uuid"] + ".lock")).open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            gpu_available(request)
            with (root / "nequip_controller.log").open("xb") as log:
                child = subprocess.Popen(arm_command(root, request, "nequip_scratch", "run"), cwd=root,
                    env=environment(root, "nequip_scratch"), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                write_json_exclusive(root / "nequip_started.json", {"pid": child.pid, "request_sha256": request["nequip_request_sha256"], "CPU_affinity": affinity})
                try:
                    code = wait_bounded(child, 1800, 32)
                except (TimeoutError, MemoryError):
                    stop_owned_group(child)
                    code = 124
            result["arms"]["nequip_scratch"] = {"exit_code": code}
            write_json_exclusive(root / "nequip_stage_exit.json", result["arms"]["nequip_scratch"])
            child = None
        # Each arm has its own current exclusive gate;no retry on device conflict.
        gpu_available(request)
        with (root / "finetune_launch.log").open("xb") as log:
            subprocess.run(arm_command(root, request, "aqcat25_finetune", "launch"), cwd=root,
                env=environment(root, "aqcat25_finetune"), stdout=log, stderr=subprocess.STDOUT, timeout=45, check=True)
        receipt = root / "finetune/direct_batch_exit_record.json"
        deadline = time.monotonic() + 1840
        while not receipt.exists() and time.monotonic() < deadline:
            time.sleep(5)
        if not receipt.exists():
            raise RuntimeError("canonical FT completion receipt unavailable;do not relaunch")
        result["arms"]["aqcat25_finetune"] = load_json_object(receipt)
        result["exit_code"] = 0 if all(r["exit_code"] == 0 for r in result["arms"].values()) else 1
    except BaseException as exc:
        result.update(exit_code=1, error=str(exc))
    finally:
        stop_owned_group(child)
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json_exclusive(root / "sequence_exit.json", result)
    return result["exit_code"]


def launch(path, digest):
    request, root = verify(path, digest)
    if load_json_object(root / "sequence_preflight.json")["request_sha256"] != digest:
        raise ValueError("current native preflight required")
    gpu_available(request)
    write_json_exclusive(root / "sequence_launch_marker.json", {"request_sha256": digest})
    with (root / "sequence_controller.log").open("xb") as log:
        process = subprocess.Popen([sys.executable, str(root / "sequence_driver.py"), "run", "--request", str(path), "--sha256", digest],
            cwd=root, env=environment(root, "aqcat25_finetune"), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    result = {"request_sha256": digest, "pid": process.pid, "scheduler_job_id": None, "execution_mode": "direct_no_scheduler"}
    write_json_exclusive(root / "sequence_launch_receipt.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "launch", "run"])
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.action == "run":
        sys.exit(run(args.request, args.sha256))
    else:
        (preflight if args.action == "preflight" else launch)(args.request, args.sha256)
