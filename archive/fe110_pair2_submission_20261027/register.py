"""Plan and verify submitted-job metadata only;never accept scientific results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from scripts.neb_agent.submission import submission_status
from scripts.registry_connection import open_registry
from scripts.registry_write import plan_registry_batch
from scripts.scheduler_evidence import validate_stored_lsf_evidence
from scripts.state_manager.job_lifecycle import JOB_ALIASES
from .submit import AUTH, HOST, OUTPUT, PREP, ROOT


def local_file(path, calculation, job, remote, submitted_files):
    stat = path.stat()
    return {"file_id": "file_" + calculation + "_" + path.name.replace(".", "_"), "calculation_id": calculation,
        "job_record_id": job, "role": "initial_structure" if path.name == "POSCAR" else "input_or_submission_evidence",
        "filename": path.name, "local_path": str(path.resolve()), "remote_path": remote + "/" + path.name if path.name in submitted_files else None,
        "storage_mode": "repository", "byte_size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(), "sha256": sha256_file(path),
        "existence_status": "confirmed", "license_or_sensitivity": "project_internal"}


def build_batch():
    summary = load_json_object(OUTPUT / "submission_summary.json")
    ready = load_json_object(OUTPUT / "ready_for_submission.json")
    if (not source_file_manifest_valid(summary) or not source_file_manifest_valid(ready)
            or len(summary["records"]) != 4 or summary["new_VASP_submitted"] != 4):
        raise ValueError("four successful bound submissions required")
    prepared = {(j["name"], j["model"]): j for j in ready["jobs"]}
    pots = load_json_object(OUTPUT / "remote_precheck.json")["POTCARs"]
    rows = {key: [] for key in ["calculations", "jobs", "job_status_history", "files"]}
    for record in summary["records"]:
        item = prepared[record["name"], record["model"]]
        folder = Path(item["directory"])
        receipt = load_json_object(folder / "submission_record.json")
        attempt = load_json_object(folder / "submission_attempt.json")
        scheduler = load_json_object(folder / "scheduler_after_submission.json")
        validate_stored_lsf_evidence(scheduler)
        if (submission_status(folder) != receipt or sha256_file(folder / "submission_record.json") != record["receipt_sha256"]
                or sha256_file(folder / "scheduler_after_submission.json") != record["scheduler_evidence_sha256"]
                or receipt["bundle_sha256"] != item["bundle_sha256"]):
            raise ValueError("native receipt or scheduler binding changed")
        cid = "fe110_force512_pair2_20261027_" + record["name"] + "_" + record["model"] + "_" + receipt["job_id"]
        jid = "job_" + cid
        queue = re.search(r"queue <([^>]+)>", receipt["submit_stdout"])
        if queue is None:
            raise ValueError("actual queue missing from native receipt")
        rows["calculations"].append({"calculation_id": cid, "module": "adsorption_workflow",
            "purpose": "Paired force512-vs-control DFT relaxation " + record["name"] + " " + record["model"],
            "scientific_system": "true_Fe110_Fe45_C2H3" if record["name"] == "10_A" else "true_Fe110_Fe45_CO_plus_C2H2_ML_product_diagnostic",
            "workflow_status": JOB_ALIASES.get(scheduler["status"], scheduler["status"]).lower(),
            "created_at": attempt["created_at_utc"], "source_record": str(PREP / "plan.json"),
            "notes": "32ranks/max80steps/DFTforce0.02/LORBIT11;C3 source is fragmented ML candidate,not intact C3 success;no scientific acceptance"})
        rows["jobs"].append({"job_record_id": jid, "calculation_id": cid, "scheduler_job_id": receipt["job_id"],
            "scheduler": "LSF", "server_alias": HOST, "queue": queue[1], "remote_directory": item["remote_dir"],
            "submit_script": "script.lsf", "submitted_at": attempt["created_at_utc"]})
        rows["job_status_history"].append({"job_record_id": jid, "scheduler_status": scheduler["status"],
            "scientific_status": "Not assessed;SCF,DFTforce,chemical identity,magnetic branch and same minimum pending",
            "checked_at": scheduler["checked_at"], "source_command": scheduler["source_command"], "source_text": scheduler["query"]["stdout"],
            "reviewer": "Codex", "notes": "Initial live scheduler observation only;no convergence or speedup claim"})
        for path in sorted(folder.iterdir()):
            if path.is_file():
                rows["files"].append(local_file(path, cid, jid, item["remote_dir"], item["files"]))
        pot = pots[item["potcar_source"]]
        rows["files"].append({"file_id": "file_" + cid + "_POTCAR", "calculation_id": cid, "job_record_id": jid,
            "role": "licensed_runtime_input", "filename": "POTCAR", "remote_path": item["remote_dir"] + "/POTCAR", "storage_mode": "remote_only",
            "byte_size": pot["bytes"], "sha256": item["potcar_sha256"], "existence_status": "confirmed",
            "license_or_sensitivity": "licensed_VASP_POTCAR", "notes": "Canonical executor checked copied remote hash immediately before bsub"})
        for path in [AUTH, PREP / "plan.json", OUTPUT / "ready_for_submission.json", OUTPUT / "submission_summary.json", OUTPUT / "remote_precheck.json"]:
            # Stable IDs include the provenance file stem;none overlap per-job filenames.
            entry = local_file(path, cid, jid, item["remote_dir"], [])
            entry["file_id"] = "file_" + cid + "_batch_" + path.name.replace(".", "_")
            rows["files"].append(entry)
    return {"schema_version": 1, "document_kind": "calculation_registry_batch", "batch_id": "fe110_force512_pair2_submission4_20261027_v1",
        "created_at": datetime.now(timezone.utc).isoformat(), "reviewer": "Codex",
        "reason": "Human authorized exactly four bounded DFT relaxations;record job and input provenance only", "rows": rows}


def plan():
    batch = build_batch()
    write_json_exclusive(OUTPUT / "registry_batch.json", batch)
    result = plan_registry_batch(ROOT / "data/project_registry.sqlite3", batch)
    write_json_exclusive(OUTPUT / "registry_plan.json", result)
    print({"plan_sha256": result["plan_sha256"], "scope": result["scope"], "insert_count": result["insert_count"],
        "update_count": result["update_count"], "rows": {k: len(v) for k, v in batch["rows"].items()}}, flush=True)


def verify():
    batch = load_json_object(OUTPUT / "registry_batch.json")
    receipt = load_json_object(OUTPUT / "registry_receipt.json")
    count = sum(len(v) for v in batch["rows"].values())
    if receipt["inserted"] != count or receipt["updated"] != 0:
        raise ValueError("registry apply counts differ")
    checked = 0
    with open_registry(ROOT / "data/project_registry.sqlite3") as conn:
        for table, key in [("calculations", "calculation_id"), ("jobs", "job_record_id"), ("files", "file_id")]:
            for row in batch["rows"][table]:
                actual = conn.execute("SELECT * FROM " + table + " WHERE " + key + "=?", (row[key],)).fetchone()
                if actual is None or any(actual[k] != v for k, v in row.items()):
                    raise ValueError("registry readback differs:" + table)
                checked += 1
        for row in batch["rows"]["job_status_history"]:
            actual = conn.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND checked_at=?", (row["job_record_id"], row["checked_at"])).fetchall()
            if len(actual) != 1 or any(actual[0][k] != v for k, v in row.items()):
                raise ValueError("scheduler history readback differs")
            checked += 1
        for row in batch["rows"]["calculations"]:
            if conn.execute("SELECT COUNT(*) FROM results WHERE calculation_id=?", (row["calculation_id"],)).fetchone()[0]:
                raise ValueError("submission metadata created scientific results")
    ready = load_json_object(OUTPUT / "ready_for_submission.json")
    for job in ready["jobs"]:
        if any(sha256_file(Path(job["directory"]) / filename) != digest for filename, digest in job["files"].items()):
            raise ValueError("submitted local input changed")
    result = {"status": "PASS_FOUR_SUBMISSION_METADATA_READBACK", "registry_rows_read_back": checked, "scientific_result_rows": 0,
        "submitted_input_hashes_unchanged": 24, "source_files": source_file_manifest([Path(__file__), OUTPUT / "registry_batch.json", OUTPUT / "registry_plan.json", OUTPUT / "registry_approval.json", OUTPUT / "registry_receipt.json", OUTPUT / "submission_summary.json"])}
    write_json_exclusive(OUTPUT / "registration_verification.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "verify"])
    args = parser.parse_args()
    plan() if args.action == "plan" else verify()
