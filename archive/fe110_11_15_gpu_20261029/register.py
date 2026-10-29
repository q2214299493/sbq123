"""Append-only submission metadata; no energy or scientific acceptance rows."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

from archive.fe110_scratch512_20261028.register_c2_dft import local_file
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from scripts.neb_agent.submission import submission_status
from scripts.registry_connection import open_registry
from scripts.registry_write import plan_registry_batch
from scripts.scheduler_evidence import validate_stored_lsf_evidence
from scripts.state_manager.job_lifecycle import JOB_ALIASES
from .adapter import NAMES
from .dft import AUTH, HOST, OUTPUT, PREP, ROOT
from .complete_dft import FINAL as SUBMISSION

DATABASE = ROOT / "data/project_registry.sqlite3"


def build_batch():
    summary = load_json_object(SUBMISSION / "submission_summary.json")
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    if (not source_file_manifest_valid(summary) or not source_file_manifest_valid(ready)
            or [r["name"] for r in summary["records"]] != NAMES or summary["new_VASP_submitted"] != 15):
        raise ValueError("fifteen successful bound submissions required")
    prepared = {j["name"]: j for j in ready["jobs"]}
    pots = load_json_object(SUBMISSION / "remote_precheck.json")["POTCARs"]
    rows = {key: [] for key in ["calculations", "jobs", "job_status_history", "files"]}
    for record in summary["records"]:
        item = prepared[record["name"]]
        folder = Path(item["directory"])
        receipt = load_json_object(folder / "submission_record.json")
        attempt = load_json_object(folder / "submission_attempt.json")
        scheduler = load_json_object(folder / "scheduler_after_submission.json")
        validate_stored_lsf_evidence(scheduler)
        if (submission_status(folder) != receipt or receipt["bundle_sha256"] != item["bundle_sha256"]
                or receipt["job_id"] != record["job_id"] or scheduler["job_id"] != receipt["job_id"]):
            raise ValueError("native receipt or scheduler binding changed")
        cid = "fe110_c2_11_15_ft512_20261029_" + record["name"] + "_" + receipt["job_id"]
        jid = "job_" + cid
        queue = re.search(r"queue <([^>]+)>", receipt["submit_stdout"])
        if queue is None:
            raise ValueError("actual native queue absent")
        candidate = load_json_object(folder / "candidate_manifest.json")
        rows["calculations"].append({"calculation_id": cid, "module": "adsorption_workflow",
            "purpose": "11-15 reviewed FT512 pre-relaxed adsorption " + record["name"],
            "scientific_system": "true_Fe110_Fe45_" + candidate["formula"],
            "workflow_status": JOB_ALIASES.get(scheduler["status"], scheduler["status"]).lower(),
            "created_at": attempt["created_at_utc"], "source_record": str(PREP / "plan.json"),
            "notes": "32ranks/max80steps/DFTforce0.02/LORBIT11;experimental ML seed;no accepted energy,minimum or automatic continuation"})
        rows["jobs"].append({"job_record_id": jid, "calculation_id": cid, "scheduler_job_id": receipt["job_id"],
            "scheduler": "LSF", "server_alias": HOST, "queue": queue[1], "remote_directory": item["remote_dir"],
            "submit_script": "script.lsf", "submitted_at": attempt["created_at_utc"]})
        rows["job_status_history"].append({"job_record_id": jid, "scheduler_status": scheduler["status"],
            "scientific_status": "Not assessed;SCF,DFTforce,chemical identity and magnetic branch pending",
            "checked_at": scheduler["checked_at"], "source_command": scheduler["source_command"], "source_text": scheduler["query"]["stdout"],
            "reviewer": "Codex", "notes": "Initial live scheduler evidence only;not convergence or speedup evidence"})
        for path in sorted(folder.iterdir()):
            if path.is_file():
                rows["files"].append(local_file(path, cid, jid, item["remote_dir"], item["files"]))
        pot = pots[item["potcar_source"]]
        rows["files"].append({"file_id": "file_" + cid + "_POTCAR", "calculation_id": cid, "job_record_id": jid,
            "role": "licensed_runtime_input", "filename": "POTCAR", "remote_path": item["remote_dir"] + "/POTCAR", "storage_mode": "remote_only",
            "byte_size": pot["bytes"], "sha256": item["potcar_sha256"], "existence_status": "confirmed",
            "license_or_sensitivity": "licensed_VASP_POTCAR", "notes": "Native executor verified copied bytes before bsub;no licensed content imported"})
        sources = [AUTH, PREP / "plan.json", PREP / "input_verification.json", OUTPUT / "ML_results_review.json",
            SUBMISSION / "ready_for_submission.json", SUBMISSION / "submission_summary.json", SUBMISSION / "remote_precheck.json",
            OUTPUT / "returned/output/finetune" / record["name"] / "seed/optimization.traj"]
        for path in sources:
            entry = local_file(path, cid, jid, item["remote_dir"], [])
            entry["file_id"] = "file_" + cid + "_batch_" + path.name.replace(".", "_")
            rows["files"].append(entry)
    return {"schema_version": 1, "document_kind": "calculation_registry_batch", "batch_id": "fe110_c2_11_15_ft512_submission_20261029_v1",
        "created_at": datetime.now(timezone.utc).isoformat(), "reviewer": "Codex",
        "reason": "Current human request explicitly authorizes GPU then DFT for15reviewed seeds;metadata only", "rows": rows}


def plan():
    batch = build_batch()
    write_json_exclusive(SUBMISSION / "registry_batch.json", batch)
    result = plan_registry_batch(DATABASE, batch)
    write_json_exclusive(SUBMISSION / "registry_plan.json", result)
    print({"plan_sha256": result["plan_sha256"], "scope": result["scope"], "insert_count": result["insert_count"],
        "update_count": result["update_count"], "rows": {k: len(v) for k, v in batch["rows"].items()}}, flush=True)


def verify():
    batch = load_json_object(SUBMISSION / "registry_batch.json")
    receipt = load_json_object(SUBMISSION / "registry_receipt.json")
    count = sum(len(v) for v in batch["rows"].values())
    if receipt["inserted"] != count or receipt["updated"] != 0:
        raise ValueError("registry applied different row counts")
    checked = 0
    with open_registry(DATABASE) as conn:
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
                raise ValueError("submission metadata inserted scientific results")
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    for job in ready["jobs"]:
        if any(sha256_file(Path(job["directory"]) / f) != h for f, h in job["files"].items()):
            raise ValueError("submitted input bytes changed")
    result = {"status": "PASS_15_JOB_METADATA_READBACK", "registry_rows_read_back": checked, "scientific_result_rows": 0,
        "submitted_input_hashes_unchanged": sum(len(j["files"]) for j in ready["jobs"]),
        "source_files": source_file_manifest([Path(__file__), SUBMISSION / "registry_batch.json", SUBMISSION / "registry_plan.json", SUBMISSION / "registry_approval.json", SUBMISSION / "registry_receipt.json", SUBMISSION / "submission_summary.json"])}
    write_json_exclusive(SUBMISSION / "registration_verification.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "verify"])
    args = parser.parse_args()
    plan() if args.action == "plan" else verify()
