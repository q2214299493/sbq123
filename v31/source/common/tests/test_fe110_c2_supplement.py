"""Bounded checks of supplement transforms and surface-aware duplicate comparison."""
from copy import deepcopy

import numpy as np

from archive.fe110_five_c2_adsorption_20261006.build_supplement import (
    equivalent_rmsd, oriented_frame,
)
from scripts.adsorption.build_fe110_adsorption import Poscar


def template():
    cell = np.diag([10., 6., 23.])
    ads = np.array([[.42, .45, .75], [.55, .48, .76], [.4, .57, .79], [.38, .38, .79]])
    return Poscar("test", cell, ["Fe", "C", "H"], [45, 2, 2],
                  np.vstack((np.zeros((45, 3)), ads)), [("T", "T", "T")]*49)


def test_height_only_shift_is_duplicate():
    a, b = template(), template()
    b.frac[45:, 2] += .2 / 23.
    assert equivalent_rmsd(a, b, [(np.eye(3), np.zeros(3))]) < 1e-12


def test_periodic_translation_and_identical_h_swap_are_duplicates():
    a, b = template(), template()
    b.frac[45:, 0] += 1.
    b.frac[[47, 48]] = b.frac[[48, 47]]
    assert equivalent_rmsd(a, b, [(np.eye(3), np.zeros(3))]) < 1e-12


def test_surface_symmetry_is_used_but_not_arbitrary_rotation():
    a, b = template(), template()
    rotation = np.diag([-1., -1., 1.])
    b.frac[45:] = a.frac[45:] @ rotation.T
    assert equivalent_rmsd(a, b, [(rotation, np.zeros(3))]) < 1e-12
    assert equivalent_rmsd(a, b, [(np.eye(3), np.zeros(3))]) > .2


def test_orientation_frame_is_proper_and_preserves_all_internal_distances():
    a = template()
    original = deepcopy(a.frac[45:] @ a.cell)
    rotation = oriented_frame([0., 1., .8]) @ oriented_frame([1., .1, .1]).T
    assert np.allclose(rotation @ rotation.T, np.eye(3))
    assert np.isclose(np.linalg.det(rotation), 1.)
    mapped = original @ rotation.T
    assert np.allclose(np.linalg.norm(original[:, None]-original[None, :], axis=2),
                       np.linalg.norm(mapped[:, None]-mapped[None, :], axis=2))
