"""Prepare one submission-only registry batch from actual canonical receipts."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.registry_connection import open_registry
from scripts.registry_mutations import plan_registry_batch

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/vasp_batch_v1"
DATABASE = ROOT / "data/project_registry.sqlite3"


def main():
    batch = load_json_object(DEST / "batch_manifest.json")
    records = []
    for entry in batch["entries"]:
        run = Path(entry["workdir"])
        receipt = load_json_object(run / "submission_record.json")
        attempt = load_json_object(run / "submission_attempt.json")
        if receipt["status"] != "SUBMITTED" or receipt["bundle_sha256"] != entry["bundle_sha256"]:
            raise ValueError("Unconfirmed submission: " + entry["name"])
        records.append({**entry, "job_id": receipt["job_id"], "submitted_at": attempt["created_at_utc"],
                        "receipt_sha256": sha256_file(run / "submission_record.json")})
    command = "bjobs -w " + " ".join(row["job_id"] for row in records)
    snapshot = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                               "sunboquan-codex", command], capture_output=True, text=True, timeout=90)
    snapshot.check_returncode()
    now = datetime.now(timezone.utc).isoformat()
    (DEST / "scheduler_snapshot.txt").write_text(snapshot.stdout, encoding="utf-8", newline="\n")
    lines = {line.split()[0]: line for line in snapshot.stdout.splitlines()
             if line.split() and line.split()[0].isdigit()}
    if set(lines) != {row["job_id"] for row in records}:
        raise ValueError("Incomplete scheduler snapshot; do not invent job states")
    for record in records:
        record["scheduler_status"] = lines[record["job_id"]].split()[2]
    write_json(DEST / "submission_summary.json", {"checked_at": now, "records": records,
                                                "scientific_acceptance": False})
    with open_registry(DATABASE) as connection:
        next_event = connection.execute("SELECT COALESCE(MAX(status_event_id),0)+1 FROM job_status_history").fetchone()[0]
    rows = {table: [] for table in ("calculations", "jobs", "job_status_history", "files")}
    for offset, record in enumerate(records):
        run = Path(record["workdir"])
        calc = "fe110_c2_06_10_adsorption_20261013_" + record["name"]
        job = "lsf_" + record["job_id"]
        notes = ("32 MPI / max32 per node; routine production; SIGMA=0.20. "
                 "Original target: " + record["connectivity"] + "; submitted predicted state: "
                 + record["submitted_connectivity"] + ". Final VASP chemistry/energy acceptance pending.")
        rows["calculations"].append({"calculation_id": calc, "module": "adsorption_workflow",
            "purpose": "reviewed_GPU_adsorption_or_reclassified_coadsorption_relaxation",
            "scientific_system": "Fe110_5layer_3x3_" + record["submitted_connectivity"],
            "workflow_status": "submitted", "created_at": record["submitted_at"],
            "source_record": str(run / "candidate_manifest.json"), "notes": notes})
        rows["jobs"].append({"job_record_id": job, "calculation_id": calc,
            "scheduler_job_id": record["job_id"], "scheduler": "LSF", "server_alias": "sunboquan-codex",
            "queue": "Gkn_normal", "remote_directory": record["remote_dir"],
            "submit_script": "script.lsf", "submitted_at": record["submitted_at"]})
        rows["job_status_history"].append({"status_event_id": next_event + offset,
            "job_record_id": job, "scheduler_status": record["scheduler_status"],
            "scientific_status": "Not assessed", "checked_at": now,
            "source_command": "ssh sunboquan-codex " + command, "source_text": lines[record["job_id"]],
            "reviewer": "Codex", "notes": "Live queue state only; not convergence or acceptance."})
        report = load_json_object(run / "submission_preflight.json")
        for filename, digest in report["files"].items():
            path = run / filename
            if sha256_file(path) != digest:
                raise ValueError("Submitted input changed: " + str(path))
            rows["files"].append({"file_id": calc + "_" + filename.replace(".", "_"),
                "calculation_id": calc, "job_record_id": job,
                "role": "initial_structure" if filename == "POSCAR" else "calculation_input",
                "filename": filename, "local_path": str(path), "remote_path": record["remote_dir"] + "/" + filename,
                "storage_mode": "local_and_remote", "byte_size": path.stat().st_size, "sha256": digest,
                "existence_status": "confirmed", "notes": "Canonical executor verified exact remote hash."})
        rows["files"].append({"file_id": calc + "_POTCAR", "calculation_id": calc, "job_record_id": job,
            "role": "calculation_input", "filename": "POTCAR", "remote_path": record["remote_dir"] + "/POTCAR",
            "storage_mode": "remote_only", "sha256": record["potcar_sha256"], "existence_status": "confirmed",
            "license_or_sensitivity": "Licensed VASP potential; contents remain remote."})
        for filename in ("submission_preflight.json", "user_execution_authorization.json", "decision.json",
                         "submission_attempt.json", "submission_record.json"):
            path = run / filename
            rows["files"].append({"file_id": calc + "_" + filename.replace(".", "_"),
                "calculation_id": calc, "job_record_id": job, "role": "submission_evidence",
                "filename": filename, "local_path": str(path), "storage_mode": "local_only",
                "byte_size": path.stat().st_size, "sha256": sha256_file(path), "existence_status": "confirmed"})
    registry_batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_c2_06_10_vasp_submission_20261013_v1", "created_at": now, "reviewer": "Codex",
        "reason": "User explicitly authorized all15 VASP relaxations after chemical reclassification review; submission provenance only.",
        "rows": rows}
    write_json(DEST / "registry_batch.json", registry_batch)
    plan = plan_registry_batch(DATABASE, registry_batch)
    write_json(DEST / "registry_plan.json", plan)
    print("JOBS", [(row["name"], row["job_id"], row["scheduler_status"]) for row in records])
    print("PLAN", plan["scope"], plan["insert_count"], plan["plan_sha256"])


if __name__ == "__main__":
    main()
