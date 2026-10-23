from __future__ import annotations

import pytest
from ase.io import write

from archive.fe110_reico_followup_20261024 import analyze, review
from archive.fe110_reico_followup_20261024.collect import check_snapshot
from scripts.adsorption.collect_completed_batch import FILES
from scripts.artifact_io import sha256_file, sha256_text
from tests.test_reico_environment_audit import slab


def snapshot(status="DONE", returncode=0):
    stdout = f"JOBID USER STAT\n123456 user {status}\n"
    return {"stdout":stdout, "stdout_sha256":sha256_text(stdout), "returncode":returncode,
            "jobs":[{"job_id":"123456", "status":status}]}


def test_snapshot_success_uses_exact_job_output():
    result = snapshot()
    assert check_snapshot(result) is result


@pytest.mark.parametrize("returncode", [1, 255])
def test_failed_connection_never_becomes_empty_success_on_resume(returncode):
    with pytest.raises(ValueError, match="query incomplete"):
        check_snapshot(snapshot(returncode=returncode))


def test_missing_job_status_cannot_be_inferred():
    result = snapshot()
    result["jobs"][0]["status"] = "UNKNOWN_QUERY_RESULT"
    with pytest.raises(ValueError, match="query incomplete"):
        check_snapshot(result)


def test_scheduler_raw_hash_checked():
    result = snapshot()
    result["stdout"] += "modified"
    with pytest.raises(ValueError, match="hash changed"):
        check_snapshot(result)


def test_scheduler_status_cannot_be_reclassified():
    result = snapshot()
    result["jobs"][0]["status"] = "RUN"
    with pytest.raises(ValueError, match="differs from raw"):
        check_snapshot(result)


def label_fixture(tmp_path):
    write(tmp_path/"POSCAR", slab(), format="vasp")
    for name in FILES:
        if name != "POSCAR":
            (tmp_path/name).write_text("fixture\n", encoding="utf-8")
    hashes = {n:sha256_file(tmp_path/n) for n in FILES}
    source = {"sample_id":"family_0001_step000", "family_id":"family_0001", "partition":"train",
              "composition":"C2HO", "structure_sha256":hashes["POSCAR"]}
    receipt = {"job_id":"123456", "remote":{"files":{n:{"sha256":h} for n,h in hashes.items()}}}
    return source, receipt


def test_collected_file_hash_failure_stops_review(tmp_path):
    source, receipt = label_fixture(tmp_path)
    (tmp_path/"OUTCAR").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="source file changed"):
        review.review_case(source, receipt, tmp_path, "binding")


def test_source_geometry_hash_must_match_original_selection(tmp_path):
    source, receipt = label_fixture(tmp_path)
    source["structure_sha256"] = "0"*64
    with pytest.raises(ValueError, match="original selection"):
        review.review_case(source, receipt, tmp_path, "binding")


@pytest.mark.parametrize("positive_count,expected", [(45,"PASS"), (44,"MAGNETIC_REVIEW_REQUIRED")])
def test_nonpositive_Fe_moment_not_automatically_admitted(tmp_path, monkeypatch, positive_count, expected):
    source, receipt = label_fixture(tmp_path)
    monkeypatch.setattr(review, "validate_static", lambda *args: {"Fe_positive_moment_count":positive_count})
    result = review.review_case(source, receipt, tmp_path, "binding")
    assert result["data_qc_status"] == expected
    assert result["training_authorized"] is False and result["reportable_final_energy"] is False


def test_native_electronic_failure_preserved(tmp_path, monkeypatch):
    source, receipt = label_fixture(tmp_path)

    def failure(*args):
        raise ValueError("electronic convergence gate failed")

    monkeypatch.setattr(review, "validate_static", failure)
    monkeypatch.setattr(review, "final_scf_status", lambda *args: {"electronically_converged":False})
    result = review.review_case(source, receipt, tmp_path, "binding")
    assert result["data_qc_status"] == "REJECTED_OR_INCOMPLETE"
    assert result["SCF_diagnostic"]["electronically_converged"] is False


def test_reserved_label_never_enters_updated_training_view(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "isolate", lambda candidates,*args: (candidates, {"comparisons":0}))
    reserved = [{"partition":"development", "data_qc_status":"PASS"},
                {"partition":"final_test", "data_qc_status":"PASS"},
                {"partition":"train", "data_qc_status":"MAGNETIC_REVIEW_REQUIRED"}]
    assert analyze.isolated_new_training(reserved, tmp_path, [], None, {}, []) == []
