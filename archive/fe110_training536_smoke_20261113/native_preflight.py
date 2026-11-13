"""CPU-only package/CLI/checkpoint/parameter checks; no forward or optimization."""
from __future__ import annotations

import argparse
import copy
import inspect
import os
import resource
import socket
import time
from collections import defaultdict
from pathlib import Path

import yaml

from scripts.adsorption.force_training_preflight import check_native_cli, verify_training_package
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    contract = load_json_object(args.contract)
    if (socket.gethostname() != contract["hostname"] or os.environ.get("CUDA_VISIBLE_DEVICES") != "-1"
            or contract["training_authorized"] or contract["forward_backward_optimizer_allowed"]):
        raise ValueError("CPU-only preflight boundary changed")
    root = args.contract.parent.resolve()
    if str(root) != str(Path(contract["remote_root"]).resolve()) or not root.is_relative_to(Path("/home/sbq/sbq").resolve()):
        raise ValueError("preflight path escaped fresh package")
    if (args.output.exists() or not args.output.resolve().is_relative_to(root)
            or sha256_file(args.request) != contract["training_request_sha256"]):
        raise ValueError("output already exists, escapes package, or request changed")
    resource.setrlimit(resource.RLIMIT_AS, (contract["memory_GB"] * 1024**3,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (contract["max_seconds"], contract["max_seconds"] + 5))
    affinity = sorted(os.sched_getaffinity(0))[:contract["CPU_count"]]
    os.sched_setaffinity(0, affinity)
    import torch
    from fairchem.core.common.registry import registry
    from fairchem.core.common.utils import load_state_dict, match_state_dict, setup_imports

    torch.set_num_threads(contract["CPU_count"])
    torch.set_grad_enabled(False)
    if torch.cuda.is_initialized():
        raise RuntimeError("unexpected CUDA initialization")
    verdict = verify_training_package(args.request)
    cli = check_native_cli(args.request.parent)
    request = load_json_object(args.request)
    config = yaml.safe_load((args.request.parent / request["config_path"]).read_text(encoding="utf-8"))
    checkpoint = Path(request["base_checkpoint"]["path"])
    checkpoint_before = sha256_file(checkpoint)
    if checkpoint_before != request["base_checkpoint"]["sha256"]:
        raise ValueError("pretrained checkpoint changed")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if payload["config"]["model"] != config["model"]:
        raise ValueError("native checkpoint architecture differs from bound config")
    setup_imports()
    model_config = copy.deepcopy(config["model"])
    model_class = registry.get_model_class(model_config.pop("name"))
    model = model_class(**model_config)
    matched = match_state_dict(model.state_dict(), payload["state_dict"])
    missing, unexpected = load_state_dict(model, matched, strict=True)
    if missing or unexpected:
        raise ValueError("native strict checkpoint load mismatch")
    model.eval()  # No forward/backward, trainer, optimizer, scheduler or checkpoint writer is invoked.
    parameters, groups = [], defaultdict(lambda: {"tensors": 0, "trainable_numel": 0, "frozen_numel": 0})
    for name, value in model.named_parameters():
        if value.device.type != "cpu" or not bool(torch.isfinite(value).all()):
            raise ValueError("non-CPU or nonfinite parameter")
        group = "backbone" if name.startswith("backbone.") else ".".join(name.split(".")[:2])
        item = {"name": name, "shape": list(value.shape), "numel": value.numel(),
                "requires_grad": value.requires_grad, "dtype": str(value.dtype), "device": str(value.device)}
        parameters.append(item)
        groups[group]["tensors"] += 1
        groups[group]["trainable_numel" if value.requires_grad else "frozen_numel"] += value.numel()
    if not parameters or torch.cuda.is_initialized() or sha256_file(checkpoint) != checkpoint_before:
        raise ValueError("empty model, CUDA initialized, or original checkpoint mutated")
    if time.monotonic() - started > contract["max_seconds"]:
        raise TimeoutError("bounded CPU preflight exceeded walltime")
    args.output.mkdir()
    write_json_exclusive(args.output / "parameters.json", {
        "request_sha256": contract["training_request_sha256"], "checkpoint_sha256": checkpoint_before,
        "model_source": inspect.getfile(model_class), "configured_freeze_backbone": model_config.get("freeze_backbone", False),
        "parameters": parameters, "groups": dict(groups), "no_forward_backward_or_optimizer": True})
    sources = [args.request, args.contract, checkpoint, Path(inspect.getfile(model_class)),
               Path(inspect.getfile(type(model.backbone))), Path(inspect.getfile(load_state_dict)),
               Path(inspect.getfile(type(model))) , Path(__file__), args.output / "parameters.json"]
    write_json_exclusive(args.output / "native_preflight.json", {
        "status": "PASS_NATIVE_CPU_PACKAGE_CLI_CHECKPOINT_PARAMETERS_NO_TRAINING",
        "request_sha256": contract["training_request_sha256"], "package_verdict": verdict, "native_cli": cli,
        "checkpoint_sha256_before": checkpoint_before, "checkpoint_sha256_after": sha256_file(checkpoint),
        "strict_checkpoint_load": True, "model_instantiated_on": "cpu", "CUDA_initialized": False,
        "parameter_tensors": len(parameters), "trainable_numel": sum(p["numel"] for p in parameters if p["requires_grad"]),
        "frozen_numel": sum(p["numel"] for p in parameters if not p["requires_grad"]), "groups": dict(groups),
        "configured_freeze_backbone": model_config.get("freeze_backbone", False),
        "energy_head_loss_coefficient": 0, "energy_head_zero_graph_link_is_not_energy_training": True,
        "parameter_requires_grad_is_not_measured_gradient_or_optimizer_update": True,
        "CPU_affinity": affinity, "peak_RSS_kB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "elapsed_seconds": time.monotonic() - started, "torch_version": torch.__version__,
        "forward_calls": 0, "backward_calls": 0, "optimizer_instances_or_steps": 0,
        "trained_model_or_warmstart_written": False, "heldout_inference_or_loader_created": False,
        "training_authorized": False, "GPU_resources_or_training_preflight_passed": False,
        "source_files": source_file_manifest(sources)})
    print({"status": "PASS_NATIVE_CPU_ONLY", "trainable_parameters": sum(p["numel"] for p in parameters if p["requires_grad"]),
           "frozen_parameters": sum(p["numel"] for p in parameters if not p["requires_grad"]),
           "elapsed_seconds": time.monotonic() - started, "CUDA_initialized": False}, flush=True)


if __name__ == "__main__":
    main()
