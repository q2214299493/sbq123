"""One authorized sequential GPU training comparison,with no scheduler emulation or retry."""
import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.adsorption.direct_gpu_batch import environment, gpu_available, timestamp


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("path escapes training package")
    return path


def check_remote_root(root, exception):
    boundary = Path("/home/sbq/sbq").resolve()
    if (socket.gethostname() != "MZ73" or root != Path(exception["remote_root"]).resolve()
            or str(boundary) != exception["canonical_remote_boundary"] or not root.is_relative_to(boundary)):
        raise ValueError("host/root/canonical write boundary mismatch")


def verify(path, expected_sha, remote=False):
    if sha256_file(path) != expected_sha:
        raise ValueError("direct request changed")
    request = load_json_object(path)
    root = path.parent.resolve()
    if not re.fullmatch(r"direct-[a-z0-9-]+", request["run_id"]):
        raise ValueError("direct ID must not imitate a scheduler ID")
    policy = inside(root, request["policy"]["path"])
    if sha256_file(policy) != request["policy"]["sha256"]:
        raise ValueError("backend policy changed")
    exception = yaml.safe_load(policy.read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["direct_execution_exceptions"][request["exception_id"]]
    for key in ("remote_root", "gpu_index", "gpu_uuid", "max_wall_seconds", "per_arm_wall_seconds"):
        if request[key] != exception[key]:
            raise ValueError("execution scope changed: " + key)
    approval = load_json_object(root / "direct_authorization.json")
    if (approval.get("request_sha256") != expected_sha or approval.get("user_authorized") is not True
            or approval.get("action") != "RUN_GPU_ADSORPTION_TRAINING_COMPARISON_DIRECT"
            or approval.get("user_request") != exception["authorizing_user_request"]):
        raise ValueError("missing exact direct-training authorization")
    if request["execution_mode"] != "direct_no_scheduler" or request["scheduler_job_id"] is not None:
        raise ValueError("scheduler emulation forbidden")
    if request["arms"] != ["control", "treatment"] or request["original_comparison_sha256"] != exception["original_comparison_sha256"]:
        raise ValueError("comparison scope changed")
    for name, sha in exception["arm_request_sha256"].items():
        if sha256_file(root / name / "training_request.json") != sha:
            raise ValueError("frozen arm request changed")
    for item in request["artifacts"]:
        if sha256_file(inside(root, item["path"])) != item["sha256"]:
            raise ValueError("bound file changed: " + item["path"])
    if sha256_file(root / "comparison_request.json") != exception["original_comparison_sha256"]:
        raise ValueError("original comparison changed")
    if remote:
        check_remote_root(root, exception)
    return request, root, exception


def arm_environment(root, request, arm):
    env = environment(root, request)
    env["PYTHONPATH"] = str(root / arm / "runtime") + ":" + env["PYTHONPATH"]
    for key in tuple(env):
        if key.startswith("SLURM_"):
            env.pop(key)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", WANDB_MODE="disabled", MPLCONFIGDIR=str(root / "cache/matplotlib"),
               TORCH_EXTENSIONS_DIR=str(root / "cache/torch_extensions"))
    return env


def make_runtime_directories(root, env):
    for key in ("TMPDIR", "XDG_CACHE_HOME", "TORCH_HOME", "HF_HOME", "MPLCONFIGDIR", "TORCH_EXTENSIONS_DIR"):
        path = Path(env[key]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("runtime write directory escapes package")
        path.mkdir(parents=True, exist_ok=True)


def arm_command(path, sha, arm, action):
    return ["/home/sbq/sbq/ml_ts_acceleration/venv/bin/python", "-m", "scripts.adsorption.direct_training_arm", action,
            "--request", str(path), "--request-sha256", sha, "--arm", arm]


def preflight(path, sha):
    request, root, _ = verify(path, sha, remote=True)
    gpu_available(request)
    for arm in request["arms"]:
        env = arm_environment(root, request, arm)
        make_runtime_directories(root, env)
        with (root / ("preflight_" + arm + ".log")).open("xb") as log:
            subprocess.run(arm_command(path, sha, arm, "preflight"), env=env, cwd=root,
                           stdout=log, stderr=subprocess.STDOUT, timeout=300, check=True)
    print(json.dumps({"status": "PASS_DIRECT_PREFLIGHT_NO_MODEL", "request_sha256": sha}), flush=True)


def launch(path, sha):
    request, root, _ = verify(path, sha, remote=True)
    for arm in request["arms"]:
        receipt = load_json_object(root / ("preflight_" + arm + ".json"))
        if receipt["request_sha256"] != sha or receipt["status"] != "PASS_NATIVE_PACKAGE_CPU":
            raise ValueError("missing current on-disk native preflight")
    gpu_available(request)
    marker = {"run_id": request["run_id"], "request_sha256": sha, "created_at": timestamp()}
    write_json_exclusive(root / "direct_launch_marker.json", marker)
    env = arm_environment(root, request, "control")
    make_runtime_directories(root, env)
    with (root / "direct_controller.log").open("xb") as log:
        child = subprocess.Popen([sys.executable, "-m", "scripts.adsorption.direct_force_training", "run",
            "--request", str(path), "--request-sha256", sha], env=env, cwd=root,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    receipt = {**marker, "pid": child.pid, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None}
    write_json_exclusive(root / "direct_launch_receipt.json", receipt)
    print(json.dumps(receipt), flush=True)


def tree_rss(pid):
    """Read only this producer's descendant tree,not every user's processes."""
    pending, seen, total = [pid], set(), 0
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if len(seen) > 256:
            raise RuntimeError("unexpected producer process tree")
        try:
            status = Path(f"/proc/{current}/status").read_text()
            total += sum(int(line.split()[1])*1024 for line in status.splitlines() if line.startswith("VmRSS:"))
            pending.extend(int(p) for p in Path(f"/proc/{current}/task/{current}/children").read_text().split())
        except FileNotFoundError:
            continue
    return total


def stop_owned_group(child):
    if child is None or child.poll() is not None:
        return
    try:
        if os.getpgid(child.pid) != child.pid:
            raise RuntimeError("refuse to signal an unowned process group")
    except ProcessLookupError:
        return
    os.killpg(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=10)


def wait_bounded(child, seconds, memory_GB):
    deadline = time.monotonic() + seconds
    while child.poll() is None:
        if time.monotonic() >= deadline:
            raise TimeoutError("authorized arm/batch walltime exhausted")
        if tree_rss(child.pid) > memory_GB * 1024**3:
            raise MemoryError("producer RSS exceeds reviewed RAM budget")
        time.sleep(1)
    return child.returncode


def execute_arms(path, sha, request, root, exception, completed):
    child = None
    deadline = time.monotonic() + request["max_wall_seconds"]
    try:
        for arm in request["arms"]:
            gpu_available(request)
            output = root / arm / "output" / request["run_id"]
            output.mkdir(parents=True, exist_ok=False)
            started = timestamp()
            with (output / "training.log").open("xb") as log:
                child = subprocess.Popen(arm_command(path, sha, arm, "train"), env=arm_environment(root, request, arm),
                    cwd=output, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                write_json_exclusive(output / "started.json", {"arm": arm, "pid": child.pid, "started_at": started,
                    "request_sha256": sha, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None})
                try:
                    code = wait_bounded(child, min(request["per_arm_wall_seconds"], deadline-time.monotonic()), exception["memory_GB"])
                except BaseException as error:
                    stop_owned_group(child)
                    write_json_exclusive(output / "producer_exit_record.json", {"arm": arm, "exit_code": child.returncode,
                        "reason": str(error), "started_at": started, "finished_at": timestamp(), "request_sha256": sha,
                        "scheduler_job_id": None, "evidence_class": "producer_process_only_not_scheduler_state"})
                    raise
            write_json_exclusive(output / "producer_exit_record.json", {"arm": arm, "exit_code": code, "started_at": started,
                "finished_at": timestamp(), "request_sha256": sha, "scheduler_job_id": None,
                "evidence_class": "producer_process_only_not_scheduler_state"})
            child = None
            if code:
                raise RuntimeError(f"{arm} producer failed with exit {code};no retry or next arm")
            binding = load_json_object(output / "execution_device.json")
            finished = load_json_object(output / "training_completed.json")
            if binding["model_device"] != "cuda:0" or finished["optimizer_steps"] != exception["max_optimizer_steps_per_arm"]:
                raise RuntimeError("producer did not prove CUDA/full bounded training completion")
            if request.get("native_two_backward_check"):
                startup = load_json_object(output / "native_two_backward_check.json")
                if startup["status"] != "PASS_NATIVE_CUDA_TWO_BACKWARDS" or startup["request_sha256"] != sha:
                    raise RuntimeError("missing same-process consecutive native backward evidence")
            completed.append(arm)
            print(json.dumps({"arm_completed": arm, "optimizer_steps": finished["optimizer_steps"]}), flush=True)
    finally:
        stop_owned_group(child)


def run(path, sha):
    import fcntl
    request, root, exception = verify(path, sha, remote=True)
    marker = load_json_object(root / "direct_launch_marker.json")
    if marker["request_sha256"] != sha:
        raise ValueError("launch marker mismatch")
    started, completed, code, reason = timestamp(), [], 1, "startup"
    def interrupted(signum, _):
        raise InterruptedError("producer signal " + str(signum))
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    try:
        allowed = sorted(os.sched_getaffinity(0))[:exception["CPU_count"]]
        if len(allowed) != exception["CPU_count"]:
            raise RuntimeError("insufficient CPU affinity")
        os.sched_setaffinity(0, allowed)
        locks = Path("/home/sbq/sbq/aqcat25_ts_pilot/direct_gpu_locks")
        locks.mkdir(exist_ok=True)
        with (locks / (request["gpu_uuid"] + ".lock")).open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            gpu_available(request)
            write_json_exclusive(root / "direct_started.json", {"request_sha256": sha, "pid": os.getpid(),
                "started_at": started, "cpu_affinity": allowed, "scheduler_job_id": None})
            execute_arms(path, sha, request, root, exception, completed)
        code, reason = 0, "both bounded producers completed;scientific review pending"
    except BaseException as error:
        reason = type(error).__name__ + ": " + str(error)
        print(json.dumps({"error": reason}), flush=True)
    finally:
        write_json_exclusive(root / "direct_batch_exit_record.json", {"run_id": request["run_id"], "pid": os.getpid(),
            "request_sha256": sha, "started_at": started, "finished_at": timestamp(), "exit_code": code,
            "reason": reason, "completed_arms": completed, "scheduler_job_id": None,
            "evidence_class": "producer_process_only_not_scheduler_state", "checkpoint_promoted": False})
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "preflight", "launch", "run"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    if args.action == "verify":
        verify(args.request, args.request_sha256)
        print("PASS_LOCAL_EXACT_BINDING")
    elif args.action == "run":
        sys.exit(run(args.request, args.request_sha256))
    else:
        (preflight if args.action == "preflight" else launch)(args.request, args.request_sha256)


if __name__ == "__main__":
    main()
