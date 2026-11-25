"""Geometric invariants for explicit seed repairs; no calculator or scientific run."""
import itertools

import numpy as np
import pytest

from archive.fe110_c2_11_15_20261020.refine_and_audit import angle_degrees, bend_branch, metrics, rotation_between
from scripts.adsorption.build_fe110_adsorption import Poscar
from scripts.adsorption.build_fe110_care_batch import display_coordinates, molecular_signature
from scripts.adsorption.build_fe110_care_isomers import connectivity


def linear_seed(hydroxyl=False):
    cell = np.diag([12., 12., 25.])
    first, center, oxygen = np.array([3.5, 5., 10.]), np.array([5., 5., 10.]), np.array([6.4, 5., 10.])
    if hydroxyl:
        hydrogens = [first + [-.54, .94, 0.], first + [-.54, -.94, 0.], oxygen + [.33, 0., .91]]
    else:
        hydrogens = [first + 1.09 * np.array([-1. / 3., np.sqrt(8. / 9.) * np.cos(a), np.sqrt(8. / 9.) * np.sin(a)])
                     for a in np.radians([0., 120., 240.])]
    positions = np.vstack((np.zeros((45, 3)), first, center, oxygen, hydrogens))
    return Poscar("linear unit fixture", cell, ["Fe", "C", "O", "H"], [45, 2, 1, 3],
                  positions @ np.linalg.inv(cell), [("F", "F", "F")] * 18 + [("T", "T", "T")] * 33)


def bond_lengths(pose):
    indices = list(range(45, 51))
    xyz = display_coordinates(pose)
    return {(a, b): np.linalg.norm(xyz[45 + a] - xyz[45 + b]) for a, b in connectivity(pose, indices)}


@pytest.mark.parametrize("hydroxyl", [False, True])
def test_bending_repairs_the_center_without_stretching_bonds_or_losing_H(hydroxyl):
    parent = linear_seed(hydroxyl)
    result = bend_branch(parent, center=46, fixed=45, branch=47, target_angle_deg=120.)
    xyz = display_coordinates(result)
    assert angle_degrees(xyz[45], xyz[46], xyz[47]) == pytest.approx(120.)
    assert molecular_signature(result) == molecular_signature(parent)
    assert bond_lengths(result) == pytest.approx(bond_lengths(parent), abs=1e-10)
    assert np.array_equal(result.frac[:45], parent.frac[:45])
    assert np.array_equal(result.frac[45:47], parent.frac[45:47])
    assert result.flags == parent.flags
    if hydroxyl:
        assert not np.array_equal(result.frac[50], parent.frac[50])


def test_periodic_branch_rotation_preserves_bonds():
    parent = linear_seed(True)
    coords = parent.frac.copy()
    coords[45:, 0] = (coords[45:, 0] + .5) % 1.
    parent = Poscar(parent.comment, parent.cell, parent.symbols, parent.counts, coords, parent.flags)
    result = bend_branch(parent, center=46, fixed=45, branch=47, target_angle_deg=120.)
    assert bond_lengths(result) == pytest.approx(bond_lengths(parent), abs=1e-10)


@pytest.mark.parametrize("angle", [0., 180., float("nan")])
def test_invalid_bend_angles_are_rejected(angle):
    with pytest.raises(ValueError, match="strictly between"):
        bend_branch(linear_seed(), center=46, fixed=45, branch=47, target_angle_deg=angle)


def test_hydrogen_cannot_be_selected_as_the_heavy_branch():
    with pytest.raises(ValueError, match="heavy-atom bonds"):
        bend_branch(linear_seed(), center=45, fixed=46, branch=48, target_angle_deg=120.)


@pytest.mark.parametrize("first,second", list(itertools.product(([1., 0., 0.],), ([1., 0., 0.], [-1., 0., 0.], [0., 0., 1.]))))
def test_rotation_is_proper_even_for_antiparallel_vectors(first, second):
    first, second = np.array(first), np.array(second)
    matrix = rotation_between(first, second)
    assert np.allclose(matrix @ first, second)
    assert np.allclose(matrix.T @ matrix, np.eye(3))
    assert np.linalg.det(matrix) == pytest.approx(1.)


def test_review_catches_the_previously_unchecked_linear_center():
    parent = linear_seed()
    slab = Poscar("unit slab", parent.cell, ["Fe"], [45], parent.frac[:45], parent.flags[:45])
    target = {"id": "12", "signature": molecular_signature(parent)}
    assert not metrics(parent, target, slab)["checks"]["supported_non_linear_heavy_centers"]
    result = bend_branch(parent, center=46, fixed=45, branch=47, target_angle_deg=120.)
    assert metrics(result, target, slab)["checks"]["supported_non_linear_heavy_centers"]
