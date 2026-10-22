import importlib.util

import pytest
from ase.io import write

from archive.fe110_reico_sampling93_20261022.prepare import ROOT
from archive.fe110_reico_sampling93_20261022.prepare_labels import prepare_one
from scripts.artifact_io import sha256_file
from scripts.neb_agent.submission import preflight as canonical_preflight
from scripts.registry_schema import migrate_registry
from scripts.vasp_result_gate import read_incar_values
from tests.test_reico_sampling import atoms_fixture


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import archive.fe110_reico_sampling93_20261022.prepare_labels as module
    database = tmp_path / "isolated_learning.sqlite3"
    migrate_registry(database)
    monkeypatch.setattr(module, "preflight", lambda workdir, kind: canonical_preflight(
        workdir, kind, learning_database=database))
    source = tmp_path / "unit_geometry.vasp"
    write(source, atoms_fixture(), format="vasp", direct=True)
    row = {"sample_id": "family_0001_step010", "structure_path": str(source),
           "structure_sha256": sha256_file(source), "already_DFT_labeled": False,
           "partition": "development", "family_id": "family_0001", "composition": "CH", "step": 10}
    destination = tmp_path / "inputs"
    destination.mkdir()
    owner = ROOT / "skills/fe-vasp-incar-custodian/scripts/incar_custodian.py"
    spec = importlib.util.spec_from_file_location("unit_reico_custodian", owner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return row, destination, module, owner


def test_exact_static_branch_and_completed_preparation_resume(setup):
    row, destination, owner, owner_path = setup
    result = prepare_one(row, destination, "a" * 64, owner, owner_path)
    assert result["status"] == "PREPARED_NOT_SUBMITTED" and result["partition"] == "development"
    directory = destination / row["sample_id"]
    incar = read_incar_values(directory / "INCAR")
    assert incar["NSW"] == "0" and incar["IBRION"] == "-1" and incar["ISPIN"] == "2"
    assert float(incar["SIGMA"]) == .20 and float(incar["EDIFF"]) == 1e-6
    assert sha256_file(directory / "POSCAR") == row["structure_sha256"]
    hashes = {p.name: sha256_file(p) for p in directory.iterdir() if p.is_file()}
    assert prepare_one(row, destination, "a" * 64, owner, owner_path) == result
    assert hashes == {p.name: sha256_file(p) for p in directory.iterdir() if p.is_file()}


def test_changed_geometry_is_rejected_before_input_creation(setup):
    row, destination, owner, owner_path = setup
    row["structure_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source structure changed"):
        prepare_one(row, destination, "a" * 64, owner, owner_path)
    assert list(destination.iterdir()) == []


def test_changed_selection_cannot_rebind_existing_inputs(setup):
    row, destination, owner, owner_path = setup
    prepare_one(row, destination, "a" * 64, owner, owner_path)
    with pytest.raises(ValueError, match="existing input preparation changed"):
        prepare_one(row, destination, "b" * 64, owner, owner_path)
