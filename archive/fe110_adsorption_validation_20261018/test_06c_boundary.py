import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.constraints import FixAtoms

from archive.fe110_adsorption_validation_20261018.prepare_06c_boundary import choose, validate_frame


def atoms():
    value = Atoms("Fe45C2OH", positions=np.arange(147).reshape(49, 3) * .1, cell=np.eye(3) * 30, pbc=True)
    value.set_constraint(FixAtoms(indices=range(18)))
    value.calc = SinglePointCalculator(value, forces=np.zeros((49, 3)), energy=0.)
    return value


def test_unchanged_saved_force_frame():
    value = atoms()
    assert validate_frame(value, value).shape == (49, 3)


@pytest.mark.parametrize("change", ["mask", "cell", "pbc", "fixed_position", "nonfinite", "incomplete", "order"])
def test_changed_source_rejected(change):
    initial = atoms()
    value = initial.copy()
    value.calc = SinglePointCalculator(value, forces=np.zeros((49, 3)))
    if change == "mask":
        value.set_constraint(FixAtoms(indices=range(19)))
    elif change == "cell":
        value.cell[0, 0] += .01
    elif change == "pbc":
        value.pbc[2] = False
    elif change == "fixed_position":
        value.positions[0, 0] += .01
    elif change == "nonfinite":
        value.calc.results["forces"][45, 0] = np.nan
    elif change == "incomplete":
        value.calc.results["forces"] = np.zeros((48, 3))
    else:
        value[45].symbol = "O"
    with pytest.raises(ValueError):
        validate_frame(value, initial)


def test_real_movable_change_is_allowed_for_force_diagnosis():
    initial = atoms()
    value = initial.copy()
    value.positions[46, 0] += 1.
    value.calc = SinglePointCalculator(value, forces=np.zeros((49, 3)))
    validate_frame(value, initial)


def test_boundary_preserves_first_persistent_loss_and_final():
    rows = [{"graph_adsorbate_local": [1]}, {"graph_adsorbate_local": [1]},
            {"graph_adsorbate_local": [2]}, {"graph_adsorbate_local": [2]}, {"graph_adsorbate_local": [3]}]
    assert choose(rows) == [("before", 1), ("after", 2), ("final", 4)]


def test_one_frame_graph_warning_is_not_persistent_loss():
    rows = [{"graph_adsorbate_local": value} for value in ([1], [2], [1], [2], [3])]
    assert choose(rows) == [("before", 2), ("after", 3), ("final", 4)]


@pytest.mark.parametrize("graphs", [([1], [1], [1]), ([1], [2]), ([1], [2], [1])])
def test_no_invented_boundary_or_duplicate_final(graphs):
    with pytest.raises(ValueError):
        choose([{"graph_adsorbate_local": value} for value in graphs])
