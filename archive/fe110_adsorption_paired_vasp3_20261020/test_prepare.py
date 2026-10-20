import copy

import pytest

from scripts.artifact_io import load_json_object
from archive.fe110_adsorption_paired_vasp3_20261020.prepare import (
    ARMS, NAMES, SOURCE, check_pair, select_rows, verify_geometry,
)


def test_only_six_seed_outputs_selected():
    review = load_json_object(SOURCE / "geometry_comparison_review_v2.json")
    rows = select_rows(review)
    assert set(rows) == {(n, a) for n in NAMES for a in ARMS}
    assert all(r["origin"] == "seed" for r in rows.values())


def test_duplicate_or_unconverged_seed_rejected():
    review = load_json_object(SOURCE / "geometry_comparison_review_v2.json")
    rows = select_rows(review)
    invalid = copy.deepcopy(review)
    invalid["geometry"].append(copy.deepcopy(rows["06_C", "baseline"]))
    with pytest.raises(ValueError, match="unique"):
        select_rows(invalid)
    invalid = copy.deepcopy(review)
    next(r for r in invalid["geometry"] if r["origin"] == "seed")["converged"] = False
    with pytest.raises(ValueError, match="review"):
        select_rows(invalid)


def test_source_hash_tamper_rejected(tmp_path):
    path = tmp_path / "POSCAR"
    path.write_text("tampered")
    with pytest.raises(ValueError, match="bytes changed"):
        verify_geometry(path, path, {"final_POSCAR_sha256": "0" * 64})


def test_restart_artifact_rejected(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "WAVECAR").write_bytes(b"restart")
    with pytest.raises(ValueError, match="fresh"):
        check_pair(a, b)


def test_pair_method_mismatch_rejected(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "INCAR").write_text("SIGMA=0.20")
    (b / "INCAR").write_text("SIGMA=0.10")
    for name in ("KPOINTS", "POTCAR.spec", "script.lsf"):
        (a / name).write_text("same")
        (b / name).write_text("same")
    with pytest.raises(ValueError, match="inputs differ"):
        check_pair(a, b)
