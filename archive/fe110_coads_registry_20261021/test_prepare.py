import numpy as np

from archive.fe110_coads_registry_20261021.prepare import fragments
from scripts.adsorption.build_fe110_adsorption import Poscar


def pose(adsorbate_positions):
    positions = np.vstack([np.zeros((45, 3)), np.asarray(adsorbate_positions)])
    return Poscar("synthetic chemistry only", np.eye(3) * 100,
                  ["Fe", "C", "O", "H"], [45, 2, 1, 1], positions / 100,
                  [("F", "F", "F")] * 18 + [("T", "T", "T")] * 31)


def test_free_h_not_silently_attached_to_carbon():
    assert fragments(pose([[0, 0, 0], [5, 0, 0], [1.2, 0, 0], [8, 0, 0]])) == ["C", "CO", "H"]


def test_ch_co_reclassification_has_different_identity():
    assert fragments(pose([[0, 0, 0], [5, 0, 0], [1.2, 0, 0], [6.1, 0, 0]])) == ["CH", "CO"]


def test_intact_c_o_ch_is_one_fragment():
    assert fragments(pose([[0, 0, 0], [2.7, 0, 0], [1.35, 0, 0], [3.8, 0, 0]])) == ["C2HO"]
