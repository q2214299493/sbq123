"""Prepare/read back GPU job and file provenance only; no scientific results."""
import argparse
from datetime import datetime, timezone

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from .prepare import OUT, PACKAGE, REMOTE, ROOT

CID = "fe110_c2_supplement_gpu_20261106_v1"
JID = "job_" + CID
DB = ROOT / "data/project_registry.sqlite3"
BATCH = OUT / "registry_batch_v2.json"


def prepare():
    receipt = load_json_object(OUT / "submission_receipt.json")
    checked = load_json_object(OUT / "scheduler_observation.stdout")
    native = checked["stdout"].strip()
    if (receipt["exit_code"] != 0 or not receipt["job_id"].isdigit()
            or receipt["request_sha256"] != sha256_file(PACKAGE / "request.json")
            or checked["exit_code"] != 0 or native.split("|")[:2] != [receipt["job_id"], "PENDING"]
            or datetime.fromisoformat(checked["checked_at"]) < datetime.fromisoformat(receipt["submitted_at"])):
        raise ValueError("successful exact native Slurm submission and pending observation required")
    now = datetime.now(timezone.utc).isoformat()
    rows = {"calculations": [{"calculation_id": CID, "module": "adsorption_workflow",
        "purpose": "Twelve user-retained non-equivalent adsorption supplement candidates;GPU pre-relaxation only",
        "scientific_system": "true_Fe110_Fe45_C2_site_supplement_05_06_07_09_11_12_13_14_18",
        "workflow_status": "submitted", "created_at": receipt["submitted_at"],
        "source_record": str(PACKAGE / "request.json"),
        "notes": "Frozen FT512;no training,promotion,CPU fallback,VASP,accepted energy or ranking;post-return site/connectivity review required."}],
        "jobs": [{"job_record_id": JID, "calculation_id": CID, "scheduler_job_id": receipt["job_id"],
            "scheduler": "Slurm", "server_alias": "BUCT(sbq)", "queue": "gpu", "remote_directory": REMOTE,
            "submit_script": "run.sbatch", "submitted_at": receipt["submitted_at"]}],
        "job_status_history": [{"job_record_id": JID, "scheduler_status": "SUBMITTED",
            "scientific_status": "Not assessed;producer not started;no electronic or ionic DFT results",
            "checked_at": checked["checked_at"], "source_command": " ".join(checked["argv"]), "source_text": native,
            "reviewer": "Codex", "notes": "Native Slurm PENDING(Resources) is retained in source_text;registry SUBMITTED records accepted submission,not RUNNING or scientific acceptance."}], "files": []}
    paths = sorted(p for p in PACKAGE.rglob("*") if p.is_file())
    paths += [OUT / name for name in ("preparation_receipt.json", "upload.receipt.json", "native_preflight.receipt.json",
        "native_preflight.stdout", "submission_receipt.json", "submit.stdout", "scheduler_observation.receipt.json", "scheduler_observation.stdout")]
    for index, path in enumerate(paths):
        remote = REMOTE + "/" + path.relative_to(PACKAGE).as_posix() if path.is_relative_to(PACKAGE) else None
        rows["files"].append({"file_id": CID + f"__file_{index:03d}", "calculation_id": CID, "job_record_id": JID,
            "role": "GPU_input_or_submission_evidence", "filename": path.name, "local_path": str(path),
            "remote_path": remote, "storage_mode": "local_and_remote" if remote else "local_only",
            "byte_size": path.stat().st_size, "sha256": sha256_file(path), "existence_status": "confirmed",
            "notes": "Prediction-stage provenance;not VASP output or accepted adsorption result."})
    write_json_exclusive(BATCH, {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": CID + "_submission", "created_at": now, "reviewer": "Codex",
        "reason": "User authorized all exact12 GPU candidates;record actual Slurm job and inputs,zero scientific results.", "rows": rows})
    print("PREPARED_METADATA", {key: len(value) for key, value in rows.items()}, "scientific_results=0")


def verify():
    batch = load_json_object(BATCH)
    keys = {"calculations": "calculation_id", "jobs": "job_record_id", "files": "file_id"}
    count = 0
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        for table, key in keys.items():
            for row in batch["rows"][table]:
                saved = db.execute("SELECT * FROM " + table + " WHERE " + key + "=?", (row[key],)).fetchone()
                if saved is None or any(saved[k] != v for k, v in row.items()):
                    raise ValueError("metadata readback differs: " + table)
                count += 1
        for row in batch["rows"]["job_status_history"]:
            saved = db.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND checked_at=?",
                               (JID, row["checked_at"])).fetchall()
            if len(saved) != 1 or any(saved[0][k] != v for k, v in row.items()):
                raise ValueError("status readback differs")
            count += 1
        if db.execute("SELECT 1 FROM results WHERE calculation_id=?", (CID,)).fetchone():
            raise ValueError("prediction stage acquired a scientific result")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("registry integrity check failed")
    write_json_exclusive(OUT / "registry_verification.json", {"status": "PASS", "rows_read_back": count,
        "GPU_jobs": 1, "candidate_count": 12, "scientific_result_rows": 0})
    print("VERIFIED", count, "provenance rows;zero scientific results")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    {"prepare": prepare, "verify": verify}[parser.parse_args().phase]()
