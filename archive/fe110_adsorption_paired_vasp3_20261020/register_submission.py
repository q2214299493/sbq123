"""Plan only job/input provenance, not scientific results or acceptance."""
import argparse
import json
from datetime import datetime, timezone

from archive.fe110_adsorption_paired_vasp3_20261020.prepare import DEST, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_mutations import plan_registry_batch
from scripts.scheduler_evidence import validate_stored_lsf_evidence


def build_batch():
    summary = load_json_object(DEST / "submission_summary.json")
    manifest = load_json_object(DEST / "batch_manifest.json")
    if summary["new_VASP_submitted"] != 6 or summary["source_manifest_sha256"] != sha256_file(DEST / "batch_manifest.json"):
        raise ValueError("not the exact six-job submitted batch")
    prepared = {(j["name"], j["arm"]): j for j in manifest["jobs"]}
    remote = json.loads(load_json_object(DEST / "remote_submission_precheck.json")["stdout"])
    pots = {p["source"]: p for p in remote["potcars"]}
    rows = {k: [] for k in ("calculations", "jobs", "job_status_history", "files")}
    for job in summary["records"]:
        item = prepared[job["name"], job["arm"]]
        folder = ROOT / item["path"]
        receipt = load_json_object(folder / "submission_record.json")
        reservation = load_json_object(folder / "submission_attempt.json")
        scheduler = load_json_object(folder / "scheduler_after_submission.json")
        validate_stored_lsf_evidence(scheduler)
        if (sha256_file(folder / "submission_record.json") != job["receipt_sha256"]
                or sha256_file(folder / "scheduler_after_submission.json") != job["scheduler_evidence_sha256"]
                or scheduler["job_id"] != job["job_id"] or scheduler["status"] != job["scheduler_status"]
                or receipt["bundle_sha256"] != item["bundle_sha256"] or receipt["status"] != "SUBMITTED"):
            raise ValueError("submission/scheduler binding changed")
        now = scheduler["checked_at"]
        cid = f"fe110_ads_pair3_{job['name']}_{job['arm']}_{job['job_id']}"
        jid = "job_" + cid
        source = (DEST / "submission_summary.json").relative_to(ROOT).as_posix()
        rows["calculations"].append({"calculation_id": cid, "module": "adsorption_workflow",
            "purpose": f"Matched VASP relaxation benchmark {job['name']} {job['arm']};no speedup claim yet",
            "scientific_system": "true_Fe110_5layer_Fe45_C2_adsorption",
            "workflow_status": "running" if scheduler["status"] == "RUN" else "submitted",
            "created_at": reservation["created_at_utc"], "source_record": source,
            "notes": "Job/input provenance only;chemistry,convergence,final minimum and model benefit not yet assessed."})
        rows["jobs"].append({"job_record_id": jid, "calculation_id": cid,
            "scheduler_job_id": job["job_id"], "scheduler": "LSF", "server_alias": item["host"],
            "queue": "Gkn_normal", "remote_directory": job["remote_dir"], "submit_script": "script.lsf",
            "submitted_at": datetime.fromtimestamp((folder / "submission_record.json").stat().st_mtime, timezone.utc).isoformat()})
        rows["job_status_history"].append({"job_record_id": jid, "scheduler_status": scheduler["status"],
            "scientific_status": "Not assessed", "checked_at": now, "source_command": scheduler["source_command"],
            "source_text": scheduler["query"]["stdout"], "reviewer": "Codex",
            "notes": "First post-submission live observation;RUN is not electronic or ionic convergence."})
        for filename in (*item["files"], "submission_preflight.json", "user_execution_authorization.json",
                         "submission_decision.json", "submission_record.json", "submission_attempt.json",
                         "scheduler_after_submission.json"):
            path = folder / filename
            if filename in item["files"] and sha256_file(path) != item["files"][filename]:
                raise ValueError("registered input changed")
            stat = path.stat()
            rows["files"].append({"file_id": f"file_{cid}_{filename.replace('.', '_')}",
                "calculation_id": cid, "job_record_id": jid, "role": "initial_structure" if filename == "POSCAR" else "input_or_submission_evidence",
                "filename": filename, "local_path": str(path.resolve()),
                "remote_path": job["remote_dir"] + "/" + filename if filename in item["files"] else None,
                "storage_mode": "repository", "byte_size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "sha256": sha256_file(path), "existence_status": "confirmed",
                "license_or_sensitivity": "project_internal"})
        pot = pots[item["potcar_source"]]
        rows["files"].append({"file_id": f"file_{cid}_POTCAR", "calculation_id": cid, "job_record_id": jid,
            "role": "licensed_runtime_input", "filename": "POTCAR", "remote_path": job["remote_dir"] + "/POTCAR",
            "storage_mode": "remote_only", "byte_size": pot["bytes"], "sha256": item["potcar_sha256"],
            "existence_status": "confirmed", "license_or_sensitivity": "licensed_VASP_POTCAR",
            "notes": "Exact source/order/SHA checked live;canonical executor verified copied remote bytes before bsub."})
    return {"schema_version": 1, "document_kind": "calculation_registry_batch",
            "batch_id": "fe110_adsorption_paired3_submitted_20261020", "created_at": summary["checked_at"],
            "reviewer": "Codex", "reason": "User explicitly authorized these six submissions;record truthful jobs and input provenance only.",
            "rows": rows}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    batch = build_batch()
    write_json_exclusive(DEST / "submission_registry_batch.json", batch)
    plan = plan_registry_batch(ROOT / "data/project_registry.sqlite3", batch)
    write_json_exclusive(DEST / "submission_registry_plan.json", plan)
    print(json.dumps({"scope": plan["scope"], "plan_sha256": plan["plan_sha256"],
                      "counts": {k: len(v) for k, v in batch["rows"].items()},
                      "insert_count": plan["insert_count"]}))


if __name__ == "__main__":
    main()
