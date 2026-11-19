"""Check the existing Fairchem CPU runtime with synthetic rows and the frozen checkpoint."""
from __future__ import annotations

from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
import inspect
import json
import os
from pathlib import Path
import resource
import socket
import sys
from tempfile import TemporaryDirectory

ROOT = Path("/home/sbq/sbq")
CHECKPOINT = ROOT / "fe110_force_training536_execution_20261113_v4/checkpoints/2026-11-14-00-04-16/best_checkpoint.pt"
CHECKPOINT_SHA256 = "2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0"
REFERENCE = ROOT / "fe110_force_training536_smoke_20261113_v1/control"
SAMPLER_SHA256 = "ab2015d56b6a370765420f1ba26880074988cd864f02286fed7b90bc3d79dc5d"
COUNT = 545
SEED = 42


def digest(path):
    value = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def synthetic_dataset(config, work):
    import numpy as np
    from ase import Atoms
    from ase.db import connect
    from fairchem.core.datasets.base_dataset import create_dataset

    database = work / "synthetic545.db"
    metadata = work / "synthetic545.npz"
    with connect(database) as db:
        for index in range(COUNT):
            db.write(Atoms("H", positions=[[0, 0, 0]]), data={"sid": f"cpu_probe_{index}"})
    np.savez(metadata, natoms=np.ones(COUNT, dtype=int), adsorption_sampling_probability=np.full(COUNT, 1 / COUNT))
    options = {**config, "src": str(database), "metadata_path": str(metadata)}
    return create_dataset(options, "train")


def native_check(work):
    import numpy as np
    import torch
    import yaml
    from fairchem.core.common.flags import flags
    from fairchem.core.common.registry import registry
    from fairchem.core.common.utils import build_config, load_state_dict, match_state_dict, setup_imports
    from fairchem.core.datasets.base_dataset import create_dataset
    from scripts.adsorption.force_role_runtime import RoleBatchSampler

    torch.set_num_threads(2)
    torch.set_grad_enabled(False)
    if torch.cuda.is_initialized() or digest(inspect.getfile(RoleBatchSampler)) != SAMPLER_SHA256:
        raise ValueError("CPU-only boundary or runtime sampler identity changed")
    frozen_cfg = yaml.safe_load((REFERENCE / "config.yml").read_text())
    cfg = deepcopy(frozen_cfg)
    cfg["optim"].update(eval_every=COUNT, checkpoint_every=COUNT)
    config_file = work / "review.yml"
    config_file.write_text(yaml.safe_dump(cfg))
    args, overrides = flags.get_parser().parse_known_args([
        "--checkpoint", str(CHECKPOINT), "--mode", "train", "--config-yml",
        str(config_file), "--seed", str(SEED), "--amp",
    ])
    effective = build_config(args, overrides)
    if overrides or any(effective[key] != cfg[key] for key in ("dataset", "model", "optim", "trainer", "loss_functions")):
        raise ValueError("Native CLI changed the bound review settings")
    setup_imports()
    dataset = synthetic_dataset(cfg["dataset"]["train"], work)
    ids = dataset.dataset.db_ids
    if len(ids) != 1 or list(ids[0]) != list(range(1, COUNT + 1)):
        raise ValueError("Synthetic ASE source rows were not enumerated in DB row order")
    mapping = [int(index) for index in dataset.indices]
    if sorted(mapping) != list(range(COUNT)):
        raise ValueError("Unexpected Fairchem subset or row index mapping")
    probabilities = dataset.get_metadata("adsorption_sampling_probability", np.arange(COUNT))
    if len(probabilities) != COUNT or not np.all(probabilities == 1 / COUNT):
        raise ValueError("Native dataset lost the uniform row probabilities")
    sampler = RoleBatchSampler(probabilities, 1, SEED)
    epoch_counts = []
    epoch_draws = []
    for epoch in range(2):
        sampler.set_epoch(epoch)
        draws = [mapping[batch[0]] for batch in sampler]
        if len(draws) != COUNT:
            raise ValueError("Native sampler did not yield the full epoch")
        tally = Counter(draws)
        epoch_draws.append(draws)
        epoch_counts.append([tally[index] for index in range(COUNT)])

    checkpoint_hash = digest(CHECKPOINT)
    if checkpoint_hash != CHECKPOINT_SHA256:
        raise ValueError("Frozen native checkpoint identity changed")
    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)
    if payload["config"]["model"] != cfg["model"]:
        raise ValueError("Frozen model and review config disagree")
    model_args = deepcopy(cfg["model"])
    model_type = registry.get_model_class(model_args.pop("name"))
    model = model_type(**model_args)
    missing, extra = load_state_dict(model, match_state_dict(model.state_dict(), payload["state_dict"]), strict=True)
    parameters = list(model.parameters())
    if missing or extra or not parameters or torch.cuda.is_initialized() or digest(CHECKPOINT) != checkpoint_hash:
        raise ValueError("Native strict CPU model load failed")
    if not all(p.device.type == "cpu" and torch.isfinite(p).all().item() for p in parameters):
        raise ValueError("Non-CPU or nonfinite model parameter")
    return {
        "host": socket.gethostname(),
        "torch": str(torch.__version__),
        "checkpoint_sha256": checkpoint_hash,
        "reference_config_sha256": digest(REFERENCE / "config.yml"),
        "sampler_sha256": digest(inspect.getfile(RoleBatchSampler)),
        "dataset_factory_sha256": digest(inspect.getfile(create_dataset)),
        "dataset_config_parsed": True,
        "training_row_count": COUNT,
        "test_dataset": "synthetic ASE DB with the same loader options and uniform metadata",
        "database_positions_in_runtime_order": mapping,
        "seed": SEED,
        "epoch_draws_db_positions_0based": epoch_draws,
        "epoch_counts_by_db_position": epoch_counts,
        "strict_cpu_model_load": True,
        "trainable_parameters": sum(p.numel() for p in parameters if p.requires_grad),
        "native_forward_calls": 0,
        "optimizer_steps": 0,
        "cuda_initialized": False,
        "training_authorized": False,
    }


def main():
    if socket.gethostname() != "MZ73" or os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
        raise ValueError("Probe requires the reviewed MZ73 CPU-only runtime")
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    resource.setrlimit(resource.RLIMIT_CPU, (37, 42))
    with TemporaryDirectory(prefix="fe110_force545_cpu_probe_", dir=ROOT) as temp:
        work = Path(temp)
        for key in ("TMPDIR", "XDG_CACHE_HOME", "HF_HOME", "TORCH_HOME", "CUDA_CACHE_PATH"):
            location = work / key.lower()
            location.mkdir()
            os.environ[key] = str(location)
        with redirect_stdout(sys.stderr):
            result = native_check(work)
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
