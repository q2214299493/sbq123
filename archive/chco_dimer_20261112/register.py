"""Register job provenance only; scientific TS and energy acceptance are excluded."""
import argparse
from datetime import datetime, timezone

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.registry_transactions import approve_plan
from scripts.registry_write import apply_registry_batch
from .run import ROOT, REVIEW, OUT, HOST, REMOTE, AUTHORITY

DB = ROOT / "data/project_registry.sqlite3"
DEST = OUT / "registration"
REVIEWER = "Codex work-side review under explicit Dimer authorization 2026-11-12"


def prepare():
    if DEST.exists():
        raise ValueError("Registration already prepared; inspect existing plan/receipt.")
    receipt = load_json_object(OUT / "submission_record.json")
    attempt = load_json_object(OUT / "submission_attempt.json")
    preflight = load_json_object(OUT / "submission_preflight.json")
    scheduler = load_json_object(OUT / "initial_scheduler_evidence.json")
    parent_scheduler = load_json_object(REVIEW / "ordinary_neb_scheduler_evidence.json")
    if (receipt["status"] != "SUBMITTED" or receipt["job_id"] != scheduler["job_id"]
            or scheduler["status"] not in ("PEND", "RUN")
            or parent_scheduler["status"] != "DONE"
            or preflight["bundle_sha256"] != receipt["bundle_sha256"]):
        raise ValueError("Actual submission and native scheduler evidence differ.")
    parent = "fe110_ch_co_ts_20261110_job9994246"
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        state = db.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (parent,)).fetchone()
        if state is None or state[0] != "submitted":
            raise ValueError("Parent current workflow changed; review before planning.")
    cid = "fe110_ch_co_dimer_20261112_job" + receipt["job_id"]
    jid = "job_" + cid
    scientific = "Dimer submitted from reviewed ordinary NEB image05/local04-06;no Dimer convergence,frequency,TS acceptance or barrier yet"
    rows = {
        "calculations": [{"calculation_id": cid, "parent_calculation_id": parent,
            "module": "transition_state_search", "purpose": "CH+CO C-C coupling Dimer;32MPI/32pernode;reviewed image05 and local04/06 tangent",
            "scientific_system": "true_Fe110_Fe45_CH_CO_to_CHCO_C2HO",
            "workflow_status": "submitted" if scheduler["status"] == "PEND" else "running",
            "created_at": attempt["created_at_utc"], "source_record": str(OUT / "submission_record.json"),
            "notes": scientific + ";parent CC sampling warning retained;no protocol change"}],
        "jobs": [{"job_record_id": jid, "calculation_id": cid, "scheduler_job_id": receipt["job_id"],
            "scheduler": "LSF", "server_alias": HOST, "queue": "Gkn_normal", "remote_directory": REMOTE,
            "submit_script": "script.lsf", "submitted_at": attempt["created_at_utc"]}],
        "job_status_history": [
            {"job_record_id": jid, "scheduler_status": scheduler["status"], "scientific_status": scientific,
             "checked_at": scheduler["checked_at"], "source_command": scheduler["source_command"],
             "source_text": scheduler["query"]["stdout"], "reviewer": REVIEWER,
             "notes": "Queue state is not electronic/ionic or scientific convergence."},
            {"job_record_id": "job_" + parent, "scheduler_status": "DONE",
             "scientific_status": "Ordinary NEB normal ending207steps;all required-accuracy markers;reviewed triad hard checks pass;sampling warning retained;not TS acceptance",
             "checked_at": parent_scheduler["checked_at"], "source_command": parent_scheduler["source_command"],
             "source_text": parent_scheduler["query"]["stdout"], "reviewer": REVIEWER,
             "notes": "Separate queue DONE from force definitions and refinement eligibility."},
        ],
        "files": [],
    }
    paths = [OUT / name for name in preflight["files"]]
    paths += [OUT / name for name in ("input_build.json", "mode_metrics.json", "mode_review.png", "mode_validation.json",
        "submission_preflight.json", "remote_preflight.json", "user_execution_authorization.json", "submission_request.json",
        "submission_decision.json", "submission_attempt.json", "submission_record.json", "initial_scheduler_evidence.json")]
    paths += [AUTHORITY, REVIEW / "ordinary_neb_scheduler_evidence.json", REVIEW / "reaction_contract.reviewed.json",
              REVIEW / "explicit_dimer_intent_20261112.json", REVIEW / "explicit_dimer_decision_20261112.json",
              REVIEW / "path/neb_analysis.json", REVIEW / "path/path_geometry_diagnosis.json",
              REVIEW / "path/neb_path_quality.json", REVIEW / "path/path_review.json"]
    for i, path in enumerate(dict.fromkeys(paths)):
        rows["files"].append({"file_id": cid + f"__provenance_{i:03d}", "calculation_id": cid,
            "job_record_id": jid, "role": "dimer_review_input_submission_and_parent_provenance", "filename": path.name,
            "local_path": str(path), "storage_mode": "local_only", "byte_size": path.stat().st_size,
            "sha256": sha256_file(path), "existence_status": "confirmed", "notes": "Starting-candidate/job evidence only;not an accepted scientific result."})
    checked = datetime.now(timezone.utc).isoformat()
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_ch_co_dimer_20261112_v1", "created_at": checked, "reviewer": REVIEWER,
        "reason": "Explicit user Dimer choice;actual single submission and completed parent provenance;zero accepted results.",
        "rows": rows, "workflow_status_changes": [{"status_change_id": "chco9994246_done_20261112_v1",
            "calculation_id": parent, "expected_workflow_status": "submitted", "new_workflow_status": "done",
            "changed_at": checked, "reviewer": REVIEWER,
            "reason": "Native DONE and completed hash-verified owner review;not acceptance of a saddle or barrier."}]}
    DEST.mkdir()
    write_json_exclusive(DEST / "batch.json", batch)
    print({"rows": {key: len(value) for key, value in rows.items()}, "workflow_changes": 1, "accepted_results": 0})


def apply_reviewed():
    """Call only after actual inspection of the saved canonical plan."""
    batch = load_json_object(DEST / "batch.json")
    plan = load_json_object(DEST / "plan.json")
    approval = approve_plan(plan, reviewer=REVIEWER, reviewed_at=datetime.now(timezone.utc).isoformat())
    write_json_exclusive(DEST / "approval.json", approval)
    receipt = apply_registry_batch(DB, batch, confirmed_sha256=plan["plan_sha256"], plan=plan, approval=approval)
    write_json_exclusive(DEST / "receipt.json", receipt)
    print({key: value for key, value in receipt.items() if key in ("batch_id", "inserted", "updated", "unchanged", "already_applied")})


def verify():
    batch = load_json_object(DEST / "batch.json")
    count = 0
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        for table, rows in batch["rows"].items():
            for row in rows:
                keys = list(row)
                query = 'SELECT COUNT(*) FROM "' + table + '" WHERE ' + ' AND '.join('"' + key + '" IS ?' for key in keys)
                if db.execute(query, tuple(row[key] for key in keys)).fetchone()[0] != 1:
                    raise ValueError("Readback differs: " + table)
                count += 1
        cid = batch["rows"]["calculations"][0]["calculation_id"]
        if db.execute("SELECT 1 FROM results WHERE calculation_id=?", (cid,)).fetchone():
            raise ValueError("Unexpected scientific result acceptance.")
        for change in batch["workflow_status_changes"]:
            if db.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (change["calculation_id"],)).fetchone()[0] != change["new_workflow_status"]:
                raise ValueError("Workflow projection differs.")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Registry integrity failed.")
    write_json_exclusive(DEST / "verification.json", {"status": "PASS", "metadata_rows_verified": count,
                         "workflow_changes_verified": 1, "accepted_results": 0})
    print("PASS", count, "metadata rows;1 parent workflow change;0 accepted results")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("prepare", "apply-reviewed", "verify"))
    {"prepare": prepare, "apply-reviewed": apply_reviewed, "verify": verify}[parser.parse_args().phase]()
