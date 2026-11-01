from dataclasses import replace

import numpy as np
import pytest

from scripts.adsorption.build_fe110_adsorption import read_poscar
from archive.fe110_c2_16_19_prepare_20261101 import prepare
from archive.fe110_c2_16_19_prepare_20261101.verify import audit_geometry


@pytest.mark.parametrize("number", ["16", "17", "18", "19"])
def test_exact_saved_isomer(number):
    pose = read_poscar(prepare.OUT / (number + "_A") / "POSCAR")
    slab = read_poscar(prepare.SLAB)
    assert audit_geometry(pose, slab, number)["expected_bonds_verified"] >= 6


def test_changed_fixed_slab_is_rejected():
    pose = read_poscar(prepare.OUT / "16_A/POSCAR")
    frac = pose.frac.copy()
    frac[0, 0] += .01
    with pytest.raises(AssertionError):
        audit_geometry(replace(pose, frac=frac), read_poscar(prepare.SLAB), "16")


def test_hydrogen_on_wrong_atom_is_rejected():
    pose = read_poscar(prepare.OUT / "17_A/POSCAR")
    frac = pose.frac.copy()
    frac[51] = frac[47] + np.array([0., 0., 1.0]) @ np.linalg.inv(pose.cell)
    with pytest.raises(AssertionError):
        audit_geometry(replace(pose, frac=frac), read_poscar(prepare.SLAB), "17")


def test_fixed_adsorbate_is_rejected():
    pose = read_poscar(prepare.OUT / "18_A/POSCAR")
    flags = pose.flags.copy()
    flags[45] = ("F", "F", "F")
    with pytest.raises(AssertionError):
        audit_geometry(replace(pose, flags=flags), read_poscar(prepare.SLAB), "18")


def test_ethane_carbon_exchange_is_not_a_new_seed():
    pose = read_poscar(prepare.OUT / "19_A/POSCAR")
    frac = pose.frac.copy()
    frac[[45, 46]] = frac[[46, 45]]
    operations = [(np.eye(3, dtype=int), np.zeros(3))]
    assert prepare.seed_rmsd(pose, replace(pose, frac=frac), operations, "19") < 1e-10


def test_existing_output_is_not_overwritten():
    with pytest.raises(FileExistsError):
        prepare.main()
