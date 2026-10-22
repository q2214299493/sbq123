"""Read actual submission receipts/LSF evidence and prepare a registry plan only."""
from __future__ import annotations

import argparse
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from archive.fe110_reico_sampling93_20261022 import submit as runner
from scripts.aqcat25_ts_schema import validate_document
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, write_json_exclusive
from scripts.registry_write import plan_registry_batch
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence
from scripts.state_manager.job_lifecycle import JOB_ALIASES

ROOT = runner.ROOT
DEST = runner.DEST
DATABASE = ROOT / "data/project_registry.sqlite3"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def collect(partial=False):
    rows = runner.checked_ready()
    records, outstanding = [], []
    for row in rows:
        directory = DEST / row["sample_id"]
        receipt = runner.submission_status(directory)
        if partial and receipt["status"] != "SUBMITTED":
            outstanding.append({"sample_id": row["sample_id"], "submission_state": receipt["status"]})
            continue
        if (receipt["status"] != "SUBMITTED"
                or receipt["gate_decision_sha256"] != row["decision_sha256"]
                or receipt["remote_dir"] != runner.REMOTE + "/" + row["sample_id"]
                or receipt["potcar_source"] != row["potcar_source"]
                or receipt["potcar_sha256"] != row["potcar_sha256"]):
            raise ValueError("all authorized jobs require exact successful receipts;never retry here")
        records.append({"sample_id": row["sample_id"], **receipt})
    ids = [r["job_id"] for r in records]
    if not records or len(set(ids)) != len(records) or (not partial and len(records) != runner.COUNT):
        raise ValueError("submission IDs are not unique")
    argv = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", runner.HOST, "bjobs", "-a", *ids]
    response = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if response.returncode:
        raise RuntimeError("exact-ID LSF snapshot failed:" + response.stderr[:1000])
    checked = utc_now()
    query = {"argv": argv, "returncode": response.returncode, "stdout": response.stdout,
             "stderr": response.stderr, "stdout_sha256": sha256_text(response.stdout)}
    evidence = []
    for job_id in ids:
        row = {"schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": "vasp_force_label",
               "scheduler": "LSF", "server_alias": runner.HOST, "job_id": job_id,
               "status": _parse_lsf_bjobs(response.stdout, job_id), "checked_at": checked,
               "source_command": " ".join(argv), "query": query}
        validate_document(row, expected_kind="scheduler_job_evidence")
        validate_stored_lsf_evidence(row)
        evidence.append(row)
    snapshot = {"document_kind": "reico280_exact_job_scheduler_snapshot", "checked_at": checked,
                "source_batch_sha256": runner.BATCH_SHA, "query": query,
                "jobs": [{k: r[k] for k in ("job_id", "status", "checked_at")} for r in evidence],
                "status_counts": dict(Counter(r["status"] for r in evidence)),
                "scientific_outputs_reviewed": False}
    snapshot_path = DEST / ("initial_submission_scheduler_snapshot.json" if partial else "scheduler_snapshot.json")
    summary_path = DEST / ("initial_submission_checkpoint.json" if partial else "submission_summary.json")
    write_json_exclusive(snapshot_path, snapshot)
    write_json_exclusive(summary_path, {
        "document_kind": "reico280_authorized_static_submission_summary",
        "status": "PARTIAL_SUBMISSION_STOPPED" if partial else "ALL_280_SUBMITTED",
        "batch_sha256": runner.BATCH_SHA, "new_DFT_jobs_submitted": len(records),
        "existing_DFT_labels_reused": 12, "potential_total_labels": 292, "records": records,
        "outstanding": outstanding, "scheduler_snapshot_path": str(snapshot_path),
        "scheduler_snapshot_sha256": sha256_file(snapshot_path),
        "checked_at": checked, "training_performed": False, "scientific_acceptance": False,
    })
    print({"actual_success_receipts": len(records), "scheduler": snapshot["status_counts"], "checked_at": checked})


def file_row(path, calculation, job, remote_dir, role):
    uploaded = path.name in {"POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "script.lsf"}
    row = {"file_id": "file_" + calculation + "_" + path.name.replace(".", "_"),
           "calculation_id": calculation, "job_record_id": job, "role": role, "filename": path.name,
           "local_path": str(path.resolve()), "storage_mode": "repository", "byte_size": path.stat().st_size,
           "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
           "sha256": sha256_file(path), "existence_status": "confirmed", "license_or_sensitivity": "project_internal",
           "notes": "Exact work-reviewed input/gate/submission provenance;not a scientifically accepted DFT result."}
    if uploaded:
        row["remote_path"] = remote_dir + "/" + path.name
    return row


def registry_plan(partial=False):
    batch = runner.checked_batch()
    summary_path = DEST / ("initial_submission_checkpoint.json" if partial else "submission_summary.json")
    summary = load_json_object(summary_path)
    snapshot_path = Path(summary["scheduler_snapshot_path"])
    snapshot = load_json_object(snapshot_path)
    if (summary["batch_sha256"] != runner.BATCH_SHA
            or summary["new_DFT_jobs_submitted"] != len(summary["records"])
            or (not partial and summary["new_DFT_jobs_submitted"] != runner.COUNT)
            or summary["scheduler_snapshot_sha256"] != sha256_file(snapshot_path)):
        raise ValueError("completed submission evidence changed")
    evidence = {r["job_id"]: r for r in snapshot["jobs"]}
    receipts = {r["sample_id"]: r for r in summary["records"]}
    rows = {"calculations": [], "jobs": [], "job_status_history": [], "files": []}
    artifacts = ["POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "script.lsf", "input_profile.json",
                 "incar_validation.json", "incar_validation_binding.json", "label_request.json",
                 "submission_preflight.json", "submission_geometry_review.json", "submission_no_output_analysis.json",
                 "user_execution_authorization.json", "execution_decision.json", "submission_attempt.json", "submission_record.json"]
    for sample in batch["samples"]:
        name = sample["sample_id"]
        if name not in receipts:
            continue
        directory = DEST / name
        receipt = receipts[name]
        if runner.submission_status(directory) != {k: v for k, v in receipt.items() if k != "sample_id"}:
            raise ValueError("live local receipt differs from the completed summary")
        job_id = receipt["job_id"]
        calculation = "fe110_reico_labels280_" + name + "_" + job_id
        job = "job_" + calculation
        package_name = Path(sample["structure_path"]).parents[4].name
        source = {"sampling6_v1": "fe110_reico_sampling6_20261022_v1_",
                  "sampling93_v1": "fe110_reico_sampling93_20261022_v1_"}[package_name] + sample["family_id"]
        status = evidence[job_id]["status"]
        attempt = load_json_object(directory / "submission_attempt.json")
        rows["calculations"].append({
            "calculation_id": calculation, "module": "adsorption_workflow",
            "purpose": "Authorized fixed-geometry DFT energy/force/magnetic label for selected random Fe110 sampling frame",
            "scientific_system": "true_Fe110_Fe45_" + sample["composition"] + "_random_environment",
            "parent_calculation_id": source, "workflow_status": JOB_ALIASES.get(status, status).lower(),
            "created_at": attempt["created_at_utc"], "source_record": str(directory / "label_request.json"),
            "notes": "partition=" + sample["partition"] + ";32cores;NSW0;no automatic retry or training;SCF/forces/moments unreviewed.",
        })
        rows["jobs"].append({"job_record_id": job, "calculation_id": calculation, "scheduler_job_id": job_id,
                             "scheduler": "LSF", "server_alias": runner.HOST, "queue": "Gkn_normal",
                             "remote_directory": receipt["remote_dir"], "submit_script": "script.lsf"})
        rows["job_status_history"].append({
            "job_record_id": job, "scheduler_status": status,
            "scientific_status": "Not reviewed;electronic convergence,exact raw energy/forces and magnetic moments pending",
            "checked_at": snapshot["checked_at"], "source_command": " ".join(snapshot["query"]["argv"]),
            "source_text": "\n".join(line for line in snapshot["query"]["stdout"].splitlines()
                                     if line.split() and line.split()[0] in {"JOBID", job_id}) + "\n",
            "reviewer": "Codex",
            "notes": "Scheduler state only;full raw snapshot SHA256=" + sha256_file(snapshot_path)
                     + ";no scientific acceptance.",
        })
        for name in artifacts:
            role = "vasp_input" if name in sample["input_hashes"] else "reviewed_submission_provenance"
            rows["files"].append(file_row(directory / name, calculation, job, receipt["remote_dir"], role))
    for shared in [DEST / "batch_request.json", DEST / "ready_for_submission.json", summary_path,
                   snapshot_path, runner.AUTH_SOURCE]:
        rows["files"].append(file_row(shared, calculation, job, receipt["remote_dir"], "batch_submission_provenance"))
    manifest = {"schema_version": 1, "document_kind": "calculation_registry_batch",
                "batch_id": "fe110_reico_labels280_submission_checkpoint_20261023_v1" if partial
                            else "fe110_reico_labels280_submission_20261023_v1",
                "created_at": utc_now(), "reviewer": "Codex",
                "reason": "Record only actual successful authorized submissions and exact input/gate/LSF provenance;no accepted results",
                "rows": rows}
    write_json_exclusive(DEST / "registry_submission_batch.json", manifest)
    plan = plan_registry_batch(DATABASE, manifest)
    write_json_exclusive(DEST / "registry_submission_plan.json", plan)
    print({"plan_sha256": plan["plan_sha256"], "inserts": plan["insert_count"],
           "updates": plan["update_count"], "scope": plan["scope"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "registry-plan", "checkpoint", "registry-checkpoint-plan"))
    args = parser.parse_args()
    {"collect": collect, "registry-plan": registry_plan,
     "checkpoint": lambda: collect(partial=True), "registry-checkpoint-plan": lambda: registry_plan(partial=True)}[args.action]()
