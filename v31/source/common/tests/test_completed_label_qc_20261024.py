from __future__ import annotations

import pytest

from archive.fe110_completed_label_qc_20261024 import run as batch
from scripts.artifact_io import sha256_text


def receipt(tmp_path, sid="family_0001_step000", job="123456"):
    return {"sample_id": sid, "workdir": str(tmp_path / "recovery" / sid), "job_id": job,
            "server_alias": batch.HOST, "scheduler": "LSF", "status": "SUBMITTED",
            "remote_dir": "~/sbq/Fe110/recovery/" + sid, "potcar_sha256": "a" * 64}


def test_fresh_recovery_directory_is_used_instead_of_old_unknown_directory(monkeypatch, tmp_path):
    record = receipt(tmp_path)
    visited = []

    def status(directory):
        visited.append(directory)
        return {k: v for k, v in record.items() if k not in {"sample_id", "workdir"}}

    monkeypatch.setattr(batch, "submission_status", status)
    result = batch.pending_rows([{"sample_id": record["sample_id"]}], [], {"records": [record]})
    assert result[0]["workdir"] == record["workdir"]
    assert str(visited[0]) == record["workdir"]


def test_previously_reviewed_label_not_collected_again(monkeypatch, tmp_path):
    record = receipt(tmp_path)
    monkeypatch.setattr(batch, "submission_status", lambda path: {k: v for k, v in record.items()
                                                                  if k not in {"sample_id", "workdir"}})
    assert batch.pending_rows([{"sample_id": record["sample_id"]}],
                              [{"sample_id": record["sample_id"]}], {"records": [record]}) == []


def test_unknown_native_attempt_cannot_enter_collection_scope(monkeypatch, tmp_path):
    record = receipt(tmp_path)
    monkeypatch.setattr(batch, "submission_status", lambda path: {"status": "UNKNOWN_NEEDS_RECONCILIATION"})
    with pytest.raises(ValueError, match="native success receipt changed"):
        batch.pending_rows([{"sample_id": record["sample_id"]}], [], {"records": [record]})


def test_duplicate_logical_sample_rejected(monkeypatch, tmp_path):
    record = receipt(tmp_path)
    monkeypatch.setattr(batch, "submission_status", lambda path: {k: v for k, v in record.items()
                                                                  if k not in {"sample_id", "workdir"}})
    with pytest.raises(ValueError, match="duplicate logical sample"):
        batch.pending_rows([{"sample_id": record["sample_id"]}], [], {"records": [record, record]})


def test_running_job_not_collected_as_completed(monkeypatch, tmp_path):
    stdout = "JOBID USER STAT\n123456 user RUN\n"
    current = {"checked_at": "2026-10-24T08:00:00+00:00",
               "command": ["ssh", batch.HOST, "bjobs", "-a", "123456"], "returncode": 0,
               "stdout": stdout, "stderr": "", "stdout_sha256": sha256_text(stdout)}
    row = {"name": "family_0001_step000", "job_id": "123456", "status": "RUN"}
    monkeypatch.setattr(batch, "collect_one", lambda *args: pytest.fail("running job collected"))
    with pytest.raises(ValueError):
        batch.process_one(row, {}, {}, tmp_path, tmp_path / "key", current, "binding")


def test_only_train_pass_labels_reach_isolation():
    from archive.fe110_completed_label_qc_20261024.finalize import training_candidates
    rows = [{"partition": "development", "data_qc_status": "PASS"},
            {"partition": "final_test", "data_qc_status": "PASS"},
            {"partition": "train", "data_qc_status": "MAGNETIC_REVIEW_REQUIRED"}]
    assert training_candidates(rows) == []


def test_force_bin_uses_all_movable_atoms_and_preserves_magnetic_grade():
    import numpy as np
    from archive.fe110_completed_label_qc_20261024.finalize import training_candidates
    forces = np.zeros((46, 3))
    forces[0, 0] = 100
    forces[18, 0] = 2
    forces[45, 0] = 1
    row = {"partition": "train", "data_qc_status": "PASS", "forces_eV_per_A": forces.tolist(),
           "magnetic_review_level": "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"}
    result = training_candidates([row])
    assert result[0]["movable_fmax_eV_A"] == 2
    assert result[0]["magnetic_review_level"] == row["magnetic_review_level"]
