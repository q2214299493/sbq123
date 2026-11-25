import numpy as np
import pytest

from scripts.adsorption.build_fe110_adsorption import Poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature
from scripts.adsorption.review_completed_batch import surface_equivalence


@pytest.fixture
def structures():
    cell = np.diag([9., 9., 24.])
    iron = np.array([[x / 3, y / 3, (3 + z) / 24] for z in range(5) for x in range(3) for y in range(3)])
    clean = Poscar("synthetic clean", cell, ["Fe"], [45], iron, [("F", "F", "F")] * 18 + [("T", "T", "T")] * 27)
    ads = np.array([[1., 1., 9.], [2.4, 1., 9.], [3.6, 1., 9.], [1., 1., 10.1]])
    pose = Poscar("synthetic CHCO", cell, ["Fe", "C", "O", "H"], [45, 2, 1, 1],
                  np.concatenate([iron, ads @ np.linalg.inv(cell)]), clean.flags + [("T", "T", "T")] * 4)
    return clean, pose


def transformed(pose, delta):
    return Poscar(pose.comment, pose.cell.copy(), pose.symbols.copy(), pose.counts.copy(),
                  pose.frac + delta, pose.flags.copy())


def test_exact_structure_has_zero_surface_rmsd(structures):
    clean, pose = structures
    score = surface_equivalence(pose, pose, clean, [(np.eye(3), np.zeros(3))])
    assert score == {"adsorbate_RMSD_A": 0., "slab_RMSD_A": 0., "slab_max_displacement_A": 0.}


def test_periodic_surface_translation_preserves_equivalence(structures):
    clean, pose = structures
    shifted = transformed(pose, np.array([1 / 3, 0., 0.]))
    # A different surface site in the same fixed slab, not a shifted fixed layer.
    shifted.frac[:45] = pose.frac[:45]
    scores = surface_equivalence(pose, shifted, clean,
                                [(np.eye(3), np.zeros(3)), (np.eye(3), np.array([-1 / 3, 0., 0.]))])
    assert scores["adsorbate_RMSD_A"] < 1e-12
    assert scores["slab_RMSD_A"] < 1e-12


def test_adsorbate_height_is_not_fitted_away(structures):
    clean, pose = structures
    shifted = transformed(pose, np.zeros(3))
    shifted.frac[45:, 2] += .6 / pose.cell[2, 2]
    scores = surface_equivalence(pose, shifted, clean, [(np.eye(3), np.zeros(3))])
    assert scores["adsorbate_RMSD_A"] == pytest.approx(.6)


def test_free_molecular_rotation_is_not_duplicate(structures):
    clean, pose = structures
    rotated = transformed(pose, np.zeros(3))
    cart = rotated.frac @ rotated.cell
    cart[45:, :2] = (cart[45:, :2] - cart[45, :2]) @ np.array([[0., 1.], [-1., 0.]]) + cart[45, :2]
    rotated.frac[:] = cart @ np.linalg.inv(rotated.cell)
    scores = surface_equivalence(pose, rotated, clean, [(np.eye(3), np.zeros(3))])
    assert scores["adsorbate_RMSD_A"] > .2


def test_same_operation_must_match_the_relaxed_fe_environment(structures):
    clean, pose = structures
    distorted = transformed(pose, np.zeros(3))
    distorted.frac[18:45, 0] += .5 / pose.cell[0, 0]
    scores = surface_equivalence(pose, distorted, clean, [(np.eye(3), np.zeros(3))])
    assert scores["adsorbate_RMSD_A"] == 0
    assert scores["slab_RMSD_A"] > .2


def test_invalid_clean_slab_symmetry_rejected(structures):
    clean, pose = structures
    with pytest.raises(ValueError, match="bijectively"):
        surface_equivalence(pose, pose, clean, [(np.eye(3), np.array([.12, 0., 0.]))])


def test_equal_formula_does_not_hide_hydrogen_rearrangement(structures):
    _, pose = structures
    moved = transformed(pose, np.zeros(3))
    moved.frac[48] = np.array([3.6, 1., 10.]) @ np.linalg.inv(pose.cell)
    assert molecular_signature(pose) != molecular_signature(moved)
