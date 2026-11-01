"""Prepare final workflow projections after verified Excel publication; never apply."""
from datetime import datetime, timezone

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry

from .collect import BASE, DB, OUT


def main():
    workbook = load_json_object(OUT / "workbook_verification.json")
    manifest = load_json_object(OUT / "publication_manifest.json")
    readback = load_json_object(OUT / "registry_readback.json")
    if workbook["status"] != "PASS" or readback["status"] != "PASS" or workbook["workbook_sha256"] != readback["workbook_sha256"]:
        raise ValueError("saved workbook and registry verification must pass first")
    decisions = load_json_object(OUT / "decisions.json")
    reviewer, now = decisions["reviewer"], datetime.now(timezone.utc).isoformat()
    sources = load_json_object(OUT / "sources.json")["records"]
    candidate = next(r for r in sources if r["name"] == "paired_06_C_candidate")
    cid = candidate["calculation_id"]
    old_review_path = BASE / "dedup_final_review_20261021_v1/review.json"
    old = next(r for r in load_json_object(old_review_path)["rows"] if r["name"] == candidate["name"])
    stderr_path = OUT / "scheduler/bjobs.stderr.txt"
    if f"Job <{candidate['job_id']}> is not found" not in stderr_path.read_text():
        raise ValueError("missing scheduler-unavailable evidence")
    reason = "No authoritative scheduler DONE evidence recovered from bjobs, bacct or all-history bhist; retain the source-bound converged geometry review without formal acceptance."
    review_path = OUT / "scientific_reviews/paired_06_C_candidate_blocked.json"
    write_json_exclusive(review_path, {"decision": "needs_review", "reason": reason, "reviewer": reviewer,
        "reviewed_at": now, "old_review_sha256": sha256_file(old_review_path), "record": old,
        "scheduler_unavailable_evidence": str(stderr_path), "scheduler_evidence_sha256": sha256_file(stderr_path),
        "accepted_numeric_energy_published": False})
    changes = []
    with open_registry(DB) as con:
        con.execute("PRAGMA query_only=ON")
        for item in manifest["accepted"]:
            status = con.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (item["calculation_id"],)).fetchone()[0]
            receipt = con.execute("SELECT registry_id,row_number FROM excel_promotions WHERE promotion_id=?", (item["promotion_id"],)).fetchone()
            if status != "accepted" or receipt[0] != item["calculation_id"] or receipt[1] != item["row"]:
                raise ValueError("accepted/published state changed before closure")
            changes.append({"status_change_id": item["calculation_id"] + "_excel_complete_20261030",
                "calculation_id": item["calculation_id"], "expected_workflow_status": "accepted",
                "new_workflow_status": "excel_promoted", "changed_at": now, "reviewer": reviewer,
                "reason": "Accepted source, exact promotion receipt and saved XLSX values/styles independently verified; original64 rows preserved."})
        job = con.execute("SELECT * FROM jobs WHERE calculation_id=? AND scheduler_job_id=?", (cid, candidate["job_id"])).fetchone()
        current = con.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (cid,)).fetchone()[0]
        if current != "running":
            raise ValueError("preserve unexpected pending-candidate workflow; reconcile before closure")
        changes.append({"status_change_id": cid + "_blocked_acceptance_20261030", "calculation_id": cid,
            "expected_workflow_status": current, "new_workflow_status": "needs_review", "changed_at": now,
            "reviewer": reviewer, "reason": reason})
        event_id = con.execute("SELECT coalesce(max(status_event_id),0)+1 FROM job_status_history").fetchone()[0]
    scheduler = load_json_object(OUT / "scheduler/receipt.json")
    prefix = cid + "_blocked_acceptance_20261030"
    rows = {
        "files": [{"file_id": prefix + "_review_file", "calculation_id": cid, "job_record_id": job["job_record_id"],
            "role": "scientific_review", "filename": review_path.name, "local_path": str(review_path),
            "storage_mode": "local_only", "sha256": sha256_file(review_path),
            "byte_size": review_path.stat().st_size, "existence_status": "confirmed"}],
        "reviews": [{"review_id": prefix + "_review", "calculation_id": cid,
            "review_type": "adsorption_completion_missing_scheduler_terminal", "decision": "needs_review",
            "reviewer": reviewer, "reviewed_at": now, "evidence": str(review_path) + "#sha256=" + sha256_file(review_path), "reason": reason}],
        "job_status_history": [{"status_event_id": event_id, "job_record_id": job["job_record_id"],
            "scheduler_status": "UNKNOWN", "scientific_status": "reviewed_converged_pending_scheduler",
            "checked_at": scheduler["checked_at"], "source_command": scheduler["commands"][0]["command"],
            "source_text": f"Job <{candidate['job_id']}> is not found", "reviewer": reviewer,
            "notes": "Unavailable queue history is UNKNOWN, never inferred DONE; the prior converged structural review is retained separately."}],
    }
    write_json_exclusive(OUT / "closure_batch.json", {"schema_version": 1,
        "document_kind": "calculation_registry_batch", "batch_id": "fe110_c2_table_closure_20261030_v1",
        "created_at": now, "reviewer": reviewer, "reason": decisions["authorizing_user_request"],
        "rows": rows, "workflow_status_changes": changes})
    print("PREPARED closure:3 published workflows,1 blocked candidate,truthful UNKNOWN scheduler;no new scientific result")


if __name__ == "__main__":
    main()
