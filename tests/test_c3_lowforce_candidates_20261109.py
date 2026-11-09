"""Candidate data safety and original-byte binding regressions; no model/SSH."""
import numpy as np
import pytest

from archive.fe110_c3_lowforce_candidates_20261109.prepare import BOUNDARIES, check_boundaries, run, save_bytes
from archive.fe110_c3_lowforce_candidates_20261109.verify import force_slice
from archive.fe110_c3_lowforce_candidates_20261109.review import check_lineage


def test_resume_reuses_identical_bytes(tmp_path):
    path = tmp_path / "source/OUTCAR"
    save_bytes(path, b"original\r\nbytes\n")
    stamp = path.stat().st_mtime_ns
    save_bytes(path, b"original\r\nbytes\n")
    assert path.stat().st_mtime_ns == stamp


def test_changed_existing_source_is_preserved(tmp_path):
    path = tmp_path / "OUTCAR"
    save_bytes(path, b"original")
    with pytest.raises(ValueError, match="preserve changed"):
        save_bytes(path, b"changed")
    assert path.read_bytes() == b"original"


def test_unknown_scheduler_does_not_promote_candidate():
    check_boundaries({**BOUNDARIES, "force_unit": "eV/Angstrom", "terminal_scheduler_status": None})


@pytest.mark.parametrize("key", list(BOUNDARIES))
def test_promotion_flags_are_rejected(key):
    with pytest.raises(ValueError, match="boundary"):
        check_boundaries({**BOUNDARIES, key: True, "force_unit": "eV/Angstrom"})


def test_wrong_force_unit_is_rejected():
    with pytest.raises(ValueError, match="unit"):
        check_boundaries({**BOUNDARIES, "force_unit": "Hartree/Bohr"})


def test_original_force_slice_and_tamper_detection():
    table = b"POSITION TOTAL-FORCE\n----------------\n0 0 0 0.1 0.2 0.3\n1 0 0 -0.1 0 0\n"
    prefix = b"source header\n"
    row = {"source_force_byte_range": [len(prefix), len(prefix) + len(table)],
           "symbols": ["Fe", "C"], "forces_eV_per_A": [[.1, .2, .3], [-.1, 0, 0]]}
    raw, values = force_slice(prefix + table + b"footer", row)
    assert raw == table
    assert np.array_equal(values[:, 3:], row["forces_eV_per_A"])
    with pytest.raises(ValueError, match="original source bytes"):
        force_slice(prefix + table.replace(b"0.3", b"0.4") + b"footer", row)


def test_unknown_existing_directory_is_not_repurposed(tmp_path):
    path = tmp_path / "existing"
    path.mkdir()
    (path / "user_file").write_text("keep")
    with pytest.raises(ValueError, match="not this candidate package"):
        run(path)
    assert (path / "user_file").read_text() == "keep"


@pytest.mark.parametrize("change", ["job", "parent", "geometry", "bundle"])
def test_parent_continuation_binding_rejects_mismatch(change):
    collection = {"job_id": "9924387", "files": {"POSCAR": {"sha256": "geometry"}}}
    plan = {"source_job_id": "9922624", "source_CONTCAR_sha256": "geometry", "bundle_sha256": "bundle"}
    submission = {"receipt": {"job_id": "9924387", "bundle_sha256": "bundle"}}
    check_lineage(collection, plan, submission)
    if change == "job":
        collection["job_id"] = "other"
    elif change == "parent":
        plan["source_job_id"] = "other"
    elif change == "geometry":
        plan["source_CONTCAR_sha256"] = "other"
    else:
        plan["bundle_sha256"] = "other"
    with pytest.raises(ValueError):
        check_lineage(collection, plan, submission)
