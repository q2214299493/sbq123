"""Exact-hash,explicitly authorized native NequIP run;no automatic submission."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import subprocess

import yaml

from scripts.adsorption.direct_gpu_batch import gpu_available
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

MANIFEST_SHA = "ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee"


def child(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("artifact escapes request root")
    return path


def verify(path, expected_sha):
    root = path.parent.resolve()
    if sha256_file(path) != expected_sha:
        raise ValueError("request hash changed")
    request = load_json_object(path)
    if request["document_kind"] != "fe110_nequip_force_scratch_trial" or request["source_manifest_sha256"] != MANIFEST_SHA:
        raise ValueError("training source/scope changed")
    if request["counts"] != {"train": 512, "development": 78} or request["initialization"] != "random_no_checkpoint":
        raise ValueError("split or initialization changed")
    for item in request["artifacts"]:
        if sha256_file(child(root, item["path"])) != item["sha256"]:
            raise ValueError("bound artifact changed")
    cfg = yaml.safe_load(child(root, request["config_path"]).read_text(encoding="utf-8"))
    if cfg["run"] != ["train"] or any(k in cfg["data"] for k in ["test_dataset", "split_dataset", "predict_dataset"]):
        raise ValueError("heldout/random resplitting forbidden")
    for key, expected in [("max_epochs", 100), ("max_steps", 12800), ("max_time", "00:00:30:00"), ("accelerator", "gpu"), ("devices", 1)]:
        if cfg["trainer"][key] != expected:
            raise ValueError("native training limit changed")
    if request["max_wall_seconds"] != 1800 or request["GPU_count"] != 1 or request["automatic_retries"] != 0:
        raise ValueError("request resource budget changed")
    return request, root


def execute(path, expected_sha):
    request, root = verify(path, expected_sha)
    auth = load_json_object(root / "authorization.json")
    policy_path = root / "execution_backends.yaml"
    if (not auth.get("user_authorized") or auth.get("action") != "RUN_GPU_FE110_NEQUIP_SCRATCH"
            or auth.get("request_sha256") != expected_sha or auth.get("policy_sha256") != sha256_file(policy_path)):
        raise ValueError("fresh exact-hash human authorization required")
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    exception = policy["backends"]["aqcat_gpu"]["direct_execution_exceptions"]["fe110_nequip_scratch512_20261028"]
    if exception["request_sha256"] != expected_sha or exception["max_wall_seconds"] != 1800 or exception["model_backend"] != "nequip_force_scratch":
        raise ValueError("canonical scoped execution exception changed")
    boundary = Path("/home/sbq/sbq").resolve()
    if socket.gethostname() != "MZ73" or root != Path(request["remote_root"]).resolve() or not root.is_relative_to(boundary):
        raise ValueError("native host/write boundary changed")
    gpu_available(request)
    output = root / "output"
    output.mkdir(exist_ok=False)
    environment = os.environ.copy()
    environment.update(CUDA_VISIBLE_DEVICES=request["gpu_uuid"], OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4",
        PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1", PYTHONUTF8="1", WANDB_MODE="disabled",
        FE110_NEQUIP_REQUEST_SHA256=expected_sha, PYTHONPATH=str(root / "runtime"),
        XDG_CACHE_HOME=str(output / "cache"), MPLCONFIGDIR=str(output / "cache/matplotlib"))
    command = [request["entrypoint"], "-cp", str(root), "-cn", request["config_path"]]
    code, started = None, datetime.now(timezone.utc).isoformat()
    with (root / "training.log").open("xb") as log:
        try:
            code = subprocess.run(command, env=environment, cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=False).returncode
        except subprocess.TimeoutExpired:
            code = 124
        finally:
            write_json_exclusive(root / "producer_exit_record.json", {"exit_code": code, "request_sha256": expected_sha,
                "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "evidence_class": "producer_not_scheduler",
                "checkpoint_promoted": False, "scientific_acceptance": False, "acceleration_proved": False})
    if code:
        raise RuntimeError("bounded native training failed or exhausted time;no automatic retry")
    if not (output / "best.ckpt").is_file() or not (output / "model_device.json").is_file():
        raise ValueError("missing native checkpoint or actual CUDA binding")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["verify", "run"])
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.action == "verify":
        verify(args.request, args.sha256)
    else:
        execute(args.request, args.sha256)


if __name__ == "__main__":
    main()
