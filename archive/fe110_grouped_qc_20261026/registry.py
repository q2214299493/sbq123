"""Plan metadata-only recording of closed jobs and their force-label audit."""
from __future__ import annotations

from datetime import datetime, timezone

from archive.fe110_reico_followup_20261024.collect import save_once
from archive.fe110_reico_sampling93_20261022.submission_review import file_row
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest_valid
from scripts.registry_connection import open_registry
from scripts.registry_write import plan_registry_batch
from .collect import FILES, HOST, OUTPUT, ROOT, scope


def run():
    summary = load_json_object(OUTPUT / "summary.json")
    verified = load_json_object(OUTPUT / "independent_verification.json")
    if not source_file_manifest_valid(summary) or not source_file_manifest_valid(verified) or verified["status"] != "PASS":
        raise ValueError("QC replay/binding required")
    snapshot = load_json_object(OUTPUT / "scheduler_snapshot.json")
    all_rows = load_json_object(OUTPUT / "all_frame_qc_local_only.json")["samples"]
    rows, changes = {"files": [], "job_status_history": []}, []
    with open_registry(ROOT / "data/project_registry.sqlite3") as connection:
        for receipt in scope():
            sid = receipt["sample_id"]
            job = connection.execute("SELECT j.job_record_id,j.calculation_id,j.remote_directory,c.workflow_status "
                "FROM jobs j JOIN calculations c ON c.calculation_id=j.calculation_id "
                "WHERE j.server_alias=? AND j.scheduler_job_id=?", (HOST, receipt["job_id"])).fetchone()
            if job is None or job["remote_directory"] != receipt["remote_dir"]:
                raise ValueError("registered exact job/target missing")
            calc, jid, remote = job["calculation_id"], job["job_record_id"], job["remote_directory"]
            directory = OUTPUT / "collection" / sid
            names = list(FILES) + (["XDATCAR"] if receipt["role"] == "optimizations" else [])
            artifacts = [*[directory / name for name in names], directory / "collection.json", OUTPUT / "case_qc" / (sid + ".json")]
            for path in artifacts:
                item = file_row(path, calc, jid, remote, "force_label_QC_evidence")
                item["file_id"] = "file_" + calc + "_grouped26_" + path.name.replace(".", "_")
                if path.name in names:
                    item["remote_path"] = remote + "/" + path.name
                item["notes"] = "Raw closed-job force-label evidence;not an accepted endpoint or reportable adsorption energy"
                rows["files"].append(item)
            labels = [r for r in all_rows if r["source_job_id"] == receipt["job_id"]]
            qualified = sum(r["data_qc_status"] == "PASS" for r in labels)
            status = ("STATIC_FORCE_LABEL_QC_" + labels[0]["data_qc_status"] if len(labels) == 1
                      else f"TRAJECTORY_FORCE_LABEL_QC_PASS_{qualified}_OF_{len(labels)};IONIC_NOT_CONVERGED")
            rows["job_status_history"].append({"job_record_id": jid, "scheduler_status": "DONE",
                "scientific_status": status + ";not an accepted adsorption endpoint", "checked_at": snapshot["checked_at"],
                "source_command": " ".join(snapshot["query"]["argv"]),
                "source_text": "\n".join(line for line in snapshot["query"]["stdout"].splitlines()
                    if line.split() and line.split()[0] in {"JOBID", receipt["job_id"]}) + "\n",
                "reviewer": "Codex", "notes": "SCF/localmoments/coordinate-force audit;train partition retained;QCsha=" + sha256_file(artifacts[-1])})
            if job["workflow_status"] != "done":
                changes.append({"status_change_id": "grouped26_done_" + calc, "calculation_id": calc,
                    "expected_workflow_status": job["workflow_status"], "new_workflow_status": "done",
                    "changed_at": snapshot["checked_at"], "reviewer": "Codex",
                    "reason": "Exact scheduler DONE;scientific label QC kept separate from workflow state"})
    for name in ("summary.json", "independent_verification.json", "all_frame_qc_local_only.json", "review_binding.json",
                 "training_isolation.json", "eligible_training_candidates.json", "recommended_small_supplement.json",
                 "collection_summary.json", "scheduler_evidence.json", "remote_metadata.json"):
        item = file_row(OUTPUT / name, calc, jid, remote, "batch_force_label_QC_provenance")
        item["file_id"] = "file_" + calc + "_grouped26_batch_" + name.replace(".", "_")
        rows["files"].append(item)
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch", "batch_id": "fe110_grouped14_QC_20261026_v2",
        "created_at": datetime.now(timezone.utc).isoformat(), "reviewer": "Codex",
        "reason": "User-authorized existing14 result recovery and force-label audit;no accepted energy results or training",
        "rows": rows, "workflow_status_changes": changes}
    save_once(OUTPUT / "registry_batch.json", batch)
    plan = plan_registry_batch(ROOT / "data/project_registry.sqlite3", batch)
    save_once(OUTPUT / "registry_plan.json", plan)
    print({k: plan[k] for k in ("plan_sha256", "scope", "insert_count", "update_count", "unchanged_count")})


if __name__ == "__main__":
    run()
