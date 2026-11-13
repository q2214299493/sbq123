"""Run one authorized 536-frame trial after checks inside its Slurm allocation."""
from __future__ import annotations

import argparse
import csv
import os
import runpy
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


def validate_contract(contract, request, config, authorization):
    if contract["user_instruction"] != authorization.get("user_request"):
        raise ValueError("user instruction binding changed")
    if (authorization.get("user_authorized") is not True
            or authorization.get("action") != "RUN_GPU_ADSORPTION_SMALL_FINETUNE"
            or authorization.get("request_sha256") != contract["training_request_sha256"]):
        raise ValueError("missing exact trial authorization")
    if request["split_counts"] != {"train": 536, "development": 78, "heldout": 53}:
        raise ValueError("frozen split scope changed")
    required = {"epochs": 2, "learning_rate": 1e-5, "seed": 42, "batch_size": 1,
                "GPU_count": 1, "CPU_count": 4, "memory_GB": 32,
                "walltime_minutes": 30, "max_optimizer_steps": 1072, "unattended_retries": 0}
    if any(request["training_limits"].get(k) != value for k, value in required.items()):
        raise ValueError("authorized trial budget changed")
    losses = {k: v for item in config["loss_functions"] for k, v in item.items()}
    if (set(config["dataset"]) != {"train", "val"} or config["optim"]["lr_initial"] != 1e-5
            or config["optim"]["max_epochs"] != 2 or config["optim"]["batch_size"] != 1
            or losses["energy"]["coefficient"] != 0 or losses["forces"]["coefficient"] != 1):
        raise ValueError("training objective/configuration changed")
    if (contract["scheduler_seconds"] != 1740 or contract["scheduler_killwait_seconds"] > 30
            or contract["scheduler_seconds"] + contract["scheduler_killwait_seconds"] > 1800
            or contract["watchdog_seconds"] != 1700 or contract["watchdog_kill_after_seconds"] != 10):
        raise ValueError("inclusive single-GPU walltime bound changed")


def gpu_snapshot(assigned):
    if not assigned or "," in assigned or not (assigned.isdigit() or assigned.startswith("GPU-")):
        raise ValueError("one explicit Slurm GPU assignment required")
    # Device cgroups can renumber the allocated card inside the job. Bind its
    # physical UUID rather than treating SLURM_JOB_GPUS as an NVML index.
    try:
        query = subprocess.check_output([
            "nvidia-smi", "--query-gpu=index,uuid,name,memory.total,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits"], text=True, timeout=15)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"allocated NVML enumeration failed ({error.returncode}): {error.output[:500]}") from error
    rows = list(csv.reader(query.strip().splitlines(), skipinitialspace=True))
    if not rows or any(len(row) != 6 for row in rows):
        raise RuntimeError("incomplete assigned-GPU NVML snapshot")
    selected = rows if len(rows) == 1 else [row for row in rows if assigned in (row[0], row[1])]
    if len(selected) != 1:
        raise RuntimeError("cannot identify exactly one scheduler-assigned visible GPU")
    index, uuid, model, total, free, utilization = selected[0]
    processes = subprocess.check_output([
        "nvidia-smi", "-i", uuid, "--query-compute-apps=pid,gpu_uuid",
        "--format=csv,noheader,nounits"], text=True, timeout=15).strip()
    if processes or int(free) < 20000 or int(utilization) > 5:
        raise RuntimeError("assigned GPU is occupied or has insufficient free memory")
    return {"index": int(index), "uuid": uuid, "model": model,
            "Slurm_global_assignment": assigned, "NVML_visible_devices": len(rows),
            "total_MiB": int(total), "free_MiB": int(free), "utilization_percent": int(utilization),
            "compute_processes_before_CUDA": []}


def install_guards(output, request_sha, gpu, job_id):
    from scripts.adsorption.direct_training_arm import install_two_backward_guard
    from scripts.adsorption.role_force_trainer import RoleForceTrainer

    install_two_backward_guard(RoleForceTrainer, {"_request_sha256": request_sha}, output)
    original = RoleForceTrainer.train

    def checked_train(self, *args, **kwargs):
        parameters = list(self.model.parameters())
        if not parameters or any(p.device.type != "cuda" or p.device.index != 0 for p in parameters):
            raise RuntimeError("model is not entirely on the allocated CUDA device")
        if self.step != 0 or self.config["optim"]["max_epochs"] != 2 or len(self.train_loader) != 536:
            raise RuntimeError("native reset/data/iteration scope changed")
        write_json_exclusive(output / "execution_device.json", {
            "scheduler_job_id": job_id, "execution_mode": "Slurm", "physical_gpu_uuid": gpu["uuid"],
            "model_device": str(parameters[0].device), "all_model_parameters_cuda": True,
            "training_request_sha256": request_sha, "pid": os.getpid()})
        result = original(self, *args, **kwargs)
        if int(self.step) != 1072:
            raise RuntimeError("two-epoch native iteration budget was not completed")
        write_json_exclusive(output / "training_completed.json", {
            "native_iterations": int(self.step), "actual_optimizer_updates": self._direct_optimizer_updates,
            "epochs": 2, "scheduler_job_id": job_id, "heldout_used": False, "model_promoted": False})
        return result

    RoleForceTrainer.train = checked_train


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    args = parser.parse_args()
    if sha256_file(args.contract) != args.contract_sha256:
        raise ValueError("execution contract changed")
    contract = load_json_object(args.contract)
    root = args.contract.parent.resolve()
    boundary = Path("/home/sbq/sbq").resolve()
    if socket.gethostname() != "MZ73" or not root.is_relative_to(boundary):
        raise ValueError("execution host/write boundary changed")
    for item in contract["execution_files"]:
        source = root / item["path"]
        if not source.resolve().is_relative_to(root) or sha256_file(source) != item["sha256"]:
            raise ValueError("bound execution source changed")
    policy = yaml.safe_load((root / "execution_backends.yaml").read_text(encoding="utf-8"))
    backend = policy["backends"]["aqcat_gpu"]
    if backend["scheduler"]["type"] != "Slurm" or "force_only_fine_tuning" not in backend["allowed"]:
        raise ValueError("backend does not authorize the native Slurm force-training route")
    job_id = os.environ.get("SLURM_JOB_ID", "")
    if not job_id.isdigit():
        raise ValueError("native Slurm allocation required")
    output = Path(os.environ["RUN_ROOT"]).resolve()
    if not output.is_relative_to(root):
        raise ValueError("output escapes separate execution directory")
    package = Path(contract["package_root"])
    request_path = package / "training_request.json"
    if sha256_file(request_path) != contract["training_request_sha256"]:
        raise ValueError("frozen prepared request changed")
    request = load_json_object(request_path)
    config = yaml.safe_load((package / "config.yml").read_text(encoding="utf-8"))
    validate_contract(contract, request, config, load_json_object(root / "training_authorization.json"))
    started = time.monotonic()
    from scripts.adsorption.force_finetune import warm_start
    from scripts.adsorption.force_training_preflight import check_native_cli, verify_training_package

    package_check = verify_training_package(request_path)
    cli_check = check_native_cli(package)
    gpu = gpu_snapshot(os.environ.get("SLURM_JOB_GPUS", os.environ.get("CUDA_VISIBLE_DEVICES", "")))
    # Bind by the scheduler-assigned physical UUID before initializing CUDA.
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu["uuid"]
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("allocated CUDA device unavailable; no training fallback")
    if float(torch.ones(8, device="cuda:0").sum().item()) != 8:
        raise RuntimeError("allocated CUDA kernel check failed")
    write_json_exclusive(output / "allocation_preflight.json", {
        "status": "PASS_ALLOCATED_GPU_NATIVE_PACKAGE_CLI_CUDA", "scheduler_job_id": job_id,
        "gpu": gpu, "package": package_check, "native_cli": cli_check,
        "CUDA_version": torch.version.cuda, "torch_version": torch.__version__,
        "training_request_sha256": contract["training_request_sha256"],
        "preflight_elapsed_seconds": time.monotonic() - started})
    warm = output / "warmstart.pt"
    warm_start(request_path, root / "training_authorization.json", warm)
    install_guards(output, contract["training_request_sha256"], gpu, job_id)
    os.chdir(output)
    sys.argv = ["fairchem.core._cli", "--checkpoint", str(warm), "--mode", "train",
                "--config-yml", str(package / "config.yml"), "--seed", "42", "--amp"]
    runpy.run_module("fairchem.core._cli", run_name="__main__")
    # Native CLI flags can anchor checkpoints at the execution root before the
    # later chdir. Both locations remain inside this separately bound run.
    candidates = list(root.rglob("best_checkpoint.pt"))
    if len(candidates) != 1:
        raise RuntimeError("one development-selected best checkpoint required")
    with candidates[0].open("rb") as source, (output / "candidate.pt").open("xb") as target:
        shutil.copyfileobj(source, target)
    write_json_exclusive(output / "candidate_binding.json", {
        "candidate_sha256": sha256_file(output / "candidate.pt"),
        "native_best_sha256": sha256_file(candidates[0]), "native_best_path": str(candidates[0]),
        "training_request_sha256": contract["training_request_sha256"],
        "scheduler_job_id": job_id, "heldout_used": False, "scientific_acceptance": False,
        "model_promoted": False})


if __name__ == "__main__":
    main()
