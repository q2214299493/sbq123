"""Small source/chemistry/duplicate safeguards; fixtures are the private work data."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import equivalent_pose_rmsd, surface_pose_symmetries
from archive.fe110_c2_site_supplement_20261106.prepare import (
    PRIOR, ROOT, SLAB, candidates, geometry, saved_rows, source_pose, twist_branch,
)


@pytest.fixture(scope="module")
def built():
    return candidates()


def test_inventory_and_no_execution(built):
    _, _, poses, records = built
    assert len(poses) == len(records) == 12
    assert {r["species_number"] for r in records} == {"05", "06", "07", "09", "11", "12", "13", "14", "18"}
    assert sum(r["byte_exact_recovery"] for r in records) == 7
    assert all(r["energy_eV"] is None and not r["relaxed"] and not r["submitted"] for r in records)


def test_source_bound_inventory():
    assert PRIOR.is_file() and ROOT.is_dir()
    rows = saved_rows()
    for key in ("11_A", "14_B", "12_A", "13_A"):
        pose, path = source_pose(rows, "original_seed", key)
        assert len(pose.frac) > 45 and path.is_file()


def test_torsion_rejects_nonbond():
    source, _ = source_pose(saved_rows(), "original_seed", "18_A")
    with pytest.raises(ValueError, match="not a source bond"):
        twist_branch(source, 47, 48, 90)


def test_torsion_keeps_fe_and_chemistry(built):
    slab, _, poses, records = built
    row = next(r for r in records if r["name"] == "18_S2")
    source = read_poscar(Path(row["source_path"]))
    assert geometry(source, poses["18_S2"], slab)["checks"]["connectivity_preserved"]
    np.testing.assert_array_equal(poses["18_S2"].frac[:45], slab.frac)


def test_collision_rejected(built):
    slab, _, poses, records = built
    pose = poses["18_S1"]
    frac = pose.frac.copy()
    frac[48] = slab.frac[41]
    bad = replace(pose, frac=frac)
    row = next(r for r in records if r["name"] == "18_S1")
    source = read_poscar(Path(row["source_path"]))
    with pytest.raises(ValueError):
        geometry(source, bad, slab)


def test_height_padding_is_duplicate():
    pose, _ = source_pose(saved_rows(), "original_seed", "18_A")
    slab = read_poscar(SLAB)
    frac = pose.frac.copy()
    frac[45:] += np.array([0., 0., .6]) @ np.linalg.inv(pose.cell)
    moved = replace(pose, frac=frac)
    score = equivalent_pose_rmsd(pose, moved, surface_pose_symmetries(slab), remove_height_shift=True)
    assert score < 1e-10
