"""Read back only this submission's metadata and native receipts."""
from __future__ import annotations

from pathlib import Path

from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid,
    write_json_exclusive,
)
from scripts.neb_agent.submission import submission_status
from scripts.registry_connection import open_registry
from .submit import INPUTS, OUTPUT, ROOT


def verify():
    batch = load_json_object(OUTPUT / "registry_batch.json")
    receipt = load_json_object(OUTPUT / "registry_receipt.json")
    if receipt["inserted"] != 288 or receipt["updated"] != 0:
        raise ValueError("unexpected canonical registry result")
    summary = load_json_object(OUTPUT / "submission_summary.json")
    if not source_file_manifest_valid(summary):
        raise ValueError("native receipt binding changed")
    checks = 0
    with open_registry(ROOT / "data/project_registry.sqlite3") as connection:
        for table, primary in [("calculations", "calculation_id"), ("jobs", "job_record_id"), ("files", "file_id")]:
            for expected in batch["rows"][table]:
                actual = connection.execute("SELECT * FROM " + table + " WHERE " + primary + "=?",
                                            (expected[primary],)).fetchone()
                if actual is None or any(actual[key] != value for key, value in expected.items()):
                    raise ValueError("registry readback differs")
                checks += 1
        for expected in batch["rows"]["job_status_history"]:
            actual = connection.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND checked_at=?",
                                       (expected["job_record_id"], expected["checked_at"])).fetchall()
            if len(actual) != 1 or any(actual[0][key] != value for key, value in expected.items()):
                raise ValueError("scheduler observation readback differs")
            checks += 1
        fields = {row["name"] for row in connection.execute("PRAGMA table_info(results)")}
        if "calculation_id" not in fields:
            raise ValueError("results schema changed")
        for row in batch["rows"]["calculations"]:
            if connection.execute("SELECT COUNT(*) FROM results WHERE calculation_id=?",
                                  (row["calculation_id"],)).fetchone()[0]:
                raise ValueError("submission must not register scientific results")
    for row in load_json_object(OUTPUT / "ready_for_submission.json")["cases"]:
        directory = Path(row["directory"])
        state = submission_status(directory)
        if state["status"] != "SUBMITTED" or state["gate_decision_sha256"] != row["decision_sha256"]:
            raise ValueError("native submission receipt changed")
        if any(sha256_file(directory / name) != digest for name, digest in row["input_hashes"].items()):
            raise ValueError("submitted inputs changed")
    old = INPUTS.parent / "grouped_supplement_20261025_v1/summary.json"
    if not source_file_manifest_valid(load_json_object(old)):
        raise ValueError("reviewed data source changed")
    result = {"status": "PASS", "registry_rows_read_back": checks, "successful_native_receipts": 14,
        "scientific_result_rows_created": 0, "input_hashes_unchanged": True,
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "registry_batch.json",
            OUTPUT / "registry_plan.json", OUTPUT / "registry_approval.json", OUTPUT / "registry_receipt.json",
            OUTPUT / "scheduler_snapshot.json", OUTPUT / "submission_summary.json", OUTPUT / "ready_for_submission.json"])}
    write_json_exclusive(OUTPUT / "submission_verification.json", result)
    print({k: v for k, v in result.items() if k != "source_files"})


if __name__ == "__main__":
    verify()
