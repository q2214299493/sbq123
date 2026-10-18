import copy

import numpy as np
import pytest

from scripts.adsorption.build_fe110_adsorption import Poscar

from archive.fe110_adsorption_validation_20261018.review import hydrogen_maps, surface_metrics


def synthetic_surface():
    # Test geometry only, never used as a scientific input.
    cell = np.diag([30., 30., 30.])
    fe = np.asarray([[2.5*i, 2.5*j, 2.*k] for k in range(5) for i in range(3) for j in range(3)])
    ads = np.asarray([[5., 5., 11.], [6.4, 5., 11.], [7.8, 5., 11.], [4.05, 5., 11.], [6.4, 6.09, 11.]])
    flags = [("F", "F", "F")] * 18 + [("T", "T", "T")] * 27
    slab = Poscar("synthetic", cell, ["Fe"], [45], fe @ np.linalg.inv(cell), flags)
    pose = Poscar("synthetic", cell, ["Fe", "O", "C", "H"], [45, 1, 2, 2],
                  np.vstack([fe, ads]) @ np.linalg.inv(cell), flags + [("T", "T", "T")] * 5)
    return slab, pose


def test_hydrogen_coordination_roles_are_not_silently_fitted_away():
    _, pose = synthetic_surface()
    assert hydrogen_maps(pose) == [[0, 1, 2, 3, 4]]


def test_adsorption_height_is_not_removed_or_fe_averaged():
    slab, reference = synthetic_surface()
    candidate = copy.deepcopy(reference)
    candidate.frac[45:, 2] += .5 / 30
    result = surface_metrics(reference, candidate, slab, [(np.eye(3), np.zeros(3))])
    assert result["adsorbate_RMSD_A"] == pytest.approx(.5)
    assert result["movable_Fe_RMSD_A"] == 0
    assert result["same_graph_as_DFT"] is True


def test_xy_periodic_representations_are_equivalent():
    slab, reference = synthetic_surface()
    candidate = copy.deepcopy(reference)
    candidate.frac[:, 0] += 1
    result = surface_metrics(reference, candidate, slab, [(np.eye(3), np.zeros(3))])
    assert result["adsorbate_RMSD_A"] < 1e-12


def test_changed_graph_is_explicit_not_accepted_by_low_rmsd():
    slab, reference = synthetic_surface()
    candidate = copy.deepcopy(reference)
    candidate.frac[49, 2] += 3 / 30
    result = surface_metrics(reference, candidate, slab, [(np.eye(3), np.zeros(3))])
    assert result["same_graph_as_DFT"] is False
