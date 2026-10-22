import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import write

from scripts.adsorption.reico_probe_review import compare_forces, projected_contacts, validate_static


@pytest.mark.parametrize("factor,opposite,error", [(1., 0, 0.), (2., 0, 1.), (-1., 2, 2.)])
def test_adsorbate_scale_and_reversal_are_not_diluted_by_fe(factor, opposite, error):
    reference = np.array([[100., 0, 0], [3., 4., 0], [0, 0, 2.]])
    prediction = reference.copy()
    prediction[0] = [-100., 0, 0]
    prediction[1:] *= factor
    result = compare_forces(reference, prediction, ["Fe", "C", "H"], [])
    group = result["groups"]["adsorbate"]
    assert group["relative_vector_L2_error"] == pytest.approx(error)
    assert group["opposite_direction_count"] == opposite
    assert group["local_descent_first_order"] == (factor > 0)


def test_zero_predicted_force_has_undefined_direction():
    result = compare_forces([[1., 0, 0]], [[0., 0, 0]], ["C"], [])
    assert result["adsorbate_atoms"][0]["cosine"] is None
    assert result["groups"]["adsorbate"]["defined_direction_count"] == 0
    assert result["groups"]["adsorbate"]["relative_vector_L2_error"] == 1.


def test_invalid_shape_and_nonfinite_force_are_rejected():
    with pytest.raises(ValueError, match="shape"):
        compare_forces([[1., 0, 0]], [[1., 0]], ["C"], [])
    with pytest.raises(ValueError, match="nonfinite"):
        compare_forces([[1., 0, 0]], [[np.nan, 0, 0]], ["C"], [])


def test_contact_projection_sign_is_separation():
    positions = [[10. + i, 10., 10.] for i in range(45)] + [[0., 0, 0], [1., 0, 0]]
    atoms = Atoms(["Fe"] * 45 + ["C", "H"], positions=positions)
    reference = np.zeros((47, 3))
    reference[45, 0], reference[46, 0] = -2., 2.
    result = projected_contacts(atoms, reference, -reference, {"C-Fe": 1.6, "Fe-H": 1.3, "C-H": .85})
    assert len(result) == 1
    assert result[0]["indices_0based"] == [45, 46]
    assert result[0]["DFT_separating_projection_eV_A"] == 4.
    assert result[0]["model_separating_projection_eV_A"] == -4.


def test_nonstatic_input_rejected_before_output_read(tmp_path):
    atoms = Atoms(["Fe"] * 45 + ["C"], positions=[[i, 0., 0.] for i in range(46)], cell=[60, 20, 20])
    atoms.set_constraint(FixAtoms(indices=range(18)))
    write(tmp_path / "POSCAR", atoms, format="vasp")
    (tmp_path / "INCAR").write_text("NSW=100\nIBRION=2\nISPIN=2\nISMEAR=1\nSIGMA=.20\n")
    with pytest.raises(ValueError, match="static branch"):
        validate_static(tmp_path, atoms.get_chemical_symbols())
