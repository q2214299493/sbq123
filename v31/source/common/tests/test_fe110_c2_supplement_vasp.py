"""Actual three-candidate VASP package; no calculations or external submissions."""
import json
import shutil
from pathlib import Path

import pytest
from ase.io import read

from archive.fe110_five_c2_adsorption_20261006 import prepare_supplement_vasp as batch
from scripts.adsorption.preflight_fe110_adsorption import preflight as adsorption_preflight
from scripts.artifact_io import sha256_file
from scripts.neb_agent.submission import InputBundle
from scripts.ts_strategy_engine.execution_gate import validate_decision

BASE = Path(__file__).resolve().parents[1] / "calculations/fe110_five_c2_adsorption_20261006"
DEST = BASE / "vasp_supplement_v1"


@pytest.mark.parametrize("name", ["01_extra1", "02_extra2", "03_extra1"])
def test_actual_candidate_input_and_gate(name, tmp_path):
    run = DEST / name
    assert (run / "POSCAR").read_bytes() == (BASE / "gpu_supplement_v1" / name / "output/job_2142/POSCAR").read_bytes()
    atoms = read(run / "POSCAR", format="vasp")
    assert len(atoms.constraints) == 1
    assert list(atoms.constraints[0].get_indices()) == list(range(18))
    manifest = json.loads((run / "candidate_manifest.json").read_text(encoding="utf-8"))
    assert manifest["geometry_checks"]["pass"]
    assert manifest["duplicate_status"] == "UNIQUE_REVIEWED_GPU_CANDIDATE"
    assert manifest["source_sha256"] == sha256_file(run / "POSCAR")
    for filename in ("POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "script.lsf", "candidate_manifest.json"):
        shutil.copyfile(run / filename, tmp_path / filename)
    # Older published preflight writes its report; use a temporary copy so
    # neither implementation can overwrite a frozen production artifact.
    assert adsorption_preflight(tmp_path)["passed"]
    # Production retry-history was checked at submission. Portable tests never
    # create, copy or replace that production database to check the input bundle.
    report = json.loads((run / "submission_preflight.json").read_text(encoding="utf-8"))
    assert report["passed"]
    InputBundle.from_preflight(report).verify(run)
    decision = json.loads((run / "decision.json").read_text(encoding="utf-8"))
    validate_decision(decision)
    assert decision["ALLOWED_ACTIONS"] == ["SUBMIT_VASP"]
    authorization = json.loads((run / "user_execution_authorization.json").read_text(encoding="utf-8"))
    assert authorization["calculation_kind"] == "adsorption_relaxation"
    incar = (run / "INCAR").read_text()
    assert "SIGMA = 0.2" in incar and "ENCUT = 400" in incar
    assert "EDIFFG = -0.02" in incar and "ALGO = Fast" in incar
    script = (run / "script.lsf").read_text()
    assert "NP=32\n" in script and "NP_PER_NODE=32\n" in script


def test_excluded_candidates_and_exclusive_preparation():
    doc = json.loads((DEST / "batch_manifest.json").read_text())
    assert [x["name"] for x in doc["entries"]] == batch.NAMES
    assert all(x["cores"] == 32 for x in doc["entries"])
    with pytest.raises(FileExistsError, match="Do not overwrite"):
        batch.prepare()
