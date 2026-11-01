"""Append-only GPU provenance and twelve native VASP job records; zero results."""
from datetime import datetime, timezone
from pathlib import Path
import re

from archive.fe110_scratch512_20261028.register_c2_dft import local_file
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest_valid, write_json_exclusive
from scripts.neb_agent.submission import submission_status
from scripts.registry_connection import open_registry
from scripts.scheduler_evidence import validate_stored_lsf_evidence
from scripts.state_manager.job_lifecycle import JOB_ALIASES

from .adapter import NAMES
from .dft import AUTH, HOST, PREP, SUBMISSION
from .prepare import OUTPUT, PACKAGE, REMOTE, ROOT

DB = ROOT / "data/project_registry.sqlite3"
GPU_CID = "fe110_c2_16_19_uncalibrated_gpu_20261102_v1"


def prepare():
    target = SUBMISSION / "registry_batch.json"
    if target.exists():
        raise FileExistsError("inspect existing metadata plan/receipt before resuming")
    summary = load_json_object(SUBMISSION / "submission_summary.json")
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    if (not source_file_manifest_valid(summary) or not source_file_manifest_valid(ready)
            or [r["name"] for r in summary["records"]] != NAMES or summary["new_VASP_submitted"] != 12):
        raise ValueError("twelve successful native submissions required")
    now = datetime.now(timezone.utc).isoformat()
    rows = {k: [] for k in ("calculations", "jobs", "job_status_history", "files")}
    rows["calculations"].append({"calculation_id": GPU_CID, "module": "adsorption_workflow",
        "purpose": "bounded shared-GPU predicted-candidate generation;12 seeds;no accepted energies",
        "scientific_system": "true_Fe110_Fe45_C2H4O_and_C2H6_reviewed_seeds",
        "workflow_status": "done", "created_at": now, "source_record": str(PACKAGE / "request.json"),
        "notes": "Direct process2588719/controller2588704;not Slurm jobs;12 ML thresholds reached,10 intact endpoints+2 original-seed fallbacks;out-of-domain,no ranking or promotion."})
    gpu_files = []
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file():
            gpu_files.append((path, "input__" + path.relative_to(PACKAGE).as_posix(), REMOTE + "/" + path.relative_to(PACKAGE).as_posix(), "local_and_remote"))
    for item in load_json_object(OUTPUT / "collection_manifest.json")["files"]:
        path = OUTPUT / "returned" / item["path"]
        if sha256_file(path) != item["sha256"]:
            raise ValueError("GPU return bytes changed")
        gpu_files.append((path, "output__" + item["path"], REMOTE + "/" + item["path"], "local_and_remote"))
    for path in [OUTPUT / "ML_results_review.json", OUTPUT / "producer_exit_handoff_adapter.json",
                 *sorted((OUTPUT / "returned_handoffs_v2").glob("*.json"))]:
        gpu_files.append((path, "work_review__" + path.relative_to(OUTPUT).as_posix(), None, "local_only"))
    for path, relative, remote, mode in gpu_files:
        rows["files"].append({"file_id": GPU_CID + "__" + relative.replace("/", "__").replace(".", "_"),
            "calculation_id": GPU_CID, "role": "predicted_candidate_provenance", "filename": path.name,
            "local_path": str(path), "remote_path": remote, "storage_mode": mode,
            "sha256": sha256_file(path), "byte_size": path.stat().st_size, "existence_status": "confirmed",
            "notes": "MZ73 GPU prediction/input evidence only,not DFT or scientific acceptance."})
    prepared = {r["name"]: r for r in ready["jobs"]}
    pots = load_json_object(SUBMISSION / "remote_precheck.json")["POTCARs"]
    for record in summary["records"]:
        row = prepared[record["name"]]
        folder = Path(row["directory"])
        receipt = load_json_object(folder / "submission_record.json")
        attempt = load_json_object(folder / "submission_attempt.json")
        scheduler = load_json_object(folder / "scheduler_after_submission.json")
        validate_stored_lsf_evidence(scheduler)
        if submission_status(folder) != receipt or receipt["job_id"] != record["job_id"] or receipt["bundle_sha256"] != row["bundle_sha256"]:
            raise ValueError("native submission binding changed")
        candidate = load_json_object(folder / "candidate_manifest.json")
        cid = "fe110_c2_16_19_ft512_20261102_" + record["name"] + "_" + receipt["job_id"]
        jid = "job_" + cid
        queue = re.search(r"queue <([^>]+)>", receipt["submit_stdout"])
        if queue is None:
            raise ValueError("native queue missing")
        rows["calculations"].append({"calculation_id": cid, "parent_calculation_id": GPU_CID,
            "module": "adsorption_workflow", "purpose": "16-19 adsorption relaxation " + record["name"] + ";" + candidate["source_role"],
            "scientific_system": "true_Fe110_Fe45_" + candidate["formula"],
            "workflow_status": JOB_ALIASES.get(scheduler["status"], scheduler["status"]).lower(),
            "created_at": attempt["created_at_utc"], "source_record": str(PREP / "plan.json"),
            "notes": "32ranks/32pernode/NSW300/EDIFFG-0.02/ALGO Fast/SIGMA0.20;no pilot,retry,accepted energy or demonstrated speedup."})
        rows["jobs"].append({"job_record_id": jid, "calculation_id": cid, "scheduler_job_id": receipt["job_id"],
            "scheduler": "LSF", "server_alias": HOST, "queue": queue[1], "remote_directory": row["remote_dir"],
            "submit_script": "script.lsf", "submitted_at": attempt["created_at_utc"]})
        rows["job_status_history"].append({"job_record_id": jid, "scheduler_status": scheduler["status"],
            "scientific_status": "Not assessed;electronic/force/final chemistry/magnetic review pending", "checked_at": scheduler["checked_at"],
            "source_command": scheduler["source_command"], "source_text": scheduler["query"]["stdout"], "reviewer": "Codex",
            "notes": "Initial native scheduler evidence only;no inferred scientific convergence."})
        for path in sorted(folder.iterdir()):
            if path.is_file():
                rows["files"].append(local_file(path, cid, jid, row["remote_dir"], row["files"]))
        pot = pots[row["potcar_source"]]
        rows["files"].append({"file_id": "file_" + cid + "_POTCAR", "calculation_id": cid, "job_record_id": jid,
            "role": "licensed_runtime_input", "filename": "POTCAR", "remote_path": row["remote_dir"] + "/POTCAR",
            "storage_mode": "remote_only", "byte_size": pot["bytes"], "sha256": row["potcar_sha256"],
            "existence_status": "confirmed", "license_or_sensitivity": "licensed_VASP_POTCAR",
            "notes": "Exact copied bytes checked before bsub;no licensed data downloaded."})
        for path in (AUTH, PREP / "plan.json", PREP / "input_verification.json", OUTPUT / "ML_results_review.json",
                     SUBMISSION / "ready_for_submission.json", SUBMISSION / "submission_summary.json", SUBMISSION / "remote_precheck.json"):
            entry = local_file(path, cid, jid, row["remote_dir"], [])
            entry["file_id"] = "file_" + cid + "_batch_" + path.name.replace(".", "_")
            rows["files"].append(entry)
    write_json_exclusive(target, {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_c2_16_19_submission_20261102_v1", "created_at": now, "reviewer": "Codex",
        "reason": "Explicit current request: GPU then work-reviewed DFT for12 seeds;metadata only.", "rows": rows})
    print("PREPARED_METADATA", {k: len(v) for k, v in rows.items()}, "scientific_results", 0)


def verify():
    batch = load_json_object(SUBMISSION / "registry_batch.json")
    keys = {"calculations": "calculation_id", "jobs": "job_record_id", "files": "file_id"}
    checked = 0
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        for table, key in keys.items():
            for row in batch["rows"][table]:
                saved = db.execute("SELECT * FROM " + table + " WHERE " + key + "=?", (row[key],)).fetchone()
                if saved is None or any(saved[k] != v for k, v in row.items()):
                    raise ValueError("metadata readback differs: " + table)
                checked += 1
        for row in batch["rows"]["job_status_history"]:
            saved = db.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND checked_at=?", (row["job_record_id"], row["checked_at"])).fetchall()
            if len(saved) != 1 or any(saved[0][k] != v for k, v in row.items()):
                raise ValueError("job history readback differs")
            checked += 1
        for row in batch["rows"]["calculations"]:
            if db.execute("SELECT 1 FROM results WHERE calculation_id=?", (row["calculation_id"],)).fetchone():
                raise ValueError("new submissions acquired unexpected scientific results")
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    write_json_exclusive(SUBMISSION / "registration_verification.json", {"status": "PASS", "rows_read_back": checked,
        "VASP_jobs": 12, "GPU_prediction_batches": 1, "scientific_result_rows": 0})
    print("VERIFIED", checked, "metadata rows;12 VASP jobs,zero scientific results")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    args = parser.parse_args()
    {"prepare": prepare, "verify": verify}[args.action]()
