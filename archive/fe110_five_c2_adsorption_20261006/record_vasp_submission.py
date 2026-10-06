"""Create submission-only registry plan and state event from actual receipts."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json
from scripts.registry_connection import open_registry
from scripts.registry_mutations import plan_registry_batch

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
DEST = BASE / "vasp_batch_v1"


def main():
    batch = json.loads((DEST / "batch_manifest.json").read_text())
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for entry in batch["entries"]:
        run = Path(entry["workdir"])
        receipt = json.loads((run / "submission_record.json").read_text())
        attempt = json.loads((run / "submission_attempt.json").read_text())
        assert receipt["status"] == "SUBMITTED" and receipt["bundle_sha256"] == entry["bundle_sha256"]
        records.append({**entry, "job_id": receipt["job_id"], "submitted_at": attempt["created_at_utc"],
                        "submit_stdout": receipt["submit_stdout"],
                        "receipt_sha256": sha256_file(run / "submission_record.json")})
    command = "bjobs -w " + " ".join(r["job_id"] for r in records)
    snapshot = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex", command], capture_output=True, text=True)
    snapshot.check_returncode()
    (DEST / "scheduler_snapshot.txt").write_text(snapshot.stdout, encoding="utf-8", newline="\n")
    lines = {line.split()[0]: line for line in snapshot.stdout.splitlines() if line.split() and line.split()[0].isdigit()}
    assert set(lines) == {r["job_id"] for r in records}
    for record in records:
        record["scheduler_status"] = lines[record["job_id"]].split()[2]
    write_json(DEST / "submission_summary.json", {"checked_at": now, "records": records, "no_final_results": True})
    database = ROOT / "data/project_registry.sqlite3"
    with open_registry(database) as connection:
        next_event = connection.execute("SELECT COALESCE(MAX(status_event_id),0)+1 FROM job_status_history").fetchone()[0]
    rows = {name: [] for name in ("calculations", "jobs", "job_status_history", "files")}
    for offset, record in enumerate(records):
        run = Path(record["workdir"])
        calculation_id = "fe110_five_c2_adsorption_20261006_" + record["name"]
        job_record_id = "lsf_" + record["job_id"]
        rows["calculations"].append({"calculation_id": calculation_id, "module": "adsorption_workflow",
            "purpose": "connectivity_specific_adsorption_relaxation", "scientific_system": "Fe110_5layer_3x3_" + record["connectivity"],
            "workflow_status": "submitted", "created_at": record["submitted_at"],
            "source_record": str(run / "candidate_manifest.json"),
            "notes": "32 MPI; SIGMA=0.20; predicted inputs only; final chemistry/convergence/energy acceptance pending."})
        rows["jobs"].append({"job_record_id": job_record_id, "calculation_id": calculation_id,
            "scheduler_job_id": record["job_id"], "scheduler": "LSF", "server_alias": "sunboquan-codex",
            "queue": "Gkn_normal", "remote_directory": record["remote_dir"], "submit_script": "script.lsf",
            "submitted_at": record["submitted_at"]})
        rows["job_status_history"].append({"status_event_id": next_event + offset, "job_record_id": job_record_id,
            "scheduler_status": record["scheduler_status"], "scientific_status": "Not assessed", "checked_at": now,
            "source_command": "ssh sunboquan-codex " + command, "source_text": lines[record["job_id"]],
            "reviewer": "Codex", "notes": "Queue state only; no scientific convergence claim."})
        report = json.loads((run / "submission_preflight.json").read_text())
        for filename, digest in report["files"].items():
            path = run / filename
            rows["files"].append({"file_id": calculation_id + "_" + filename.replace(".", "_"),
                "calculation_id": calculation_id, "job_record_id": job_record_id,
                "role": "initial_structure" if filename == "POSCAR" else "calculation_input",
                "filename": filename, "local_path": str(path), "remote_path": record["remote_dir"] + "/" + filename,
                "storage_mode": "local_and_remote", "byte_size": path.stat().st_size, "sha256": digest,
                "existence_status": "confirmed", "notes": "Exact input hash verified remotely by canonical submission executor."})
        rows["files"].append({"file_id": calculation_id + "_POTCAR", "calculation_id": calculation_id,
            "job_record_id": job_record_id, "role": "calculation_input", "filename": "POTCAR",
            "remote_path": record["remote_dir"] + "/POTCAR", "storage_mode": "remote_only",
            "sha256": record["potcar_sha256"], "existence_status": "confirmed", "license_or_sensitivity": "VASP licensed POTCAR; contents remain remote"})
    registry_batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_five_c2_adsorption_vasp_submission_20261006", "created_at": now,
        "reviewer": "Codex", "reason": "User authorized submission; register actual jobs and input provenance only, not accepted energies.", "rows": rows}
    write_json(DEST / "registry_batch.json", registry_batch)
    plan = plan_registry_batch(database, registry_batch)
    write_json(DEST / "registry_plan.json", plan)
    print(json.dumps({"job_ids": [r["job_id"] for r in records], "statuses": [r["scheduler_status"] for r in records],
                      "registry_insert_count": plan["insert_count"], "scope": plan["scope"], "plan_sha256": plan["plan_sha256"]}))


if __name__ == "__main__":
    main()
