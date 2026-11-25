import subprocess

import pytest

from archive.fe110_reico_sampling93_20261022 import submission_review as review
from scripts.artifact_io import load_json_object


@pytest.fixture
def receipts(tmp_path, monkeypatch):
    ready = [{"sample_id": name, "decision_sha256": "a" * 64,
              "potcar_source": "~/sbq/unit/POTCAR", "potcar_sha256": "b" * 64} for name in ("one", "two")]
    records = {row["sample_id"]: {"status": "SUBMITTED", "job_id": str(1001 + i),
                "gate_decision_sha256": row["decision_sha256"], "potcar_source": row["potcar_source"],
                "potcar_sha256": row["potcar_sha256"], "remote_dir": review.runner.REMOTE + "/" + row["sample_id"]}
               for i, row in enumerate(ready)}
    monkeypatch.setattr(review, "DEST", tmp_path)
    monkeypatch.setattr(review.runner, "COUNT", 2)
    monkeypatch.setattr(review.runner, "checked_ready", lambda: ready)
    monkeypatch.setattr(review.runner, "submission_status", lambda directory: records[directory.name])
    return tmp_path, records


def test_exact_id_batch_query_uses_canonical_evidence_validation(receipts, monkeypatch):
    dest, records = receipts
    raw = "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n1001 unit RUN normal login 32*node unit Oct23\n1002 unit PEND normal login - unit Oct23\n"

    def query(argv, **kwargs):
        assert argv[-4:] == ["bjobs", "-a", "1001", "1002"]
        return subprocess.CompletedProcess(argv, 0, raw, "")

    monkeypatch.setattr(review.subprocess, "run", query)
    review.collect()
    snapshot = load_json_object(dest / "scheduler_snapshot.json")
    summary = load_json_object(dest / "submission_summary.json")
    assert snapshot["query"]["stdout"] == raw
    assert snapshot["status_counts"] == {"RUN": 1, "PEND": 1}
    assert summary["new_DFT_jobs_submitted"] == 2
    assert not summary["scientific_acceptance"]
    assert not summary["training_performed"]


@pytest.mark.parametrize("failure", ["unknown", "foreign_target", "duplicate_id"])
def test_incomplete_or_unbound_receipts_fail_before_remote_query(receipts, monkeypatch, failure):
    dest, records = receipts
    if failure == "unknown":
        records["two"] = {"status": "UNKNOWN_NEEDS_RECONCILIATION"}
    elif failure == "foreign_target":
        records["two"]["remote_dir"] += "_changed"
    else:
        records["two"]["job_id"] = records["one"]["job_id"]
    monkeypatch.setattr(review.subprocess, "run", lambda *a, **kw: pytest.fail("no remote query before complete receipt validation"))
    with pytest.raises(ValueError):
        review.collect()
    assert not (dest / "submission_summary.json").exists()


def test_partial_checkpoint_keeps_rejections_separate_from_real_jobs(receipts, monkeypatch):
    dest, records = receipts
    records["two"] = {"status": "UNKNOWN_NEEDS_RECONCILIATION"}
    raw = "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n1001 unit RUN normal login 32*node unit Oct23\n"
    monkeypatch.setattr(review.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, raw, ""))
    review.collect(partial=True)
    summary = load_json_object(dest / "initial_submission_checkpoint.json")
    assert summary["status"] == "PARTIAL_SUBMISSION_STOPPED"
    assert summary["new_DFT_jobs_submitted"] == 1
    assert summary["outstanding"] == [{"sample_id": "two", "submission_state": "UNKNOWN_NEEDS_RECONCILIATION"}]
    assert not (dest / "submission_summary.json").exists()
