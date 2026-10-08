"""Validate exact fixed-geometry diagnostic inputs without running a model."""

import json
from pathlib import Path

import numpy as np
from ase.io import read
from evaluate_fe45_calibration import sha256_file

ROOT = Path(__file__).resolve().parent
CHECKPOINT = Path("/home/sbq/sbq/aqcat25/demo_single/model.pt")


def validate(checkpoint=True):
    batch = json.loads((ROOT / "batch_manifest.json").read_text())
    for item in batch["files"]:
        assert sha256_file(ROOT / item["path"]) == item["sha256"], item["path"]
    if checkpoint:
        assert sha256_file(CHECKPOINT) == batch["checkpoint_sha256"]
    labels = json.loads((ROOT / "labels.json").read_text())
    names = set()
    cell = None
    for label in labels["samples"]:
        name = label["sample_id"]
        assert name not in names and Path(name).name == name
        names.add(name)
        path = ROOT / "structures" / (name + ".vasp")
        assert sha256_file(path) == label["structure_sha256"]
        atoms = read(path, format="vasp")
        assert atoms.get_chemical_symbols() == label["symbols"]
        assert atoms.get_chemical_symbols()[:45] == ["Fe"] * 45
        assert len(atoms.constraints) == 1
        assert list(atoms.constraints[0].get_indices()) == list(range(18))
        assert label["fixed_atom_indices_1based"] == list(range(1, 19))
        assert np.isfinite(atoms.positions).all()
        if cell is None:
            cell = atoms.cell.array.copy()
        assert np.allclose(atoms.cell.array, cell, rtol=0, atol=1e-10)
    assert len(names) == 10
    assert not (ROOT / "output" / "predictions.json").exists(), "No duplicate execution"
    print("GPU_BEFORE_EXECUTION_PASS_NO_MODEL_RUN", flush=True)
    return batch


if __name__ == "__main__":
    validate()
