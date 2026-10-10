"""Actual MZ73 CPU runtime checks; never instantiate or run a model."""

import hashlib
import json
import shlex
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from ase.db import connect
from ase.geometry import wrap_positions


def main():
    root = Path(sys.argv[1])
    request = json.loads((root / "training_request.json").read_text())
    config = yaml.safe_load((root / "config.yml").read_text())
    from fairchem.core.common.utils import setup_imports
    from fairchem.core.common.registry import registry
    from fairchem.core.common.flags import flags
    from fairchem.core.common.utils import build_config
    import fairchem.core._cli  # noqa: F401

    setup_imports()
    registry.get_model_class("aqformer_backbone_film")
    registry.get_trainer_class(config["trainer"])
    # Parse the actual wrapper invocation, not an independently reconstructed one.
    wrapper = (root / "runtime/adsorption_finetune_job.sh").read_text()
    invocation = [line for line in wrapper.splitlines() if ' -m fairchem.core._cli ' in line]
    assert len(invocation) == 1
    tokens = shlex.split(invocation[0])
    assert tokens[:3] == ["$AQCAT_PYTHON", "-m", "fairchem.core._cli"]
    cli_args = [token.replace("$PACKAGE_ROOT", str(root)).replace("$RUN_ROOT", str(root / "output/preflight_placeholder"))
                for token in tokens[3:]]
    args, overrides = flags.get_parser().parse_known_args(cli_args)
    assert not overrides, "unreviewed CLI overrides"
    effective = build_config(args, overrides)
    assert effective["seed"] == config["seed"] == request["training_limits"]["seed"] == 42
    assert effective["mode"] == "train" and effective["amp"] is True
    assert not effective["submit"] and effective["world_size"] == 1
    for key in ("dataset", "optim", "model", "outputs", "loss_functions", "evaluation_metrics", "trainer"):
        assert effective[key] == config[key], f"CLI changed {key}"
    # Exercise the actual trainer's dataset factory, sampler and collater without
    # invoking its constructor (which would instantiate and run the model).
    trainer_class = registry.get_trainer_class(config["trainer"])
    trainer = trainer_class.__new__(trainer_class)
    trainer.device = torch.device("cpu")
    trainer.config = {**effective, "cmd": {"seed": effective["seed"]},
                      "dataset": effective["dataset"]["train"],
                      "val_dataset": effective["dataset"]["val"],
                      "test_dataset": {}, "relax_dataset": {}}
    trainer.load_datasets()
    counts = {}
    for split, key in (("train", "train"), ("development", "val")):
        dataset = trainer.train_dataset if key == "train" else trainer.val_dataset
        assert len(dataset) == request["split_counts"][split]
        database = connect(root / f"{split}.db")
        rows = list(database.select())
        for index in range(len(dataset)):
            graph = dataset[index]
            source_index = int(dataset.indices[index])
            assert int(dataset.get_metadata("row_ids", index)) == rows[source_index].id
            atoms = rows[source_index].toatoms()
            assert int(dataset.get_metadata("natoms", index)) == len(atoms)
            expected_positions = wrap_positions(atoms.positions, atoms.cell, pbc=atoms.pbc, eps=0)
            np.testing.assert_allclose(graph.pos.numpy(), expected_positions, atol=1e-5)
            np.testing.assert_allclose(graph.forces.numpy(), atoms.get_forces(apply_constraint=False), atol=1e-6)
            assert int(graph.fixed.sum()) == 18
            assert torch.all(graph.fixed[:18] == 1) and torch.all(graph.fixed[18:] == 0)
            assert torch.all(graph.tags == 0)
            assert torch.isfinite(graph.forces).all()
        sampler = trainer.train_sampler if key == "train" else trainer.val_sampler
        indices = [index for batch in sampler for index in batch]
        assert sorted(indices) == list(range(len(dataset)))
        loader = trainer.train_loader if key == "train" else trainer.val_loader
        assert sum(int(batch.num_graphs) for batch in loader) == len(dataset)
        counts[split] = len(dataset)
    baseline = Path(request["base_checkpoint"]["path"])
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == request["base_checkpoint"]["sha256"]
    checkpoint = torch.load(baseline, map_location="cpu", weights_only=False)
    assert checkpoint["config"]["model"] == config["model"]
    print(json.dumps({"status": "PASS_NO_MODEL_RUN", "counts": counts,
                      "actual_trainer_dataset_sampler_loader_traversed": True,
                      "effective_cli_seed": effective["seed"], "CLI_matches_reviewed_config": True,
                      "heldout_not_consumed": True, "model_instantiated": False,
                      "training_performed": False, "torch_version": torch.__version__}))


if __name__ == "__main__":
    main()
