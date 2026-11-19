"""Bound BUCT2 CPU preflight and one native, observed force-only training arm."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import inspect
import json
import os
from pathlib import Path
import runpy
import shutil
import socket
import sys
import time

import yaml

from scripts.artifact_io import load_json_object as load, sha256_file as sha, write_json_exclusive as save
from scripts.adsorption.force_finetune import validate_database_metadata
from scripts.adsorption.force_training_preflight import check_budget
from allocation_owner import gpu_snapshot

ROOT = Path("/home/sbq/sbq/force536_545_comparison_20261119_v1")
PAYLOAD = ROOT / "payload"
RUNTIME = Path("/home/sbq/sbq/compute_pool_20261117/deployed/runtime/python")
COUNTS = {"control536": 536, "increment545": 545}


def checked_contract(expected):
    path = PAYLOAD / "contract.json"
    if sha(path) != expected or socket.gethostname() != "pc-G7466-M6" or ROOT.resolve() != ROOT:
        raise ValueError("Approved request or host changed")
    contract = load(path)
    approval = load(PAYLOAD / "user_authorization.json")
    if (
        approval.get("user_authorized") is not True
        or approval.get("action") != "RUN_GPU_ADSORPTION_SMALL_FINETUNE"
        or approval.get("arms") != COUNTS
        or approval.get("backend") != "buct2_gpu"
    ):
        raise PermissionError("The two-arm authorization is missing")
    if sha(ROOT / "frozen536.pt") != contract["checkpoint_sha256"] or sha(RUNTIME) != contract["runtime_sha256"]:
        raise ValueError("Runtime or frozen initialization changed")
    for name, expected_hash in contract["files"].items():
        target = (PAYLOAD / name).resolve()
        if not target.is_relative_to(PAYLOAD) or sha(target) != expected_hash:
            raise ValueError(f"Staged input changed: {name}")
    return contract


def config_for(arm, contract):
    config_path = PAYLOAD / f"{arm}.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    limits = contract["arms"][arm]["limits"]
    check_budget({"training_limits": limits, "split_counts": {"train": COUNTS[arm], "development": 78, "heldout": 53}}, config)
    losses = {name: values["coefficient"] for loss in config["loss_functions"] for name, values in loss.items()}
    if (
        losses != {"energy": 0.0, "forces": 1.0}
        or config["optim"]["lr_initial"] != 1e-5
        or config["seed"] != 42
        or config["optim"]["max_epochs"] != 2
        or config["evaluation_metrics"]["primary_metric"] != "forces_role_vector_mae"
    ):
        raise ValueError("Reviewed loss, optimizer or development selection changed")
    return config, config_path


def native_argv(config_path):
    return ["--checkpoint", str(ROOT / "warmstart.pt"), "--mode", "train", "--config-yml", str(config_path), "--seed", "42", "--amp"]


def replay(config, arm, contract):
    import numpy as np
    from ase.db import connect
    from fairchem.core.datasets.base_dataset import create_dataset
    from scripts.adsorption.force_role_runtime import RoleBatchSampler

    count = COUNTS[arm]
    paths = config["dataset"]
    raw_rows = {}
    for key, size in (("train", count), ("val", 78)):
        database, metadata = Path(paths[key]["src"]), Path(paths[key]["metadata_path"])
        if validate_database_metadata(database, metadata)["rows"] != size:
            raise ValueError("Wrong train/development row count")
        raw_rows[key] = [r.data.sid for r in connect(database).select()]
    dataset = create_dataset(paths["train"], "train")
    indices = [int(i) for i in dataset.indices]
    if sorted(indices) != list(range(count)) or len(set(raw_rows["train"])) != count:
        raise ValueError("Native training row index mapping changed")
    probabilities = dataset.get_metadata("adsorption_sampling_probability", np.arange(count))
    if not np.all(probabilities == 1 / count):
        raise ValueError("Non-uniform training weight")
    sampler = RoleBatchSampler(probabilities, 1, 42)
    trace = []
    for epoch in range(2):
        sampler.set_epoch(epoch)
        trace.append([raw_rows["train"][indices[i]] for (i,) in sampler])
    new_ids = contract["arms"][arm]["new_ids"]
    for epoch in trace:
        if len(epoch) != count or Counter(sid for sid in epoch if sid in new_ids) != {sid: 1 for sid in new_ids}:
            raise ValueError("Native replay missed a newly labeled frame")
    # Exercise the actual ASE -> graph -> collated string identity path without a model call.
    from torch_geometric.data import Batch

    assert extract_sid(Batch.from_data_list([dataset[0]])) == raw_rows["train"][indices[0]]
    val = create_dataset(paths["val"], "val")
    val_ids = [raw_rows["val"][i] for i in val.indices]
    if len(val_ids) != 78 or len(set(val_ids)) != 78:
        raise ValueError("Development membership changed")
    return trace, val_ids


def preflight(contract, expected):
    import torch
    from fairchem.core.common.flags import flags
    from fairchem.core.common.registry import registry
    from fairchem.core.common.utils import build_config, load_state_dict, match_state_dict, setup_imports

    torch.set_num_threads(2)
    torch.set_grad_enabled(False)
    if torch.cuda.is_initialized() or os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
        raise ValueError("CPU preflight requires CUDA disabled")
    if shutil.disk_usage(ROOT).free < 1_190_000_000:
        raise ValueError("Insufficient room for both arms and their retained checkpoints")
    setup_imports()
    payload = torch.load(ROOT / "frozen536.pt", map_location="cpu", weights_only=True)
    reviews = {}
    for arm in COUNTS:
        cfg, path = config_for(arm, contract)
        options = native_argv(path)
        options[1] = str(ROOT / "frozen536.pt")
        args, overrides = flags.get_parser().parse_known_args(options)
        effective = build_config(args, overrides)
        if overrides or any(effective[key] != cfg[key] for key in ("dataset", "model", "optim", "trainer", "loss_functions")):
            raise ValueError("Native CLI changed its config")
        if cfg["model"] != payload["config"]["model"]:
            raise ValueError("Frozen checkpoint architecture changed")
        draws, val_ids = replay(cfg, arm, contract)
        reviews[arm] = {"epochs": draws, "development_ids": val_ids}
    if reviews["control536"]["development_ids"] != reviews["increment545"]["development_ids"]:
        raise ValueError("The two development sets are not identical")
    model_cfg = deepcopy(payload["config"]["model"])
    model_class = registry.get_model_class(model_cfg.pop("name"))
    model = model_class(**model_cfg)
    missing, unexpected = load_state_dict(model, match_state_dict(model.state_dict(), payload["state_dict"]), strict=True)
    if missing or unexpected or not all(p.device.type == "cpu" and torch.isfinite(p).all() for p in model.parameters()):
        raise ValueError("Strict native CPU load failed")
    for key in ("optimizer", "scheduler", "scaler", "best_val_metric", "primary_metric"):
        payload.pop(key, None)
    payload.update(epoch=0, step=0, amp=False)
    with (ROOT / "warmstart.pt").open("xb") as stream:
        torch.save(payload, stream)
    save(
        ROOT / "cpu_preflight.json",
        {
            "contract_sha256": expected,
            "warmstart_sha256": sha(ROOT / "warmstart.pt"),
            "arms": reviews,
            "device": "cpu",
            "cuda_initialized": torch.cuda.is_initialized(),
            "model_source_sha256": sha(Path(inspect.getfile(model_class))),
            "torch": str(torch.__version__),
            "development_rows": 78,
        },
    )
    print("CPU preflight passed both arms; all nine increment IDs appear once in each replay epoch.", flush=True)


def extract_sid(batch):
    value = batch.sid
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], str):
        return value[0]
    raise ValueError(f"Native batch lost its single string sample identity: {type(value)}")


def observe_training(arm, output, review, expected, gpu):
    import torch
    from scripts.adsorption.direct_training_arm import install_two_backward_guard
    from scripts.adsorption.role_force_trainer import RoleForceTrainer

    install_two_backward_guard(RoleForceTrainer, {"_request_sha256": expected}, output)
    original_train = RoleForceTrainer.train
    original_loss = RoleForceTrainer._compute_loss
    original_backward = RoleForceTrainer._backward
    epoch_length = COUNTS[arm]
    expected_sequence = [sid for epoch in review["epochs"] for sid in epoch]

    def loss(self, out, batch):
        result = original_loss(self, out, batch)
        if self.model.training and torch.is_grad_enabled():
            self._comparison_sid = extract_sid(batch)
            if self._comparison_sid != expected_sequence[int(self.step) - 1]:
                raise RuntimeError("Actual training batch differed from the approved replay")
        return result

    def backward(self, value):
        updates_before = self._direct_optimizer_updates
        result = original_backward(self, value)
        step = int(self.step)
        if step != self._comparison_seen + 1 or self._comparison_sid != expected_sequence[step - 1]:
            raise RuntimeError("Missing actual training visit record")
        record = {
            "step": step,
            "epoch": (step - 1) // epoch_length + 1,
            "sample_id": self._comparison_sid,
            "optimizer_update": self._direct_optimizer_updates > updates_before,
        }
        self._comparison_trace.write(json.dumps(record) + "\n")
        self._comparison_seen = step
        self._comparison_sid = None
        return result

    def train(self, *args, **kwargs):
        params = list(self.model.parameters())
        if (
            self.step != 0
            or len(self.train_loader) != epoch_length
            or not params
            or any(p.device.type != "cuda" or p.device.index != 0 for p in params)
            or len(self.val_loader) != 78
        ):
            raise RuntimeError("The actual native training state or development count changed")
        save(
            output / "execution_device.json",
            {
                "job_id": os.environ["SLURM_JOB_ID"],
                "gpu": gpu,
                "training_rows": epoch_length,
                "development_rows": 78,
            },
        )
        self._comparison_seen = 0
        self._comparison_sid = None
        with (output / "training_visits.jsonl").open("x", buffering=1, encoding="utf-8") as trace:
            self._comparison_trace = trace
            result = original_train(self, *args, **kwargs)
        if self._comparison_seen != len(expected_sequence) or self.step != len(expected_sequence):
            raise RuntimeError("Two epochs were not completed")
        save(
            output / "training_completed.json",
            {
                "native_iterations": self._comparison_seen,
                "optimizer_updates": self._direct_optimizer_updates,
                "epochs": 2,
                "heldout_used": False,
                "contract_sha256": expected,
            },
        )
        return result

    RoleForceTrainer._compute_loss = loss
    RoleForceTrainer._backward = backward
    RoleForceTrainer.train = train


def train_arm(arm, output, expected, contract):
    path = ROOT / "cpu_preflight.json"
    pre = load(path)
    if pre["contract_sha256"] != expected or sha(ROOT / "warmstart.pt") != pre["warmstart_sha256"] or pre["cuda_initialized"]:
        raise ValueError("CPU preflight or shared warmstart changed")
    job = os.environ.get("SLURM_JOB_ID", "")
    if not job.isdecimal() or output.resolve() != ROOT / f"{arm}_{job}":
        raise ValueError("Use the single bound Slurm output allocation")
    gpu = gpu_snapshot(os.environ.get("SLURM_JOB_GPUS", os.environ.get("CUDA_VISIBLE_DEVICES", "")))
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu["uuid"]
    import torch

    if torch.cuda.is_initialized() or not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Exactly one scheduler-assigned CUDA device required")
    if float(torch.ones(8, device="cuda:0").sum().item()) != 8:
        raise RuntimeError("Allocated CUDA kernel check failed")
    # Check remaining disk before permitting model execution; files from other jobs are never touched.
    if shutil.disk_usage(ROOT).free < 520_000_000:
        raise RuntimeError("Insufficient space for the native best and last checkpoints")
    save(output / "allocation_preflight.json", {"job_id": job, "gpu": gpu, "cuda": torch.version.cuda, "contract_sha256": expected})
    observe_training(arm, output, pre["arms"][arm], expected, gpu)
    _, config_path = config_for(arm, contract)
    os.chdir(output)
    sys.argv = ["fairchem.core._cli", *native_argv(config_path)]
    started = time.monotonic()
    runpy.run_module("fairchem.core._cli", run_name="__main__")
    candidates = list(output.glob("checkpoints/*/best_checkpoint.pt"))
    if len(candidates) != 1:
        raise RuntimeError("Exactly one development-selected native best is required")
    candidate = candidates[0]
    val = torch.load(candidate, map_location="cpu", weights_only=True)["val_metrics"]
    primary = val["forces_role_vector_mae"]
    if primary["numel"] != 78:
        raise RuntimeError("Wrong number of development frames on the native model")
    save(
        output / "candidate_binding.json",
        {
            "job_id": job,
            "arm": arm,
            "contract_sha256": expected,
            "path": candidate.relative_to(ROOT).as_posix(),
            "sha256": sha(candidate),
            "metrics": {k: v for k, v in val.items() if k.startswith("forces")},
            "native_train_cli_wall_seconds": time.monotonic() - started,
            "promoted": False,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("preflight", *COUNTS))
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contract = checked_contract(args.contract_sha256)
    if args.arm == "preflight":
        preflight(contract, args.contract_sha256)
    else:
        train_arm(args.arm, args.output, args.contract_sha256, contract)


if __name__ == "__main__":
    main()
