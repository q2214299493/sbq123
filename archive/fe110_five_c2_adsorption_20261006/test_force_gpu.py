import importlib.util
import json

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import write

from archive.fe110_five_c2_adsorption_20261006 import c2_force_gpu
from scripts.artifact_io import sha256_file


def frozen(tmp_path, monkeypatch):
    source = tmp_path / "source"
    structures = source / "structures"
    structures.mkdir(parents=True)
    samples = []
    for index in range(10):
        atoms = Atoms("Fe45C2H", positions=np.zeros((48, 3)), cell=[8, 8, 23])
        atoms.set_constraint(FixAtoms(indices=range(18)))
        path = structures / f"s{index}.vasp"
        write(path, atoms, format="vasp")
        samples.append(
            {
                "sample_id": f"s{index}",
                "structure_sha256": sha256_file(path),
                "symbols": atoms.get_chemical_symbols(),
                "fixed_atom_indices_1based": list(range(1, 19)),
            }
        )
    (source / "labels.json").write_text(json.dumps({"samples": samples}))
    (source / "evaluate_fe45_calibration.py").write_text(
        "import hashlib\ndef sha256_file(path):\n    return hashlib.sha256(path.read_bytes()).hexdigest()\n"
    )
    (source / "assessment_plan.json").write_text(
        json.dumps(
            {
                "labels_sha256": sha256_file(source / "labels.json"),
                "runner_sha256": sha256_file(source / "evaluate_fe45_calibration.py"),
                "checkpoint_sha256": "a" * 64,
            }
        )
    )
    package = tmp_path / "package"
    monkeypatch.setattr(c2_force_gpu, "PACKAGE", package)
    monkeypatch.setattr(c2_force_gpu, "SOURCE", source)
    env_base = tmp_path / "base"
    env = env_base / "gpu_repair_v1/runtime/aqcat25_mz73_env.sh"
    env.parent.mkdir(parents=True)
    env.write_text("# test environment fixture\n")
    monkeypatch.setattr(c2_force_gpu, "BASE", env_base)
    c2_force_gpu.freeze()
    monkeypatch.syspath_prepend(str(package))
    spec = importlib.util.spec_from_file_location("diagnostic_preflight_test", package / "force_prediction_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return package, module


def test_frozen_inputs_validate_without_model(tmp_path, monkeypatch):
    package, module = frozen(tmp_path, monkeypatch)
    assert module.validate(checkpoint=False)["remote_root"] == c2_force_gpu.REMOTE
    assert not (package / "output").exists()
    with pytest.raises(AssertionError, match="Preserve"):
        c2_force_gpu.freeze()


def test_stale_hash_rejected(tmp_path, monkeypatch):
    _, module = frozen(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "sha256_file", lambda _: "0" * 64)
    with pytest.raises(AssertionError):
        module.validate(checkpoint=False)
