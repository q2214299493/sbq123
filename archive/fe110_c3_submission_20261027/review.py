"""Register one native submission's provenance without accepting results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess

from archive.fe110_reico_sampling93_20261022.submission_review import file_row
from scripts.aqcat25_ts_schema import validate_document
from scripts.artifact_io import load_json_object, sha256_text, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from scripts.neb_agent.submission import submission_status
from scripts.registry_connection import open_registry
from scripts.registry_write import plan_registry_batch
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence
from scripts.state_manager.job_lifecycle import JOB_ALIASES
from .submit import AUTH, BUNDLE, DIRECTORY, HOST, OUTPUT, PREP, REMOTE, ROOT


def collect():
    summary = load_json_object(OUTPUT / "submission_summary.json")
    if not source_file_manifest_valid(summary):
        raise ValueError("native receipt binding changed")
    receipt = summary["receipt"]
    argv = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "-o", "ControlMaster=no",
            "-o", "ControlPath=none", HOST, "bjobs", "-a", receipt["job_id"]]
    process = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40, check=False)
    query = {"argv": argv, "returncode": process.returncode, "stdout": process.stdout,
        "stderr": process.stderr, "stdout_sha256": sha256_text(process.stdout)}
    write_json_exclusive(OUTPUT / "scheduler_query.json", query)
    if process.returncode:
        raise ValueError("exact-ID scheduler checkpoint failed;do not resubmit")
    evidence = {"schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": "adsorption_relaxation",
        "scheduler": "LSF", "server_alias": HOST, "job_id": receipt["job_id"],
        "status": _parse_lsf_bjobs(process.stdout, receipt["job_id"]), "checked_at": datetime.now(timezone.utc).isoformat(),
        "source_command": " ".join(argv), "query": query}
    validate_document(evidence, expected_kind="scheduler_job_evidence")
    validate_stored_lsf_evidence(evidence)
    write_json_exclusive(OUTPUT / "scheduler_evidence.json", evidence)
    write_json_exclusive(OUTPUT / "scheduler_snapshot.json", {**evidence,
        "scientific_outputs_reviewed": False, "source_files": source_file_manifest([
            Path(__file__), OUTPUT / "submission_summary.json", OUTPUT / "scheduler_query.json", OUTPUT / "scheduler_evidence.json"])})
    print({k: evidence[k] for k in ["job_id", "status", "checked_at"]}, flush=True)


def registry_plan():
    snapshot = load_json_object(OUTPUT / "scheduler_snapshot.json")
    summary = load_json_object(OUTPUT / "submission_summary.json")
    if not source_file_manifest_valid(snapshot) or not source_file_manifest_valid(summary):
        raise ValueError("scheduler or receipt binding changed")
    receipt = summary["receipt"]
    if submission_status(DIRECTORY) != receipt:
        raise ValueError("native submission receipt changed")
    parent = "fe110_grouped14_family_0099_step020_9922624"
    with open_registry(ROOT / "data/project_registry.sqlite3") as connection:
        if not connection.execute("SELECT 1 FROM calculations WHERE calculation_id=?", (parent,)).fetchone():
            raise ValueError("reviewed source parent missing from registry")
    job_id = receipt["job_id"]
    calculation = "fe110_c3_continue_0099_20261027_" + job_id
    job = "job_" + calculation
    attempt = load_json_object(DIRECTORY / "submission_attempt.json")
    match = re.search(r"queue <([^>]+)>", receipt["submit_stdout"])
    if not match:
        raise ValueError("native receipt lacks actual queue")
    rows = {"calculations": [{"calculation_id": calculation, "module": "adsorption_workflow",
        "purpose": "Authorized one-job C3 continuation for low-force training-label candidates",
        "scientific_system": "true_Fe110_Fe45_C3H2O", "parent_calculation_id": parent,
        "workflow_status": JOB_ALIASES.get(snapshot["status"], snapshot["status"]).lower(),
        "created_at": attempt["created_at_utc"], "source_record": str(PREP / "plan.json"),
        "notes": "32cores;maximum300additional steps;EDIFFG-0.02;no automatic continuation,retry,training or accepted endpoint"}],
        "jobs": [{"job_record_id": job, "calculation_id": calculation, "scheduler_job_id": job_id,
            "scheduler": "LSF", "server_alias": HOST, "queue": match[1], "remote_directory": REMOTE,
            "submit_script": "script.lsf", "submitted_at": attempt["created_at_utc"]}],
        "job_status_history": [{"job_record_id": job, "scheduler_status": snapshot["status"],
            "scientific_status": "Not reviewed;SCF,force convergence,geometry and magnetic moments pending",
            "checked_at": snapshot["checked_at"], "source_command": snapshot["source_command"],
            "source_text": snapshot["query"]["stdout"], "reviewer": "Codex",
            "notes": "Scheduler evidence only;no accepted scientific result"}], "files": []}
    preflight = load_json_object(DIRECTORY / "submission_preflight.json")
    if preflight["bundle_sha256"] != BUNDLE:
        raise ValueError("submitted bundle changed")
    for path in sorted(DIRECTORY.iterdir()):
        if not path.is_file():
            continue
        row = file_row(path, calculation, job, REMOTE, "vasp_input" if path.name in preflight["files"] else "submission_provenance")
        if path.name in preflight["files"]:
            row["remote_path"] = REMOTE + "/" + path.name
        rows["files"].append(row)
    metadata = load_json_object(DIRECTORY / "POTCAR.metadata.json")
    rows["files"].append({"file_id": "file_" + calculation + "_POTCAR", "calculation_id": calculation,
        "job_record_id": job, "role": "vasp_input", "filename": "POTCAR", "remote_path": REMOTE + "/POTCAR",
        "storage_mode": "remote_only", "byte_size": metadata["bytes"], "sha256": receipt["potcar_sha256"],
        "existence_status": "confirmed", "license_or_sensitivity": "licensed_VASP_POTCAR_remains_remote",
        "notes": "Native executor verified target hash immediately before bsub"})
    for path in [AUTH, PREP / "plan.json", OUTPUT / "ready_for_submission.json", OUTPUT / "submission_summary.json",
                 OUTPUT / "remote_precheck.json", OUTPUT / "scheduler_snapshot.json"]:
        rows["files"].append(file_row(path, calculation, job, REMOTE, "batch_submission_provenance"))
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_c3_continuation_submission_20261027_v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": "Codex", "reason": "Record one human-authorized native continuation submission;no accepted results", "rows": rows}
    write_json_exclusive(OUTPUT / "registry_batch.json", batch)
    plan = plan_registry_batch(ROOT / "data/project_registry.sqlite3", batch)
    write_json_exclusive(OUTPUT / "registry_plan.json", plan)
    print({k: plan[k] for k in ["plan_sha256", "insert_count", "update_count", "scope"]}, flush=True)


def verify():
    batch = load_json_object(OUTPUT / "registry_batch.json")
    receipt = load_json_object(OUTPUT / "registry_receipt.json")
    count = sum(len(rows) for rows in batch["rows"].values())
    if receipt["inserted"] != count or receipt["updated"] != 0:
        raise ValueError("unexpected registry receipt")
    summary = load_json_object(OUTPUT / "submission_summary.json")
    if not source_file_manifest_valid(summary) or submission_status(DIRECTORY) != summary["receipt"]:
        raise ValueError("submission binding changed")
    checked = 0
    with open_registry(ROOT / "data/project_registry.sqlite3") as connection:
        for table, key in [("calculations", "calculation_id"), ("jobs", "job_record_id"), ("files", "file_id")]:
            for expected in batch["rows"][table]:
                actual = connection.execute("SELECT * FROM " + table + " WHERE " + key + "=?", (expected[key],)).fetchone()
                if actual is None or any(actual[k] != v for k, v in expected.items()):
                    raise ValueError("registry readback differs")
                checked += 1
        expected = batch["rows"]["job_status_history"][0]
        actual = connection.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND checked_at=?",
                                    (expected["job_record_id"], expected["checked_at"])).fetchall()
        if len(actual) != 1 or any(actual[0][k] != v for k, v in expected.items()):
            raise ValueError("scheduler observation readback differs")
        checked += 1
        calculation = batch["rows"]["calculations"][0]["calculation_id"]
        if connection.execute("SELECT COUNT(*) FROM results WHERE calculation_id=?", (calculation,)).fetchone()[0]:
            raise ValueError("submission must not create accepted scientific results")
    preflight = load_json_object(DIRECTORY / "submission_preflight.json")
    from scripts.artifact_io import sha256_file
    if any(sha256_file(DIRECTORY / n) != digest for n, digest in preflight["files"].items()):
        raise ValueError("submitted inputs changed")
    result = {"status": "PASS", "registry_rows_read_back": checked, "successful_native_receipts": 1,
        "scientific_result_rows_created": 0, "input_hashes_unchanged": True,
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "registry_batch.json", OUTPUT / "registry_plan.json",
            OUTPUT / "registry_approval.json", OUTPUT / "registry_receipt.json", OUTPUT / "submission_summary.json", OUTPUT / "scheduler_snapshot.json"])}
    write_json_exclusive(OUTPUT / "submission_verification.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["collect", "registry-plan", "verify"])
    args = parser.parse_args()
    {"collect": collect, "registry-plan": registry_plan, "verify": verify}[args.action]()
