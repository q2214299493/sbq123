"""Record actual CH+CO GPU and VASP jobs, without accepting scientific results."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import subprocess

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from .vasp import OUT as VASP, ROOT

OUT = VASP.parent / "job_registration_20261110_v1"
REVIEWER = "Codex work-side review under explicit GPU/VASP submission authority 2026-11-10"
DB = ROOT / "data/project_registry.sqlite3"


def prepare():
    if OUT.exists():
        raise ValueError("Registration package exists; reconcile, do not regenerate.")
    OUT.mkdir()
    rows = {key: [] for key in ("calculations", "jobs", "job_status_history", "files")}
    for job, folder, parent, purpose in (
        ("12405", "gpu_20261110_v1", None, "Bounded MatRIS ordinary ML-NEB and exact-path AQCat25 audit"),
        ("12406", "gpu_fixed_path_audit_20261110_v2", "12405", "Exact fixed-path dual-model CUDA audit; zero optimization/training steps"),
        ("9994246", "vasp_ordinary_neb_20261110_v1", "12406", "Reviewed first VASP ordinary NEB; six internal images;96MPI/32pernode;no pilot"),
    ):
        base = VASP.parent / folder
        cid = "fe110_ch_co_ts_20261110_job" + job
        jid = "job_" + cid
        if job != "9994246":
            receipt = load_json_object(base / "submission_receipt.json")
            raw = load_json_object(base / "return_inventory.json")
            inventory = json.loads(raw["stdout"])
            native = inventory["scheduler"]["stdout"]
            expected = "FAILED" if job == "12405" else "COMPLETED"
            if receipt["job_id"] != job or "JobState=" + expected not in native or "JobId=" + job + " " not in native:
                raise ValueError("Native GPU execution provenance differs.")
            status = "FAILED" if job == "12405" else "DONE"
            workflow = "failed" if job == "12405" else "done"
            scientific = ("MatRIS primary converged in60steps;secondary CUDA device guard failed before prediction;not a model-force failure" if job == "12405" else
                          "Exact seven-image predictions complete for both models on CUDA;geometry reviewed;not DFT accuracy,TS or barrier validation")
            remote = receipt["remote_root"]
            submitted = receipt["submitted_at"]
            checked = raw["checked_at"]
            command = "scontrol show job -o " + job
            queue = "gpu"
            scheduler = "Slurm"
            host = "BUCT(sbq)"
            paths = [base / name for name in ("submission_receipt.json", "return_inventory.json")]
            paths += [base / "package" / name for name in ("request.json", "bundle.json")]
            returned = base / ("return_" + job)
            paths += [returned / name for name in ("collection_receipt.json", "worker_exit.json")]
            manifest = returned / "output/dual_model_gpu_ml_neb_path_manifest.candidate.json"
            if manifest.exists():
                paths.append(manifest)
            paths += [returned / f"output/images/{i:02d}/POSCAR" for i in range(7)]
        else:
            receipt = load_json_object(base / "submission_record.json")
            attempt = load_json_object(base / "submission_attempt.json")
            if receipt["job_id"] != job or receipt["status"] != "SUBMITTED":
                raise ValueError("VASP submission receipt differs.")
            query = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "sunboquan-codex",
                                    "bjobs", "-a", "-w", job], capture_output=True, text=True, timeout=30)
            checked = datetime.now(timezone.utc).isoformat()
            evidence = {"job_id": job, "checked_at": checked, "source_command": "bjobs -a -w " + job,
                        "returncode": query.returncode, "stdout": query.stdout, "stderr": query.stderr}
            write_json_exclusive(OUT / "vasp_scheduler.json", evidence)
            fields = next((line.split() for line in query.stdout.splitlines() if line.split() and line.split()[0] == job), None)
            if query.returncode or fields is None or fields[2] not in ("PEND", "RUN"):
                raise ValueError("Need result-aware review if job is not pending/running.")
            status = fields[2]
            workflow = "submitted" if status == "PEND" else "running"
            scientific = "Initial ordinary NEB only;electronic,ionic,geometry,TS and barrier validity not assessed"
            native = query.stdout
            command = evidence["source_command"]
            queue = fields[3]
            host, scheduler, remote = "sunboquan-codex", "LSF", receipt["remote_dir"]
            submitted = attempt["created_at_utc"]
            preflight = load_json_object(base / "submission_preflight.json")
            if not preflight["passed"] or preflight["bundle_sha256"] != receipt["bundle_sha256"]:
                raise ValueError("Submitted canonical preflight differs.")
            paths = [base / name for name in preflight["files"]]
            paths += [base / name for name in ("submission_record.json", "submission_attempt.json", "submission_preflight.json",
                      "submission_decision.v2.json", "user_execution_authorization.v2.json", "path_review.json",
                      "path_geometry_diagnosis.json", "path_generation_report.json", "reaction_contract.normalized.json")]
            paths.append(OUT / "vasp_scheduler.json")
        rows["calculations"].append({"calculation_id": cid,
            "parent_calculation_id": "fe110_ch_co_ts_20261110_job" + parent if parent else None,
            "module": "transition_state_search", "purpose": purpose, "scientific_system": "true_Fe110_Fe45_CH_CO_to_CHCO_C2HO",
            "workflow_status": workflow, "created_at": submitted, "source_record": str(paths[0]),
            "notes": scientific + ";No accepted ML/DFT energy or speedup claim;no fine-tuning or final TS acceptance."})
        rows["jobs"].append({"job_record_id": jid, "calculation_id": cid, "scheduler_job_id": job,
            "scheduler": scheduler, "server_alias": host, "queue": queue, "remote_directory": remote,
            "submit_script": "script.lsf" if job == "9994246" else "run.sbatch", "submitted_at": submitted})
        rows["job_status_history"].append({"job_record_id": jid, "scheduler_status": status, "scientific_status": scientific,
            "checked_at": checked, "source_command": command, "source_text": native, "reviewer": REVIEWER,
            "notes": "Native scheduler evidence is not scientific convergence;Slurm COMPLETED normalized to DONE;raw state retained."})
        for i, path in enumerate(dict.fromkeys(paths)):
            if not path.is_file():
                raise ValueError("Missing actual provenance source: " + str(path))
            rows["files"].append({"file_id": cid + f"__provenance_{i:03d}", "calculation_id": cid,
                "job_record_id": jid, "role": "reviewed_input_prediction_or_native_job_evidence", "filename": path.name,
                "local_path": str(path), "storage_mode": "local_only", "byte_size": path.stat().st_size,
                "sha256": sha256_file(path), "existence_status": "confirmed", "notes": "No accepted scientific result."})
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch", "batch_id": "fe110_ch_co_ts_jobs_20261110_v1",
             "created_at": datetime.now(timezone.utc).isoformat(), "reviewer": REVIEWER,
             "reason": "User-authorized GPU then work-side reviewed VASP handoff;three actual job provenance records only.", "rows": rows}
    write_json_exclusive(OUT / "registry_batch.json", batch)
    print("PREPARED", {key: len(value) for key, value in rows.items()}, "accepted_results=0")


def verify():
    batch = load_json_object(OUT / "registry_batch.json")
    count = 0
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        for table, rows in batch["rows"].items():
            for row in rows:
                keys = list(row)
                query = 'SELECT COUNT(*) FROM "' + table + '" WHERE ' + ' AND '.join('"' + key + '" IS ?' for key in keys)
                if db.execute(query, tuple(row[key] for key in keys)).fetchone()[0] != 1:
                    raise ValueError("Job metadata readback differs: " + table)
                count += 1
        for item in batch["rows"]["calculations"]:
            if db.execute("SELECT 1 FROM results WHERE calculation_id=?", (item["calculation_id"],)).fetchone():
                raise ValueError("Candidate-stage job acquired scientific acceptance.")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Registry integrity failed.")
    write_json_exclusive(OUT / "registry_verification.json", {"status": "PASS", "rows_read_back": count,
        "jobs": 3, "accepted_scientific_results": 0})
    print("VERIFIED", count, "metadata rows;accepted_results=0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    {"prepare": prepare, "verify": verify}[parser.parse_args().phase]()
