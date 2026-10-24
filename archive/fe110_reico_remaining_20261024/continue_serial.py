"""Continue untouched cases serially; preserve every uncertain attempt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, source_file_manifest, write_json, write_json_exclusive
from scripts.neb_agent.submission import submission_status
from .preflight import OUTPUT
from .submit import checked_scope, original, submit_one


def run(max_new=None):
    rows=checked_scope()
    scope_path=OUTPUT/"serial_scope.json"
    if scope_path.exists():
        scoped=load_json_object(scope_path)
    else:
        safe=[r for r in rows if submission_status(original.DEST/r["sample_id"])["status"] == "NOT_RESERVED"]
        scoped={"cases":safe,"unknown_preserved":[r["sample_id"] for r in rows
                if submission_status(original.DEST/r["sample_id"])["status"] == "UNKNOWN_NEEDS_RECONCILIATION"],
                "source_files":source_file_manifest([Path(__file__),OUTPUT/"execution_binding.json",OUTPUT/"submission_progress.json"])}
        write_json_exclusive(scope_path,scoped)
    pending=[r for r in scoped["cases"] if submission_status(original.DEST/r["sample_id"])["status"] != "SUBMITTED"]
    if max_new is not None:
        if max_new <= 0:
            raise ValueError("max_new must be positive")
        pending=pending[:max_new]
    for row in pending:
        if submission_status(original.DEST/row["sample_id"])["status"] != "NOT_RESERVED":
            raise ValueError("uncertain serial attempt requires recovery; no retry")
        try:
            receipt=submit_one(row)
        except Exception as error:
            write_json_exclusive(OUTPUT/(row["sample_id"]+"_serial_failure.json"),{"error":str(error),"sample_id":row["sample_id"]})
            raise
        print(f"SUBMITTED_SERIAL {row['sample_id']} job={receipt['job_id']}",flush=True)
        current=[{"sample_id":r["sample_id"],**submission_status(original.DEST/r["sample_id"])} for r in rows]
        write_json(OUTPUT/"serial_progress.json",{"checked_at":datetime.now(timezone.utc).isoformat(),
             "successful":[r for r in current if r["status"] == "SUBMITTED"],
             "untouched":[r for r in current if r["status"] == "NOT_RESERVED"],
             "unknown":[r for r in current if r["status"] == "UNKNOWN_NEEDS_RECONCILIATION"]})


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-new",type=int)
    args=parser.parse_args()
    run(args.max_new)
