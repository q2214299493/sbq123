"""One repaired input only; frozen hashes, scope and no hidden bond restraints."""
import json
from pathlib import Path

import pytest
from ase.io import read

from archive.fe110_five_c2_adsorption_20261006 import repair_gpu
from scripts.aqcat25_handoff import validate_handoff
from scripts.artifact_io import sha256_file

BASE = Path(__file__).resolve().parents[1] / "calculations/fe110_five_c2_adsorption_20261006"


def test_single_repair_is_exact_reviewed_input():
    package = BASE / "gpu_repair_v1"
    batch = json.loads((package / "batch_manifest.json").read_text())
    review = json.loads((BASE / "supplement_repair_v1/repair_review.json").read_text(encoding="utf-8"))
    assert [x["name"] for x in batch["handoffs"]] == ["03_extra2_repair_v1"]
    for item in batch["files"]:
        assert sha256_file(package / item["path"]) == item["sha256"]
    directory = package / batch["handoffs"][0]["name"]
    assert sha256_file(directory / "POSCAR") == review["structure_sha256"]
    validate_handoff(directory / "handoff.json", root=directory)
    doc = json.loads((directory / "handoff.json").read_text())
    atoms = read(directory / "POSCAR", format="vasp")
    assert atoms.get_chemical_symbols() == ["Fe"]*45 + ["C", "C", "O", "H"]
    assert doc["selective_dynamics"]["fixed_atom_indices_1based"] == list(range(1, 19))
    assert len(atoms.constraints) == 1
    assert not doc["adsorption"]["connectivity_constraints"]
    assert len(doc["adsorption"]["monitored_pairs"]) == 6
    assert doc["model"]["max_steps"] == 80 and doc["model"]["fmax_eV_per_A"] == .10
    plan = json.loads((package / "reviewed_plan.json").read_text(encoding="utf-8"))
    assert plan["repair_review_sha256"] == sha256_file(BASE / "supplement_repair_v1/repair_review.json")
    assert all(value is False for value in plan["restrictions"].values())
    script = (package / "batch_job.sh").read_text()
    assert "--time=00:30:00" in script
    assert "--gres=gpu:1" in script and "--cpus-per-task=4" in script


def test_frozen_package_is_not_overwritten():
    with pytest.raises(FileExistsError, match="Never overwrite"):
        repair_gpu.freeze()
