"""Scientific geometry and immutable-resume checks; no network or potential."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.build import bcc110
from ase.constraints import FixAtoms
from ase.io import read, write

from scripts.adsorption import reico_random_geometry as sampler
from scripts.artifact_io import sha256_file

CONFIG = Path(__file__).resolve().parents[1] / "configs/fe110_reico_pilot/geometry_v1.json"


@pytest.fixture
def config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


@pytest.fixture
def slab():
    atoms = bcc110("Fe", size=(3, 3, 5), a=2.8269483674, vacuum=7.5, orthogonal=False)
    atoms.pbc = True
    atoms.set_constraint(FixAtoms(indices=list(range(18))))
    return atoms


def test_frozen_families_are_split_before_sampling(config):
    sampler.validate_config(config)
    plan = sampler.family_plan(config)
    assert len(plan) == 100
    assert len({f["family_id"] for f in plan}) == 100
    for group, expected in {"train": 80, "development": 10, "final_test": 10}.items():
        rows = [r for r in plan if r["partition"] == group]
        assert len(rows) == expected
        assert sum(r["counts"]["C"] == 2 for r in rows) == expected // 2
        assert sum(r["counts"]["C"] == 3 for r in rows) == expected // 2
    assert sampler.family_plan(config) == plan


@pytest.mark.parametrize("mutation", ["missing_pair", "nan", "too_many", "bad_height", "bad_count", "negative_seed"])
def test_invalid_configuration_is_rejected(config, mutation):
    if mutation == "missing_pair":
        del config["pair_minimum_A"]["C-H"]
    elif mutation == "nan":
        config["pair_minimum_A"]["C-H"] = np.nan
    elif mutation == "too_many":
        config["compositions"][0]["families"]["train"] = 101
    elif mutation == "bad_height":
        config["height_above_top_Fe_A"]["H"] = [2, 1]
    elif mutation == "bad_count":
        config["compositions"][0]["counts"]["C"] = 1
    else:
        config["base_seed"] = -1
    with pytest.raises(ValueError):
        sampler.validate_config(config)


@pytest.mark.parametrize("symbol,bond_length", [("C", 1.09), ("O", 0.97)])
def test_normal_CH_and_OH_distances_are_allowed(slab, config, symbol, bond_length):
    top = slab.positions[:, 2].argmax()
    origin = slab.positions[top] + [0, 0, 2.1]
    atoms = slab + Atoms([symbol, "H"], positions=[origin, origin + [bond_length, 0, 0]])
    audit = sampler.audit_geometry(atoms, slab, config)
    assert not audit["reasons"]
    assert audit["pair_minima_A"][sampler.pair_key(symbol, "H")] == pytest.approx(bond_length)


def test_short_H_Fe_collision_is_rejected(slab, config):
    origin = slab.positions[slab.positions[:, 2].argmax()]
    atoms = slab + Atoms("CH", positions=[origin + [0, 0, 2.1], origin + [0, 0, 1.0]])
    assert "SHORT_CONTACT:Fe-H" in sampler.audit_geometry(atoms, slab, config)["reasons"]


def test_changed_slab_and_fixed_mask_are_rejected(slab, config):
    atoms = sampler.draw_atoms(slab, {"C": 2, "O": 1, "H": 1}, config, np.random.default_rng(42))
    atoms.positions[0, 0] += 0.01
    assert sampler.audit_geometry(atoms, slab, config)["reasons"] == ["SLAB_OR_CONSTRAINT_CHANGED"]
    atoms.positions[:45] = slab.positions
    atoms.set_constraint(FixAtoms(indices=list(range(17))))
    assert sampler.audit_geometry(atoms, slab, config)["reasons"] == ["SLAB_OR_CONSTRAINT_CHANGED"]


def test_nonfinite_geometry_is_rejected_before_mic(slab, config):
    atoms = sampler.draw_atoms(slab, {"C": 2, "O": 1, "H": 1}, config, np.random.default_rng(42))
    atoms.positions[-1, 0] = np.nan
    assert sampler.audit_geometry(atoms, slab, config)["reasons"] == ["NONFINITE_GEOMETRY"]


def test_exact_duplicate_key_preserves_site_and_height(slab, config):
    a = sampler.draw_atoms(slab, {"C": 2, "O": 1, "H": 2}, config, np.random.default_rng(12))
    b = a.copy()
    b.positions[45:] += a.cell[0] - a.cell[1]
    b.positions[[48, 49]] = b.positions[[49, 48]]
    assert sampler.geometry_key(a) == sampler.geometry_key(b)
    b.positions[45:, 2] += 0.1
    assert sampler.geometry_key(a) != sampler.geometry_key(b)
    b.positions[45:, 2] -= 0.1
    b.positions[45:, 0] += 0.2
    assert sampler.geometry_key(a) != sampler.geometry_key(b)


def make_run_input(tmp_path, slab, config):
    source = tmp_path / "slab.POSCAR"
    write(source, slab, format="vasp", direct=True, sort=False)
    config["source_slab"] = "slab.POSCAR"
    config["source_slab_sha256"] = sha256_file(source)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_generation_roundtrip_resume_and_source_binding(tmp_path, slab, config, monkeypatch):
    path = make_run_input(tmp_path, slab, config)
    output = tmp_path / "run"
    first = sampler.run(path, output, root=tmp_path, limit=4)
    assert first["generated"] == 4 and first["failed"] == 0
    assert first["gpu_jobs"] == first["dft_jobs"] == first["training_runs"] == 0
    assert first["attempts"] <= 80
    hashes = {p: sha256_file(p) for p in output.rglob("*") if p.is_file()}
    monkeypatch.setattr(sampler, "generate_family", lambda *args: pytest.fail("completed families must not be regenerated"))
    assert sampler.run(path, output, root=tmp_path, limit=4) == first
    assert all(sha256_file(p) == digest for p, digest in hashes.items())
    source = tmp_path / "slab.POSCAR"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source slab SHA256"):
        sampler.run(path, output, root=tmp_path, limit=4)


def test_tampered_poscar_is_not_overwritten(tmp_path, slab, config):
    path = make_run_input(tmp_path, slab, config)
    output = tmp_path / "run"
    sampler.run(path, output, root=tmp_path, limit=1)
    poscar = output / "families/family_0001/POSCAR"
    modified = poscar.read_bytes() + b"changed\n"
    poscar.write_bytes(modified)
    with pytest.raises(ValueError, match="changed POSCAR"):
        sampler.run(path, output, root=tmp_path, limit=1)
    assert poscar.read_bytes() == modified


def test_exhausted_family_is_preserved_without_retry(tmp_path, slab, config):
    config["pair_minimum_A"]["C-Fe"] = 100
    config["max_attempts_per_family"] = 2
    path = make_run_input(tmp_path, slab, config)
    output = tmp_path / "run"
    result = sampler.run(path, output, root=tmp_path, limit=1)
    assert result["generated"] == 0 and result["failed"] == 1 and result["attempts"] == 2
    assert not (output / "families/family_0001/POSCAR").exists()
    assert sampler.run(path, output, root=tmp_path, limit=1) == result


def test_partial_family_resumes_deterministically(tmp_path, slab, config):
    path = make_run_input(tmp_path, slab, config)
    output = tmp_path / "run"
    sampler.run(path, output, root=tmp_path, limit=1)
    family = output / "families/family_0001"
    expected = (family / "family.json").read_bytes()
    # Simulate the completion record not yet being published after output files.
    (family / "family.json").unlink()
    sampler.run(path, output, root=tmp_path, limit=1)
    assert (family / "family.json").read_bytes() == expected


def test_invalid_source_fixed_mask_is_rejected(tmp_path, slab, config):
    slab.set_constraint(FixAtoms(indices=list(range(17))))
    path = make_run_input(tmp_path, slab, config)
    with pytest.raises(ValueError, match="bottom 18"):
        sampler.run(path, tmp_path / "run", root=tmp_path, limit=1)


def test_random_seed_and_poscar_are_reproducible(slab, config):
    counts = copy.deepcopy(config["compositions"][0]["counts"])
    a = sampler.draw_atoms(slab, counts, config, np.random.default_rng(42))
    b = sampler.draw_atoms(slab, counts, config, np.random.default_rng(42))
    assert sampler.render_poscar(a) == sampler.render_poscar(b)
    loaded = read(__import__("io").StringIO(sampler.render_poscar(a).decode()), format="vasp")
    assert sampler.fixed_indices(loaded) == list(range(18))
    assert loaded.get_chemical_symbols()[45:] == ["C", "C", "O", "H"]
