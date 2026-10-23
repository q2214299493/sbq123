import pytest
import numpy as np
from ase import Atoms

from archive.fe110_c3_source_recovery_20261023.review import candidate_status, fragments, rounding_bounds


@pytest.mark.parametrize("ionic,graph,force,anchor", [
    (True, True, .015, True),
    (False, True, .015, False),
    (True, False, .015, False),
    (True, True, .2, False),
])
def test_raw_labels_are_separate_from_stable_anchor(ionic, graph, force, anchor):
    value = candidate_status(technical=True, ionic=ionic, unchanged_graph=graph, fmax=force)
    assert value["raw_force_label_candidate"] is True
    assert value["intact_C3_anchor_candidate"] is anchor
    assert value["scientific_acceptance"] is False


def test_bad_electronic_or_source_evidence_never_qualifies():
    value = candidate_status(technical=False, ionic=True, unchanged_graph=True, fmax=.001)
    assert not value["raw_force_label_candidate"] and not value["intact_C3_anchor_candidate"]


def test_fragment_formula_distinguishes_composition_from_connected_C3():
    atoms = Atoms(["Fe"] * 45 + ["C", "C", "C", "O", "H", "H"])
    assert fragments(atoms, [(0, 1), (0, 4), (1, 5), (2, 3)]) == ["C2H2", "CO"]


def test_coordinate_tolerance_follows_actual_printed_precision():
    bounds = rounding_bounds([["1.23456", "2.34567", "3.45678"], ["1.234560", "2.345670", "3.456780"]])
    assert bounds[0] == pytest.approx(np.sqrt(3) * .5e-5)
    assert bounds[1] == pytest.approx(np.sqrt(3) * .5e-6)
    assert 7.9e-6 < bounds[0] and 7.9e-6 > bounds[1]


def test_scientific_notation_position_precision():
    bounds = rounding_bounds([["1.23456e1", "2.34567e1", "3.45678e1"]])
    assert bounds[0] == pytest.approx(np.sqrt(3) * .5e-4)
