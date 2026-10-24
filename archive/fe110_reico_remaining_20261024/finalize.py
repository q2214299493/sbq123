"""Verify all logical sample receipts and plan the single 76-job registry batch."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from archive.fe110_reico_sampling93_20261022 import submit as original
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, write_json_exclusive
from scripts.neb_agent.submission import preflight, submission_status
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence
from scripts.ts_strategy_engine.execution_gate import require_action
from .checkpoint import registry_plan
from .preflight import OUTPUT
from .recover16 import AUTH, checked_cases


def run():
    cases = checked_cases()
    recovery = {r["sample_id"]: r for r in cases}
    recovered_receipts = load_json_object(OUTPUT / "recovery16_submissions.json")["records"]
    if {r["sample_id"] for r in recovered_receipts} != set(recovery):
        raise ValueError("sixteen-case receipt scope mismatch")
    initial = load_json_object(OUTPUT / "initial_scope.json")
    new_ids = {r["sample_id"] for r in [*initial["eligible"], *initial["unknown"]]}
    records = []
    for row in original.checked_ready():
        sid = row["sample_id"]
        directory = Path(recovery[sid]["proposed_workdir"]) if sid in recovery else original.DEST / sid
        expected_remote = recovery[sid]["proposed_remote_dir"] if sid in recovery else original.REMOTE + "/" + sid
        state = submission_status(directory)
        if state["status"] != "SUBMITTED" or state["remote_dir"] != expected_remote:
            raise ValueError("logical sample lacks exact native success receipt")
        if sha256_file(directory / "execution_decision.json") != state["gate_decision_sha256"]:
            raise ValueError("success receipt gate binding changed")
        gate = load_json_object(directory / "execution_decision.json")
        require_action(directory / "execution_decision.json", original.ACTION, gate["state_sha256"])
        report = preflight(directory, "diagnostic_static", write_report=False)
        if not report["passed"] or report != load_json_object(directory / "submission_preflight.json"):
            raise ValueError("logical sample input/preflight changed after submission")
        records.append({"sample_id": sid, "workdir": str(directory), **state})
    if len(records) != 280 or len({r["job_id"] for r in records}) != 280 or len(new_ids) != 76:
        raise ValueError("logical sample/job scope not 280 unique including76new")
    newly = [r for r in records if r["sample_id"] in new_ids]
    argv = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", original.HOST,
            "bjobs", "-a", *[r["job_id"] for r in newly]]
    response = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    checked = datetime.now(timezone.utc).isoformat()
    query = {"argv": argv, "returncode": response.returncode, "stdout": response.stdout,
             "stderr": response.stderr, "stdout_sha256": sha256_text(response.stdout)}
    if response.returncode:
        write_json_exclusive(OUTPUT / "final_scheduler_query_failure.json", query)
        raise RuntimeError("submitted receipts valid; exact scheduler query failed; do not resubmit")
    jobs = []
    for row in newly:
        evidence = {"schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": "vasp_force_label",
                    "scheduler": "LSF", "server_alias": original.HOST, "job_id": row["job_id"],
                    "status": _parse_lsf_bjobs(response.stdout, row["job_id"]), "checked_at": checked,
                    "source_command": " ".join(argv), "query": query}
        validate_stored_lsf_evidence(evidence)
        jobs.append({"sample_id": row["sample_id"], "job_id": row["job_id"], "status": evidence["status"]})
    resources = subprocess.run(["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", original.HOST, "busers", "-w"],
                               capture_output=True, text=True, timeout=60, check=False)
    if resources.returncode:
        raise RuntimeError("submitted jobs queried; resource query failed; do not resubmit")
    fields = [line.split() for line in resources.stdout.splitlines()]
    resource = dict(zip(fields[0], next(row for row in fields[1:] if row[0] == "nsgkn_chengdj3")))
    if int(resource["MAX"]) != 128 or int(resource["RUN"]) > 128:
        raise ValueError("observed account resource policy differs from128cores")
    scheduler = {"checked_at": checked, "query": query, "jobs": jobs,
                 "status_counts": dict(Counter(r["status"] for r in jobs)),
                 "account_resource_query": {"returncode": resources.returncode, "stdout": resources.stdout, "stderr": resources.stderr},
                 "account_resource_fields": resource, "scientific_outputs_reviewed": False}
    write_json_exclusive(OUTPUT / "final_scheduler_snapshot.json", scheduler)
    write_json_exclusive(OUTPUT / "new76_submissions_summary.json", {"records": newly, "native_success_count": 76})
    resolution = {"human_confirmation_sha256": sha256_file(OUTPUT / "recovery16_human_confirmation.json"),
                  "old_markers_preserved": True, "cases": [{**r, "new_receipt": next(n for n in newly if n["sample_id"] == r["sample_id"])} for r in cases]}
    write_json_exclusive(OUTPUT / "recovery16_resolution.json", resolution)
    checkpoint = {"status": "ALL_280_LOGICAL_SAMPLES_HAVE_NATIVE_SUCCESS_RECEIPTS", "checked_at": checked,
                  "batch_sha256": original.BATCH_SHA, "records": records, "new_this_turn": 76,
                  "original_root_success_receipts": 264, "fresh_directory_success_receipts": 16,
                  "existing_DFT_labels_reused": 12, "logical_total_selected": 292,
                  "unknown_old_markers_retained": 16, "remaining_logical_samples_without_success_receipt": 0,
                  "old_marker_resolution_path": str(OUTPUT / "recovery16_resolution.json"),
                  "training_performed": False, "scientific_outputs_reviewed": False}
    write_json_exclusive(OUTPUT / "final_submission_checkpoint.json", checkpoint)
    registry_plan("new76_submissions_summary.json", "final_scheduler_snapshot.json", "_v2", [
        OUTPUT / "final_submission_checkpoint.json", OUTPUT / "recovery16_resolution.json",
        OUTPUT / "recovery16_human_confirmation.json", OUTPUT / "recovery16_proposal.json", AUTH])
    print({"new_submitted": 76, "logical_success": 280, "scheduler": scheduler["status_counts"], "resources": resource})


if __name__ == "__main__":
    run()
