"""Prepare sixteen unknown cases for explicit operator review, without submission."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

from archive.fe110_reico_sampling93_20261022 import submit as original
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.submission import preflight, submission_status
from .preflight import OUTPUT, ROOT


def run():
    old_proposal=load_json_object(OUTPUT/"recovery7_proposal.json")
    prepared={r["sample_id"]:r for r in old_proposal["cases"]}
    inspections={r["sample_id"]:r for r in load_json_object(OUTPUT/"reconciliation16_parsed.json")["targets"]}
    rows=[]
    for ready in original.checked_ready():
        sid=ready["sample_id"]
        source=original.DEST/sid
        if submission_status(source)["status"] != "UNKNOWN_NEEDS_RECONCILIATION":
            continue
        target=Path(prepared[sid]["proposed_workdir"]) if sid in prepared else OUTPUT/"recovery16_workdirs"/sid
        old=load_json_object(source/"submission_preflight.json")
        if sid not in prepared:
            target.mkdir(parents=True,exist_ok=False)
            for name in [*old["files"],"input_profile.json","incar_validation.json","incar_validation_binding.json","label_request.json"]:
                shutil.copyfile(source/name,target/name)
            current=preflight(target,"diagnostic_static",write_report=False)
            write_json_exclusive(target/"submission_preflight.json",current)
        current=load_json_object(target/"submission_preflight.json")
        if not current["passed"] or current["bundle_sha256"] != old["bundle_sha256"]:
            raise ValueError("review proposal changed frozen scientific bundle")
        rows.append({"sample_id":sid,"original_workdir":str(source),
            "original_attempt_sha256":sha256_file(source/"submission_attempt.json"),
            "original_record_sha256":sha256_file(source/"submission_record.json"),
            "proposed_workdir":str(target),"proposed_remote_dir":"~/sbq/Fe110/diagnostics/reico_labels_recovery16_20261024_v1/"+sid,
            "bundle_sha256":current["bundle_sha256"],"input_hashes":current["files"],"preflight_passed":True,
            "remote_inspection":inspections[sid],"human_duplicate_absence_confirmation":False,
            "potcar_source":ready["potcar_source"],"potcar_sha256":ready["potcar_sha256"]})
    if len(rows) != 16:
        raise ValueError("unknown count changed; inspect before operator review")
    result={"status":"WAITING_EXPLICIT_HUMAN_DUPLICATE_REVIEW","prepared_at":datetime.now(timezone.utc).isoformat(),
        "cases":rows,"cores_per_job":32,"account_core_limit":128,"new_jobs_submitted":0,
        "original_attempts_records_and_remote_locks_preserved":True,
        "reason":"7prior unknown outcomes plus9SSH-interrupted new attempts;no matching unreceipted account job uniquely found;queue absence is not proof",
        "required_confirmation":"Confirm no matching job exists for these16cases before a new canonical submission attempt",
        "source_files":source_file_manifest([Path(__file__),ROOT/"SUBMISSION_RECOVERY.md",OUTPUT/"recovery7_proposal.json",
            OUTPUT/"reconciliation16.json",OUTPUT/"reconciliation16_parsed.json"])}
    write_json_exclusive(OUTPUT/"recovery16_proposal.json",result)
    print({"status":result["status"],"prepared":len(rows),"new_jobs":0})


if __name__ == "__main__":
    run()
