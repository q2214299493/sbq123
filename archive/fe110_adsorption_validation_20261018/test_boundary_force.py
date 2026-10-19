import copy
import json

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import write

from archive.fe110_adsorption_validation_20261018.boundary_force import bond_projection, force_frame
from archive.fe110_adsorption_validation_20261018.runtime import validate_scope, verify_labels
from archive.fe110_adsorption_validation_20261018.test_force24 import force_scope
from scripts.artifact_io import sha256_file


def static_scope():
    request, auth, digest, exception = copy.deepcopy(force_scope())
    request["document_kind"] = "adsorption_exact_static_force_comparison"
    request["samples"] = [{"sample_id": str(i), "source_name": "06_C"} for i in range(3)]
    exception.update(sample_count=3, source_names=["06_C"])
    return request, auth, digest, exception


def test_static_force_only_scope():
    validate_scope(*static_scope())


@pytest.mark.parametrize("change", ["optimization", "duplicate", "count", "source"])
def test_static_scope_expansion_rejected(change):
    request, auth, digest, exception = static_scope()
    if change == "optimization":
        request["geometry_cases"] = [{"name": "unapproved"}]
    elif change == "duplicate":
        request["samples"][0] = request["samples"][1]
    elif change == "count":
        request["samples"].pop()
    else:
        request["samples"][0]["source_name"] = "unapproved"
    with pytest.raises(ValueError):
        validate_scope(request, auth, digest, exception)


def test_static_labels_do_not_fabricate_xdatcar(tmp_path):
    atoms = Atoms("Fe45C2OH", positions=np.arange(147).reshape(49, 3)*.1, cell=np.eye(3)*30)
    atoms.set_constraint(FixAtoms(indices=range(18)))
    path = tmp_path / "POSCAR"
    write(path, atoms, format="vasp")
    row = {"sample_id": "unit_test", "structure_path": "POSCAR", "structure_sha256": sha256_file(path),
        "forces_eV_per_A": np.zeros((49, 3)).tolist(), "symbols": atoms.get_chemical_symbols(),
        "fixed_atom_indices_0based": list(range(18)), "electronic_converged": True, "geometry_review_pass": True,
        "source_OUTCAR_sha256": "a"*64, "source_name": "06_C", "source_job_id": "unit_test", "ionic_step": 1,
        "source_POSCAR_sha256": sha256_file(path), "source_INCAR_sha256": "b"*64, "source_force_table_sha256": "c"*64}
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"samples": [row]}))
    request = {"document_kind": "adsorption_exact_static_force_comparison", "samples": [row], "geometry_cases": [],
        "source_manifest_path": "source.json", "source_manifest_sha256": sha256_file(source)}
    verify_labels(tmp_path, request)
    assert "source_XDATCAR_sha256" not in row
    request["samples"] = [{**row, "source_INCAR_sha256": "d"*64}]
    with pytest.raises(ValueError, match="source_INCAR"):
        verify_labels(tmp_path, request)


def test_static_force_parser_keeps_printing_precision():
    block = "POSITION TOTAL-FORCE (eV/Angst)\n-----\n1.000000 2.000000 3.000000 .1 .2 .3\n-----\n"
    result = force_frame(block)
    assert result["position_tokens"] == [["1.000000", "2.000000", "3.000000"]]
    assert result["forces_eV_per_A"] == [[.1, .2, .3]]
    with pytest.raises(ValueError, match="one NSW=0"):
        force_frame(block + block)


def test_projection_sign_and_pbc():
    atoms = Atoms("CO", positions=[[9.5, 0, 0], [.5, 0, 0]], cell=np.eye(3)*10, pbc=True)
    assert bond_projection(atoms, [[1, 2, 0], [-1, 3, 0]], 0, 1) == pytest.approx(-1.)
    assert bond_projection(atoms, [[-1, 2, 0], [1, 3, 0]], 0, 1) == pytest.approx(1.)
    atoms.positions[1] = atoms.positions[0]
    with pytest.raises(ValueError, match="undefined"):
        bond_projection(atoms, np.zeros((2, 3)), 0, 1)
