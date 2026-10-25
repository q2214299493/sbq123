"""Capture exact14-job scheduler evidence and plan provenance-only registry rows."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess

from archive.fe110_reico_sampling93_20261022.submission_review import file_row
from scripts.aqcat25_ts_schema import validate_document
from scripts.artifact_io import (
    load_json_object, sha256_text, source_file_manifest,
    source_file_manifest_valid, write_json_exclusive,
)
from scripts.neb_agent.submission import submission_status
from scripts.registry_write import plan_registry_batch
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence
from scripts.state_manager.job_lifecycle import JOB_ALIASES
from .submit import AUTH, HOST, INPUTS, OUTPUT, ROOT


def collect():
    summary = load_json_object(OUTPUT / "submission_summary.json")
    if not source_file_manifest_valid(summary) or len(summary["records"]) != 14:
        raise ValueError("all14native receipts required")
    ids = [r["job_id"] for r in summary["records"]]
    if len(set(ids)) != 14:
        raise ValueError("duplicate LSF job identity")
    command = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               HOST, "bjobs", "-a", *ids]
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=40, check=False)
    checked = datetime.now(timezone.utc).isoformat()
    query = {"argv": command, "returncode": process.returncode, "stdout": process.stdout,
             "stderr": process.stderr, "stdout_sha256": sha256_text(process.stdout)}
    write_json_exclusive(OUTPUT / "scheduler_query.json", query)
    if process.returncode:
        raise ValueError("exact-ID scheduler query failed;preserve this checkpoint")
    jobs, evidence = [], []
    for receipt in summary["records"]:
        status = _parse_lsf_bjobs(process.stdout, receipt["job_id"])
        row = {"schema_version": 1, "document_kind": "scheduler_job_evidence",
            "stage": "vasp_force_label" if receipt["role"] == "single_points" else "adsorption_relaxation",
            "scheduler": "LSF", "server_alias": HOST, "job_id": receipt["job_id"],
            "status": status, "checked_at": checked, "source_command": " ".join(command), "query": query}
        validate_document(row, expected_kind="scheduler_job_evidence")
        validate_stored_lsf_evidence(row)
        evidence.append(row)
        jobs.append({"sample_id": receipt["sample_id"], "role": receipt["role"],
            "job_id": receipt["job_id"], "status": status, "remote_dir": receipt["remote_dir"]})
    write_json_exclusive(OUTPUT / "scheduler_evidence.json", {"jobs": evidence})
    snapshot = {"checked_at": checked, "jobs": jobs,
        "status_counts": dict(Counter(r["status"] for r in jobs)),
        "query": query, "scientific_outputs_reviewed": False,
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "submission_summary.json",
            OUTPUT / "scheduler_query.json", OUTPUT / "scheduler_evidence.json"])}
    write_json_exclusive(OUTPUT / "scheduler_snapshot.json", snapshot)
    print({"successful_native_receipts": 14, "scheduler": snapshot["status_counts"],
           "checked_at": checked})


def registry_plan():
    snapshot = load_json_object(OUTPUT / "scheduler_snapshot.json")
    summary = load_json_object(OUTPUT / "submission_summary.json")
    if not source_file_manifest_valid(snapshot) or not source_file_manifest_valid(summary):
        raise ValueError("scheduler or receipt evidence changed")
    ready = load_json_object(OUTPUT / "ready_for_submission.json")["cases"]
    by_id = {r["sample_id"]: r for r in ready}
    states = {r["job_id"]: r["status"] for r in snapshot["jobs"]}
    previous = load_json_object(INPUTS.parent / "grouped_supplement_20261025_v1/proposals.json")
    old_jobs = {r["sample_id"]: r["source_job_id"] for r in previous["optimization_sources_already_labelled"]}
    rows = {"calculations": [], "jobs": [], "job_status_history": [], "files": []}
    for receipt in summary["records"]:
        case = by_id[receipt["sample_id"]]
        directory = Path(case["directory"])
        live = submission_status(directory)
        if live["status"] != "SUBMITTED" or live["job_id"] != receipt["job_id"]:
            raise ValueError("native receipt changed")
        job_id, name = receipt["job_id"], receipt["sample_id"]
        calculation = "fe110_grouped14_" + name + "_" + job_id
        job = "job_" + calculation
        parent = ("fe110_reico_sampling93_20261022_v1_" + name.split("_step")[0]
                  if case["role"] == "single_points" else
                  "fe110_reico_labels280_" + name + "_" + old_jobs[name])
        attempt = load_json_object(directory / "submission_attempt.json")
        rows["calculations"].append({"calculation_id": calculation, "module": "adsorption_workflow",
            "purpose": "Authorized grouped supplement " + case["role"],
            "scientific_system": "true_Fe110_Fe45_" + case["composition"],
            "parent_calculation_id": parent, "workflow_status": JOB_ALIASES.get(states[job_id], states[job_id]).lower(),
            "created_at": attempt["created_at_utc"], "source_record": str(directory / "prepared_case.json"),
            "notes": "train;32cores;NSW=" + str(case["incar"]["NSW"]) + ";no automatic retry,continuation or training;new labels unreviewed"})
        match = re.search(r"queue <([^>]+)>", receipt["submit_stdout"])
        if not match:
            raise ValueError("actual submission queue missing")
        rows["jobs"].append({"job_record_id": job, "calculation_id": calculation,
            "scheduler_job_id": job_id, "scheduler": "LSF", "server_alias": HOST,
            "queue": match[1], "remote_directory": receipt["remote_dir"], "submit_script": "script.lsf"})
        rows["job_status_history"].append({"job_record_id": job, "scheduler_status": states[job_id],
            "scientific_status": "Not reviewed;SCF,geometry,forces and magnetic moments pending",
            "checked_at": snapshot["checked_at"], "source_command": " ".join(snapshot["query"]["argv"]),
            "source_text": "\n".join(line for line in snapshot["query"]["stdout"].splitlines()
                if line.split() and line.split()[0] in {"JOBID", job_id}) + "\n",
            "reviewer": "Codex", "notes": "Scheduler evidence only;no scientific-result acceptance"})
        provenance = ["input_profile.json", "POTCAR.metadata.json", "incar_custodian_validation.json",
            "submission_preflight.json", "prepared_case.json", "submission_geometry_review.json",
            "submission_no_output_analysis.json", "user_execution_authorization.json", "execution_decision.json",
            "submission_attempt.json", "submission_record.json"]
        for filename in [*case["input_hashes"], *provenance]:
            row = file_row(directory / filename, calculation, job, receipt["remote_dir"],
                "vasp_input" if filename in case["input_hashes"] else "submission_provenance")
            if filename in case["input_hashes"]:
                row["remote_path"] = receipt["remote_dir"] + "/" + filename
            rows["files"].append(row)
        potcar = load_json_object(directory / "POTCAR.metadata.json")
        rows["files"].append({"file_id": "file_" + calculation + "_POTCAR",
            "calculation_id": calculation, "job_record_id": job, "role": "vasp_input",
            "filename": "POTCAR", "remote_path": receipt["remote_dir"] + "/POTCAR",
            "storage_mode": "remote_only", "byte_size": potcar["bytes"],
            "sha256": receipt["potcar_sha256"], "existence_status": "confirmed",
            "license_or_sensitivity": "licensed_VASP_POTCAR_remains_remote",
            "notes": "Exact target POTCAR hash verified by native executor immediately before bsub"})
    for path in [INPUTS / "plan.json", INPUTS / "verification.json", OUTPUT / "ready_for_submission.json",
                 OUTPUT / "submission_summary.json", OUTPUT / "scheduler_snapshot.json", AUTH]:
        rows["files"].append(file_row(path, calculation, job, receipt["remote_dir"], "batch_submission_provenance"))
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_grouped14_submission_20261025_v1",
        "created_at": datetime.now(timezone.utc).isoformat(), "reviewer": "Codex",
        "reason": "Record exact14human-authorized successful submissions and evidence;no accepted results",
        "rows": rows}
    write_json_exclusive(OUTPUT / "registry_batch.json", batch)
    plan = plan_registry_batch(ROOT / "data/project_registry.sqlite3", batch)
    write_json_exclusive(OUTPUT / "registry_plan.json", plan)
    print({"plan_sha256": plan["plan_sha256"], "inserts": plan["insert_count"],
           "updates": plan["update_count"], "scope": plan["scope"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["collect", "registry-plan"])
    args = parser.parse_args()
    collect() if args.action == "collect" else registry_plan()
