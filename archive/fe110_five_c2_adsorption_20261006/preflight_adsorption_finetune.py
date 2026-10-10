"""Actual MZ73 CPU runtime checks; never instantiate or run a model."""

import hashlib
import json
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
    from fairchem.core.datasets.ase_datasets import AseDBDataset
    import fairchem.core._cli  # noqa: F401

    setup_imports()
    registry.get_model_class("aqformer_backbone_film")
    registry.get_trainer_class(config["trainer"])
    counts = {}
    for split, key in (("train", "train"), ("development", "val")):
        dataset = AseDBDataset(config["dataset"][key])
        assert len(dataset) == request["split_counts"][split]
        database = connect(root / f"{split}.db")
        for index in range(len(dataset)):
            graph = dataset[index]
            atoms = database.get(id=index + 1).toatoms()
            expected_positions = wrap_positions(atoms.positions, atoms.cell, pbc=atoms.pbc, eps=0)
            np.testing.assert_allclose(graph.pos.numpy(), expected_positions, atol=1e-5)
            np.testing.assert_allclose(graph.forces.numpy(), atoms.get_forces(apply_constraint=False), atol=1e-6)
            assert int(graph.fixed.sum()) == 18
            assert torch.all(graph.fixed[:18] == 1) and torch.all(graph.fixed[18:] == 0)
            assert torch.all(graph.tags == 0)
            assert torch.isfinite(graph.forces).all()
        counts[split] = len(dataset)
    baseline = Path(request["base_checkpoint"]["path"])
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == request["base_checkpoint"]["sha256"]
    checkpoint = torch.load(baseline, map_location="cpu", weights_only=False)
    assert checkpoint["config"]["model"] == config["model"]
    print(json.dumps({"status": "PASS_NO_MODEL_RUN", "counts": counts,
                      "heldout_not_consumed": True, "model_instantiated": False,
                      "training_performed": False, "torch_version": torch.__version__}))


if __name__ == "__main__":
    main()
