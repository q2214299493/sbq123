"""Prepare reviewable fresh attempts for seven unknown outcomes; never submit."""
from __future__ import annotations

from datetime import datetime, timezone
import shutil

from archive.fe110_reico_sampling93_20261022 import submit as original
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.submission import preflight, submission_status
from .preflight import OUTPUT, ROOT


def run():
    path=OUTPUT/"recovery7_proposal.json"
    if path.exists():
        raise ValueError("prepared recovery proposal already exists; preserve its reviewed bytes")
    scope=load_json_object(OUTPUT/"initial_scope.json")
    remote=load_json_object(OUTPUT/"remote_check_parsed.json")
    evidence={r["sample_id"]:r for r in remote["targets"]}
    rows=[]
    for source in scope["unknown"]:
        sid=source["sample_id"]
        old=original.DEST/sid
        if submission_status(old)["status"] != "UNKNOWN_NEEDS_RECONCILIATION":
            raise ValueError("unknown source state changed; inspect before preparing recovery")
        target=OUTPUT/"recovery7_workdirs"/sid
        target.mkdir(parents=True,exist_ok=False)
        old_report=load_json_object(old/"submission_preflight.json")
        for name in [*old_report["files"],"input_profile.json","incar_validation.json","incar_validation_binding.json","label_request.json"]:
            shutil.copyfile(old/name,target/name)
        report=preflight(target,"diagnostic_static",write_report=False)
        if not report["passed"] or report["bundle_sha256"] != old_report["bundle_sha256"]:
            raise ValueError("fresh recovery candidate changed input bundle or failed preflight")
        write_json_exclusive(target/"submission_preflight.json",report)
        rows.append({"sample_id":sid,"original_attempt_sha256":sha256_file(old/"submission_attempt.json"),
            "original_record_sha256":sha256_file(old/"submission_record.json"),
            "original_remote_dir":source["attempt"]["remote_dir"],
            "proposed_workdir":str(target),"proposed_remote_dir":"~/sbq/Fe110/diagnostics/reico_labels_recovery7_20261024_v1/"+sid,
            "bundle_sha256":report["bundle_sha256"],"input_hashes":report["files"],"preflight_passed":True,
            "remote_inspection":evidence[sid],"matching_job_uniquely_recovered":False,
            "duplicate_absence_confirmed_by_human":False,"submission_authorized":False,
            "potcar_source":source["potcar_source"],"potcar_sha256":source["potcar_sha256"]})
    result={"status":"OPERATOR_REVIEW_REQUIRED","prepared_at":datetime.now(timezone.utc).isoformat(),"cases":rows,
        "inputs_unchanged":True,"original_markers_or_remote_locks_changed":False,"new_jobs_submitted":0,
        "review_requirement":"SUBMISSION_RECOVERY.md: Any subsequent submission requires explicit human confirmation that no matching job exists",
        "source_files":source_file_manifest([ROOT/"SUBMISSION_RECOVERY.md",OUTPUT/"initial_scope.json",
            OUTPUT/"remote_check.json",OUTPUT/"remote_check_parsed.json",__import__('pathlib').Path(__file__)])}
    write_json_exclusive(path,result)
    print({"status":result["status"],"prepared":len(rows),"new_jobs":0})


if __name__ == "__main__":
    run()
