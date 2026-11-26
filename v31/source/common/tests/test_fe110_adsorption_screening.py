from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.adsorption.preflight_fe110_adsorption import preflight
from scripts.vasp_inputs import build_fe110_adsorption_relaxation


def prepare(path: Path, *, screening: bool = True) -> None:
    coordinates = ["0 0 0 F F F"] * 18 + ["0.2 0.2 0.6 T T T"] * 33
    (path / "POSCAR").write_text(
        "C3 screening fixture\n1.0\n10 0 0\n0 10 0\n0 0 20\n"
        "Fe C O H\n45 3 1 2\nSelective dynamics\nDirect\n"
        + "\n".join(coordinates) + "\n", encoding="ascii",
    )
    metadata = build_fe110_adsorption_relaxation(
        path, screening=screening, write_local_moments=True,
    )
    (path / "candidate_manifest.json").write_text(
        json.dumps({key: metadata[key] for key in ("relaxation_stage", "write_local_moments")}),
        encoding="utf-8",
    )


@pytest.mark.parametrize("screening,nsw", [(True, 80), (False, 300)])
def test_c3_stage_and_magnetic_output(tmp_path, screening, nsw):
    prepare(tmp_path, screening=screening)
    report = preflight(tmp_path, write_report=False)
    assert report["passed"], report["errors"]
    incar = (tmp_path / "INCAR").read_text(encoding="ascii")
    assert f"NSW = {nsw}\n" in incar
    assert "LORBIT = 11\n" in incar
    assert "EDIFFG = -0.02\n" in incar
    assert "MAGMOM = 45*2.2 3*0.0 1*0.0 2*0.0\n" in incar


@pytest.mark.parametrize("old,new,error", [
    ("NSW = 80", "NSW = 300", "INCAR_MISMATCH:NSW"),
    ("EDIFFG = -0.02", "EDIFFG = -0.05", "INCAR_MISMATCH:EDIFFG"),
    ("LORBIT = 11", "LORBIT = 10", "INCAR_MISMATCH:LORBIT"),
    ("ISPIN = 2", "ISPIN = 1", "INCAR_MISMATCH:ISPIN"),
])
def test_screening_rejects_unapproved_method_or_budget(tmp_path, old, new, error):
    prepare(tmp_path)
    p = tmp_path / "INCAR"
    p.write_text(p.read_text(encoding="ascii").replace(old, new), encoding="ascii")
    assert error in preflight(tmp_path, write_report=False)["errors"]


@pytest.mark.parametrize("manifest,error", [
    ({}, "INCAR_MISMATCH:NSW"),
    ({"relaxation_stage": "custom"}, "UNKNOWN_RELAXATION_STAGE"),
    ({"relaxation_stage": "screening", "write_local_moments": "yes"}, "INVALID_LOCAL_MOMENT_FLAG"),
    ([], "INVALID_CANDIDATE_MANIFEST"),
])
def test_stage_manifest_is_required_and_validated(tmp_path, manifest, error):
    prepare(tmp_path)
    (tmp_path / "candidate_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert any(item.startswith(error) for item in preflight(tmp_path, write_report=False)["errors"])


def test_unified_preflight_applies_same_screening_gate(tmp_path):
    from scripts.neb_agent import submission
    from scripts.registry_schema import migrate_registry

    prepare(tmp_path)
    database = tmp_path / "learning.sqlite3"
    migrate_registry(database)
    report = submission.preflight(tmp_path, "adsorption_relaxation", learning_database=database, write_report=False)
    assert report["passed"], report["errors"]
    assert report["adsorption_hard_gate"]["relaxation_stage"] == "screening"
    (tmp_path / "INCAR").write_text(
        (tmp_path / "INCAR").read_text(encoding="ascii").replace("SIGMA = 0.2", "SIGMA = 0.1"), encoding="ascii",
    )
    failed = submission.preflight(tmp_path, "adsorption_relaxation", learning_database=database, write_report=False)
    assert not failed["passed"]
    assert "INCAR_MISMATCH:SIGMA" in failed["errors"]
