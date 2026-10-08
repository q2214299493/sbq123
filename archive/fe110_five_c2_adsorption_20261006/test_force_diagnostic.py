import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms

from archive.fe110_five_c2_adsorption_20261006.prepare_c2_force_diagnostic import verify_frame


def fixture():
    atoms = Atoms("Fe18C2H", positions=np.zeros((21, 3)), cell=[8, 8, 23], pbc=[True, True, False])
    atoms.set_constraint(FixAtoms(indices=range(18)))
    frame = {
        "positions_A": atoms.positions.tolist(),
        "forces_eV_per_A": np.zeros((21, 3)).tolist(),
        "position_tokens": [["0.00000"] * 3 for _ in atoms],
    }
    return atoms, frame


def test_rounding_and_xy_periodic_equivalence():
    atoms, frame = fixture()
    frame["positions_A"][18] = [8.000004, -8.000004, 0.000004]
    assert verify_frame(atoms, frame).shape == (21, 3)


@pytest.mark.parametrize("bad", ["shape", "nonfinite", "geometry", "mask", "z_wrap"])
def test_reject_invalid_frame(bad):
    atoms, frame = fixture()
    if bad == "shape":
        frame["forces_eV_per_A"].pop()
    elif bad == "nonfinite":
        frame["forces_eV_per_A"][18][0] = float("nan")
    elif bad == "geometry":
        frame["positions_A"][18][0] = 0.001
    elif bad == "mask":
        atoms.set_constraint(FixAtoms(indices=range(17)))
    else:
        frame["positions_A"][18][2] = 23
    with pytest.raises(ValueError):
        verify_frame(atoms, frame)
