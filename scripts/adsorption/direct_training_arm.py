"""Bound native Fairchem training entry; adds CUDA/budget assertions,not a new loss or model."""
import argparse
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

import yaml

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.adsorption.direct_force_training import verify
from scripts.adsorption.force_finetune import warm_start
from scripts.adsorption.force_training_preflight import check_native_cli, verify_training_package


def install_cuda_guard(request, output, exception):
    import torch
    from scripts.adsorption.role_force_trainer import RoleForceTrainer
    original = RoleForceTrainer.train
    def checked_train(self, *args, **kwargs):
        parameters = list(self.model.parameters())
        if (not parameters or any(p.device.type != "cuda" or p.device.index != 0 for p in parameters)
                or not torch.cuda.is_available() or torch.cuda.device_count() != 1
                or os.environ.get("CUDA_VISIBLE_DEVICES") != request["gpu_uuid"]):
            raise RuntimeError("native force model is not on the one authorized CUDA device;no CPU fallback")
        if self.step != 0 or self.config["optim"]["max_epochs"] != exception["max_epochs"] or len(self.train_loader)*exception["max_epochs"] != exception["max_optimizer_steps_per_arm"]:
            raise RuntimeError("native trainer reset/epoch/step budget mismatch")
        write_json_exclusive(output / "execution_device.json", {"model_device": str(parameters[0].device),
            "physical_gpu_uuid": request["gpu_uuid"], "pid": os.getpid(), "scheduler_job_id": None,
            "actual_model_parameters_cuda": True, "execution_mode": "direct_no_scheduler"})
        result = original(self, *args, **kwargs)
        write_json_exclusive(output / "training_completed.json", {"optimizer_steps": int(self.step),
            "max_epochs": exception["max_epochs"], "heldout_used": False, "checkpoint_promoted": False})
        return result
    RoleForceTrainer.train = checked_train


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "train"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--arm", choices=("control", "treatment"), required=True)
    args = parser.parse_args()
    request, root, exception = verify(args.request, args.request_sha256, remote=True)
    arm = root / args.arm
    request_path = arm / "training_request.json"
    if args.action == "preflight":
        import torch
        verdict = verify_training_package(request_path)
        native = check_native_cli(arm)
        original = json.loads(request_path.read_text(encoding="utf-8"))
        checkpoint = Path(original["base_checkpoint"]["path"])
        if sha256_file(checkpoint) != original["base_checkpoint"]["sha256"]:
            raise ValueError("base checkpoint changed")
        payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
        config = yaml.safe_load((arm / "config.yml").read_text(encoding="utf-8"))
        if payload["config"]["model"] != config["model"]:
            raise ValueError("checkpoint architecture differs from frozen config")
        write_json_exclusive(root / ("preflight_" + args.arm + ".json"), {"status": "PASS_NATIVE_PACKAGE_CPU",
            "request_sha256": args.request_sha256, "arm": args.arm, "label_verdict": verdict, "native_CLI": native,
            "model_instantiated": False, "CUDA_initialized": torch.cuda.is_initialized()})
        return
    output = arm / "output" / request["run_id"]
    warm = output / "warmstart.pt"
    warm_start(request_path, arm / "direct_arm_authorization.json", warm)
    install_cuda_guard(request, output, exception)
    os.chdir(output)
    sys.argv = ["fairchem.core._cli", "--checkpoint", str(warm), "--mode", "train",
                "--config-yml", str(arm / "config.yml"), "--seed", "42", "--amp"]
    runpy.run_module("fairchem.core._cli", run_name="__main__")
    candidates = list(output.rglob("best_checkpoint.pt"))
    if len(candidates) != 1:
        raise RuntimeError("one development-selected checkpoint required;no last-checkpoint fallback")
    with candidates[0].open("rb") as source, (output / "candidate.pt").open("xb") as target:
        shutil.copyfileobj(source, target)


if __name__ == "__main__":
    main()
