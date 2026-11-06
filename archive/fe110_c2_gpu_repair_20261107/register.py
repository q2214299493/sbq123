"""Prepare/read back repaired-job provenance through the canonical registry writer."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from .prepare import OUT, REMOTE

DB = Path("data/project_registry.sqlite3")
IDS = {"aqcat_gpu": "fe110_c2_supplement_mz73_independent_20261107_v1",
       "buct2_gpu": "fe110_c2_supplement_buct2_independent_20261107_v1"}
OLD_IDS = {"aqcat_gpu": "fe110_c2_supplement_gpu_20261106_v1",
           "buct2_gpu": "fe110_c2_supplement_buct2_gpu_20261106_v1"}


def prepare():
    rows = {key: [] for key in ("calculations", "jobs", "job_status_history", "files")}
    changes = []
    for backend, cid in IDS.items():
        base, jid = OUT / backend, "job_" + cid
        package = base / "package"
        receipt = load_json_object(base / "submission_receipt.json")
        snapshot = load_json_object(base / "native_status.json")
        if (receipt["exit_code"] or receipt["request_sha256"] != sha256_file(package / "request.json")
                or snapshot["request_sha256"] != receipt["request_sha256"] or snapshot["job_id"] != receipt["job_id"]):
            raise ValueError("native submitted request binding failed")
        state = {"PENDING": "SUBMITTED", "RUNNING": "RUNNING"}.get(snapshot["state"])
        if state is None:
            raise ValueError("terminal job requires result-aware review before registration")
        rows["calculations"].append({"calculation_id": cid, "parent_calculation_id": OLD_IDS[backend],
            "module": "adsorption_workflow", "purpose": "Repaired independent GPU replica of exact12 reviewed seeds",
            "scientific_system": "true_Fe110_Fe45_C2_site_supplement_05_06_07_09_11_12_13_14_18",
            "workflow_status": state.lower(), "created_at": receipt["submitted_at"],
            "source_record": str(package / "request.json"),
            "notes": "Only execution layer repaired;frozenFT512/seeds/optimizer unchanged;no winner permit,no CPU fallback,training,promotion,VASP or accepted energy."})
        rows["jobs"].append({"job_record_id": jid, "calculation_id": cid, "scheduler_job_id": receipt["job_id"],
            "scheduler": "Slurm", "server_alias": "BUCT(sbq)" if backend == "aqcat_gpu" else "BUCT2",
            "queue": "gpu", "remote_directory": REMOTE, "submit_script": "run.sbatch", "submitted_at": receipt["submitted_at"]})
        rows["job_status_history"].append({"job_record_id": jid, "scheduler_status": state,
            "scientific_status": "Not assessed;ML candidates only;work-side site/connectivity review required",
            "checked_at": snapshot["checked_at"], "source_command": "scontrol show job -o " + receipt["job_id"],
            "source_text": snapshot["scheduler_raw"], "reviewer": "Codex",
            "notes": "Native PENDING means queued,not CUDA/model/structure convergence."})
        paths = sorted(path for path in base.rglob("*") if path.is_file() and path.suffix != ".tar")
        for index, path in enumerate(paths):
            remote = REMOTE + "/" + path.relative_to(package).as_posix() if path.is_relative_to(package) else None
            rows["files"].append({"file_id": cid + f"__file_{index:03d}", "calculation_id": cid, "job_record_id": jid,
                "role": "GPU_repair_input_and_native_execution_evidence", "filename": path.name,
                "local_path": str(path), "remote_path": remote,
                "storage_mode": "local_and_remote" if remote else "local_only", "byte_size": path.stat().st_size,
                "sha256": sha256_file(path), "existence_status": "confirmed", "notes": "No formal DFT or adsorption result."})
        old = load_json_object(base / "obsolete_terminal.json")
        if backend == "aqcat_gpu":
            if not any("WEXITSTATUS 1" in line for line in old["controller_lines"]):
                raise ValueError("old MZ73 native failure not established")
            reason = "Native Slurm controller records11396 WEXITSTATUS1;GPU precheck failed before optimization."
        else:
            if "JobState=CANCELLED" not in old["scheduler_raw"]:
                raise ValueError("obsolete BUCT2 cancellation not established")
            reason = "User-authorized obsolete1355 cancellation;native CANCELLED;not a structural/model failure."
        rows["job_status_history"].append({"job_record_id": "job_" + OLD_IDS[backend], "scheduler_status": "FAILED",
            "scientific_status": "Not assessed;zero optimized structures;execution failure or authorized cancellation",
            "checked_at": old["checked_at"], "source_command": "scontrol show job -o " + old["job_id"] + "; own-job native controller log",
            "source_text": old["scheduler_raw"] + "\n" + "\n".join(old["controller_lines"]),
            "reviewer": "Codex", "notes": reason + " Registry FAILED is terminal normalization only;raw native state retained."})
        changes.append({"status_change_id": OLD_IDS[backend] + "__replaced_20261107", "calculation_id": OLD_IDS[backend],
            "expected_workflow_status": "submitted", "new_workflow_status": "failed", "changed_at": old["checked_at"],
            "reviewer": "Codex", "reason": reason})
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
             "batch_id": "fe110_c2_gpu_independent_repair_20261107_v1", "created_at": datetime.now(timezone.utc).isoformat(),
             "reviewer": "Codex", "reason": "Explicit user repair/submission authority;job provenance only,zero accepted scientific results.",
             "rows": rows, "workflow_status_changes": changes}
    write_json_exclusive(OUT / "registry_batch.json", batch)
    print("PREPARED_METADATA", {key: len(value) for key, value in rows.items()}, "workflow_changes=2 scientific_results=0")


def verify():
    batch = load_json_object(OUT / "registry_batch.json")
    keys = {"calculations": "calculation_id", "jobs": "job_record_id", "files": "file_id"}
    count = 0
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        for table, key in keys.items():
            for row in batch["rows"][table]:
                saved = db.execute("SELECT * FROM " + table + " WHERE " + key + "=?", (row[key],)).fetchone()
                if saved is None or any(saved[field] != value for field, value in row.items()):
                    raise ValueError("readback differs: " + table)
                count += 1
        for row in batch["rows"]["job_status_history"]:
            saved = db.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND checked_at=?",
                               (row["job_record_id"], row["checked_at"])).fetchall()
            if len(saved) != 1 or any(saved[0][key] != value for key, value in row.items()):
                raise ValueError("job history readback differs")
            count += 1
        for change in batch["workflow_status_changes"]:
            saved = db.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (change["calculation_id"],)).fetchone()
            if saved[0] != change["new_workflow_status"]:
                raise ValueError("obsolete workflow projection differs")
        for cid in IDS.values():
            if db.execute("SELECT 1 FROM results WHERE calculation_id=?", (cid,)).fetchone():
                raise ValueError("ML stage acquired scientific result")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("registry integrity failed")
    write_json_exclusive(OUT / "registry_verification.json", {"status": "PASS", "rows_read_back": count,
        "workflow_changes_verified": 2, "new_GPU_jobs": 2, "candidate_count": 12, "scientific_results": 0})
    print("VERIFIED", count, "provenance rows;2 workflow changes;zero scientific results")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    {"prepare": prepare, "verify": verify}[parser.parse_args().phase]()
