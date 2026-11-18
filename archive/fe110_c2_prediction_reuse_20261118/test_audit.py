"""Reject invalid reuse despite matching names or nearly matching geometries."""
from ase import Atoms
from ase.constraints import FixAtoms

from archive.fe110_c2_prediction_reuse_20261118.audit import MODEL_SHA, eligible, same_coordinates


def structure():
    atoms = Atoms('FeCH', positions=[[0, 0, 0], [1, 1, 2], [1, 1, 3]], cell=[8, 8, 20], pbc=[True, True, False])
    atoms.set_constraint(FixAtoms(indices=[0]))
    return atoms


def test_same_coordinate_old_checkpoint_is_not_frozen536_prediction():
    atoms = structure()
    assert not eligible('cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0', atoms, atoms.copy())


def test_same_model_near_duplicate_is_not_same_coordinate():
    atoms, other = structure(), structure()
    other.positions[1, 2] += .001
    assert not eligible(MODEL_SHA, atoms, other)


def test_xy_wrapping_preserves_coordinates_but_z_shift_does_not():
    atoms, other = structure(), structure()
    other.positions[1, 0] += 8
    assert same_coordinates(atoms, other)
    other.positions[1, 2] += 20
    assert not same_coordinates(atoms, other)


def test_fixed_mask_change_prevents_reuse():
    atoms, other = structure(), structure()
    other.set_constraint(FixAtoms(indices=[0, 1]))
    assert not same_coordinates(atoms, other)
