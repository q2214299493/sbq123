"""Append source-Dimer completion and VFA2260 job evidence;no accepted TS result."""
import argparse

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.registry_transactions import approve_plan
from scripts.registry_write import apply_registry_batch
from .workflow import ROOT, REVIEW, SOURCE, DEST, CONTRACT, AUTHORITY, HOST, REMOTE, now

DB = ROOT / "data/project_registry.sqlite3"
OUT = DEST / "registration"
REVIEWER = "Codex reviewed source and actual VFA submission under explicit conditional user authority 2026-11-15"


def prepare():
    if OUT.exists():
        raise ValueError("Registry package exists;inspect receipts before any retry.")
    receipt = load_json_object(DEST / "submission_record.json")
    attempt = load_json_object(DEST / "submission_attempt.json")
    preflight = load_json_object(DEST / "submission_preflight.json")
    scheduler = load_json_object(DEST / "initial_scheduler_evidence.json")
    parent_scheduler = load_json_object(SOURCE / "scheduler_evidence.json")
    if (receipt["status"] != "SUBMITTED" or scheduler["job_id"] != receipt["job_id"]
            or parent_scheduler["status"] != "DONE" or scheduler["status"] not in ("PEND", "RUN")
            or receipt["bundle_sha256"] != preflight["bundle_sha256"]):
        raise ValueError("Actual job/native scheduling/input evidence differs.")
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        parent = dict(db.execute("SELECT c.calculation_id,c.workflow_status,j.job_record_id FROM calculations c "
            "JOIN jobs j ON j.calculation_id=c.calculation_id WHERE j.server_alias=? AND j.scheduler_job_id=?",
            (HOST, "9998592")).fetchone())
    if parent["workflow_status"] not in ("submitted", "running"):
        raise ValueError("Parent current projection changed;review instead of overwriting it.")
    cid = "fe110_ch_co_vfa_20261115_job" + receipt["job_id"]
    jid = "job_" + cid
    scientific = "Local C45/C46/O47/H48 partial-Hessian diagnostic only;user accepts Dimer soft residuals for frequency,not TS acceptance"
    rows = {"calculations": [{"calculation_id": cid, "parent_calculation_id": parent["calculation_id"],
        "module": "ts_vibrational_validation", "purpose": scientific + ";32MPI/32pernode;no pilot",
        "scientific_system": "true_Fe110_Fe45_CH_CO_to_CHCO_C2HO", "workflow_status": "submitted" if scheduler["status"] == "PEND" else "running",
        "created_at": attempt["created_at_utc"], "source_record": str(DEST / "submission_record.json"),
        "notes": "No frequencies,accepted TS,barrier,thermal correction or kinetics claim."}],
        "jobs": [{"job_record_id": jid, "calculation_id": cid, "scheduler_job_id": receipt["job_id"],
            "scheduler": "LSF", "server_alias": HOST, "queue": "Gkn_normal", "remote_directory": REMOTE,
            "submit_script": "script.lsf", "submitted_at": attempt["created_at_utc"]}],
        "job_status_history": [], "files": []}
    for job_record, observation, status in ((jid, scheduler, scientific),
            (parent["job_record_id"], parent_scheduler, "Dimer DONE,normal/electronic and max-atom-force/negative-curvature hard checks pass;Force/Torque residuals accepted only for diagnostic frequency;not TS accepted")):
        rows["job_status_history"].append({"job_record_id": job_record, "scheduler_status": observation["status"],
            "scientific_status": status, "checked_at": observation["checked_at"], "source_command": observation["source_command"],
            "source_text": observation["query"]["stdout"], "reviewer": REVIEWER, "notes": "Native queue state and scientific acceptance remain separate."})
    inventory = load_json_object(REVIEW / "remote_inventory.json")
    parent_paths = [SOURCE / item["relative_path"] for item in inventory["files"]]
    parent_paths += [SOURCE / name for name in ("scheduler_evidence.json", "dimer_analysis.json", "final_mode_review.json")]
    parent_paths += [REVIEW / name for name in ("remote_inventory.json", "collection_receipt.json", "geometry_and_mode_metrics.json",
        "final_mode_review.png", "dimer_soft_gate_review.json", "frequency_handoff_gate.json")]
    child_paths = [DEST / name for name in preflight["files"]]
    child_paths += [DEST / name for name in ("input_build.json", "submission_preflight.json", "remote_preflight.json",
        "user_execution_authorization.json", "submission_request.json", "submission_decision.json", "submission_attempt.json",
        "submission_record.json", "initial_scheduler_evidence.json")]
    child_paths += [CONTRACT, AUTHORITY]
    for calculation, job, paths in ((parent["calculation_id"], parent["job_record_id"], parent_paths), (cid, jid, child_paths)):
        for index, path in enumerate(dict.fromkeys(paths)):
            rows["files"].append({"file_id": calculation + f"__vfa20261115_{index:03d}", "calculation_id": calculation,
                "job_record_id": job, "role": "reviewed_source_or_frequency_job_provenance", "filename": path.name,
                "local_path": str(path), "storage_mode": "local_only", "byte_size": path.stat().st_size,
                "sha256": sha256_file(path), "existence_status": "confirmed", "notes": "No accepted TS or frequency result."})
    rows["files"].append({"file_id": cid + "__remote_POTCAR", "calculation_id": cid, "job_record_id": jid,
        "role": "licensed_VASP_input", "filename": "POTCAR", "remote_path": REMOTE + "/POTCAR", "storage_mode": "remote_only",
        "sha256": receipt["potcar_sha256"], "existence_status": "confirmed", "license_or_sensitivity": "VASP licensed;contents excluded from local transfer and Git",
        "notes": "Canonical executor verifies target POTCAR bytes before bsub;hash retained in immutable receipt."})
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch", "batch_id": "chco_vfa_source_and_job_20261115_v1",
        "created_at": now(), "reviewer": REVIEWER, "reason": "Completed Dimer provenance and actual single authorized local-frequency job;zero accepted results.",
        "rows": rows, "workflow_status_changes": [{"status_change_id": "chco_dimer9998592_done_20261115_v1",
            "calculation_id": parent["calculation_id"], "expected_workflow_status": parent["workflow_status"], "new_workflow_status": "done",
            "changed_at": now(), "reviewer": REVIEWER, "reason": "Native DONE and source hard convergence pass;diagnostic-only residual review,not formal TS acceptance."}]}
    OUT.mkdir()
    write_json_exclusive(OUT / "batch.json", batch)
    print({"rows": {key: len(value) for key, value in rows.items()}, "workflow_changes": 1, "accepted_results": 0})


def apply_reviewed():
    batch = load_json_object(OUT / "batch.json")
    plan = load_json_object(OUT / "plan.json")
    approval = approve_plan(plan, reviewer=REVIEWER, reviewed_at=now())
    write_json_exclusive(OUT / "approval.json", approval)
    receipt = apply_registry_batch(DB, batch, confirmed_sha256=plan["plan_sha256"], plan=plan, approval=approval)
    write_json_exclusive(OUT / "receipt.json", receipt)
    print({key: receipt[key] for key in ("inserted", "updated", "already_applied")})


def verify():
    batch = load_json_object(OUT / "batch.json")
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
            raise ValueError("Unexpected accepted result for an unperformed frequency calculation.")
        change = batch["workflow_status_changes"][0]
        if db.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (change["calculation_id"],)).fetchone()[0] != "done":
            raise ValueError("Parent workflow projection differs.")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Registry integrity failed.")
    write_json_exclusive(OUT / "verification.json", {"status": "PASS", "metadata_rows_verified": count,
        "workflow_changes_verified": 1, "accepted_results": 0})
    print("PASS", count, "metadata rows;1 workflow change;0 accepted results")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("prepare", "apply-reviewed", "verify"))
    {"prepare": prepare, "apply-reviewed": apply_reviewed, "verify": verify}[parser.parse_args().phase]()
