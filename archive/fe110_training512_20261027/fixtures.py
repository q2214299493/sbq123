"""Synthetic unit-test fixtures ported from the legacy force adapter tests."""
import json

import numpy as np
import pytest
import yaml
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import write

from scripts.adsorption.force_finetune import digest


@pytest.fixture
def fixture_manifest(tmp_path):
    splits = {}
    for i, split in enumerate(("train", "development", "heldout")):
        positions = np.zeros((47, 3))
        positions[:, 0] = np.arange(47) * 1.5
        positions[-1, 2] = 2 + i
        atoms = Atoms("Fe45CH", positions=positions, cell=[100, 20, 20], pbc=True)
        atoms.set_constraint(FixAtoms(indices=list(range(18))))
        path = tmp_path / (split + ".vasp")
        write(path, atoms, format="vasp", direct=True, vasp5=True)
        source = {"sample_id": split, "structure_sha256": digest(path), "symbols": atoms.get_chemical_symbols(),
                  "forces_eV_per_A": np.full((47, 3), .03).tolist(), "toten_eV_force_label_only": -100.,
                  "source_OUTCAR_sha256": str(i)*64}
        label_path = tmp_path / (split + "_source.json")
        label_path.write_text(json.dumps({"samples": [source]}))
        row = {**source, "structure_path": path.name, "energy_eV_force_label_only": -100.,
               "structure_equivalence_sha256": str(i)*64, "calculation_group": "job" + str(i),
               "fixed_atom_indices_0based": list(range(18)), "electronic_converged": True,
               "geometry_review_pass": True, "sample_role": "adsorption_trajectory_" + split, "ionic_step": 1,
               "label_source": {"path": label_path.name, "sha256": digest(label_path), "sample_id": split}}
        splits[split] = [row]
    manifest = {"document_kind": "aqcat25_adsorption_force_training_manifest", "training_target": "forces_only",
                "energy_loss_coefficient": 0, "reportable_final_energy": False, "splits": splits}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, manifest


@pytest.fixture
def fixture_request(fixture_manifest):
    manifest_path, _ = fixture_manifest
    remote = "/home/sbq/sbq/test_package"
    dataset = {"atoms_transform_args": {"skip_always": True}}
    config = {"optim": {"max_epochs": 4, "lr_initial": 1e-5},
              "dataset": {"train": {**dataset, "src": remote + "/train.db"},
                          "val": {**dataset, "src": remote + "/development.db"}},
              "outputs": {"forces": {"train_on_free_atoms": True, "eval_on_free_atoms": True}},
              "loss_functions": [{"energy": {"coefficient": 0}}, {"forces": {"coefficient": 1}}]}
    config_path = manifest_path.parent / "config.yml"
    config_path.write_text(yaml.safe_dump(config))
    request = {"document_kind": "aqcat25_adsorption_small_finetune_request", "manifest_path": manifest_path.name,
               "config_path": config_path.name, "remote_package_root": remote,
               "training_limits": {"epochs": 4, "learning_rate": 1e-5},
               "split_counts": {s: 1 for s in ("train", "development", "heldout")},
               "training_authorized": False,
               "artifacts": [{"path": p.name, "sha256": digest(p)} for p in (manifest_path, config_path)]}
    request_path = manifest_path.parent / "request.json"
    request_path.write_text(json.dumps(request))
    return request_path, request, config
