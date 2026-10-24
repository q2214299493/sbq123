"""Submit only frozen NOT_RESERVED cases through the canonical executor."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path

from archive.fe110_reico_sampling93_20261022 import submit as original
from scripts.artifact_io import load_json_object, source_file_manifest, write_json, write_json_exclusive
from scripts.neb_agent.submission import submit, submission_status
from scripts.ts_strategy_engine.execution_gate import require_action
from .preflight import OUTPUT, ROOT

AUTH = ROOT/"docs/reviews/fe110_reico_remaining_20261024/user_authorization.md"


def checked_scope():
    scope = load_json_object(OUTPUT/"initial_scope.json")
    remote = load_json_object(OUTPUT/"remote_check_parsed.json")
    if (remote["user"]["stdout"].strip() != "nsgkn_chengdj3" or remote["account_resource_query"]["returncode"]
            or not all(remote["runtime"].values()) or any(r["directory_exists"] or r["lock_exists"] for r in remote["new_targets"])):
        raise ValueError("remote runtime/account/target preflight failed")
    table = remote["account_resource_query"]["stdout"].splitlines()
    columns, values = table[0].split(), table[1].split()
    if int(values[columns.index("MAX")]) != 128:
        raise ValueError("account quota differs from approved128 core branch")
    ready = {r["sample_id"]:r for r in original.checked_ready()}
    rows = scope["eligible"]
    if len(rows) != 69 or any(ready[r["sample_id"]] != r for r in rows):
        raise ValueError("eligible69scope changed")
    for row in rows:
        if remote["POTCARs"][row["potcar_source"]] != row["potcar_sha256"]:
            raise ValueError("live POTCAR differs")
        path = original.DEST/row["sample_id"]/"execution_decision.json"
        gate = load_json_object(path)
        require_action(path, original.ACTION, gate["state_sha256"])
    binding = {"source_files":source_file_manifest([Path(__file__), AUTH, OUTPUT/"initial_scope.json",
        OUTPUT/"remote_check.json", OUTPUT/"remote_check_parsed.json", original.DEST/"batch_request.json",
        original.DEST/"ready_for_submission.json"]), "sample_ids":[r["sample_id"] for r in rows]}
    path = OUTPUT/"execution_binding.json"
    if path.exists():
        if load_json_object(path) != binding:
            raise ValueError("submission continuation inputs/source changed")
    else:
        write_json_exclusive(path,binding)
    return rows


def submit_one(row):
    directory = original.DEST/row["sample_id"]
    state = submission_status(directory)
    if state["status"] == "SUBMITTED":
        record = state
    elif state["status"] == "NOT_RESERVED":
        record = submit(directory,directory/"execution_decision.json",original.HOST,
                        original.REMOTE+"/"+row["sample_id"],row["potcar_source"],row["potcar_sha256"],original.ACTION)
    else:
        raise ValueError("unknown attempt must not be retried")
    if (record["gate_decision_sha256"] != row["decision_sha256"]
            or record["remote_dir"] != original.REMOTE+"/"+row["sample_id"]):
        raise ValueError("success receipt differs from exact approved scope")
    return {"sample_id":row["sample_id"],**record}


def run(max_new=None):
    if max_new is not None and max_new <= 0:
        raise ValueError("max_new must be positive")
    rows = checked_scope()
    unsubmitted = [r for r in rows if submission_status(original.DEST/r["sample_id"])["status"] != "SUBMITTED"]
    if max_new is not None:
        unsubmitted = unsubmitted[:max_new]
    failures = []
    for start in range(0,len(unsubmitted),12):
        chunk = unsubmitted[start:start+12]
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(submit_one,row):row for row in chunk}
            for future in as_completed(futures):
                row=futures[future]
                try:
                    result=future.result()
                    print(f"SUBMITTED {row['sample_id']} job={result['job_id']}",flush=True)
                except Exception as error:
                    failures.append({"sample_id":row["sample_id"],"error":str(error)})
                    print(f"BLOCKED {row['sample_id']}: {error}",flush=True)
        current = [{"sample_id":r["sample_id"],**submission_status(original.DEST/r["sample_id"])} for r in rows]
        write_json(OUTPUT/"submission_progress.json",{"checked_at":datetime.now(timezone.utc).isoformat(),
            "successful":[r for r in current if r["status"] == "SUBMITTED"], "failures":failures,
            "unresolved":[r for r in current if r["status"] != "SUBMITTED"]})
        if failures:
            raise ValueError("submission stopped after failed chunk; inspect native receipts before recovery")
    result=load_json_object(OUTPUT/"submission_progress.json")
    if len(result["successful"]) == len(rows):
        path=OUTPUT/"submission69_summary.json"
        summary={"status":"ALL69_SUBMITTED","batch_sha256":original.BATCH_SHA,"records":result["successful"],
                 "unknown_original7_not_retried":True,"training_performed":False}
        if path.exists():
            if load_json_object(path) != summary:
                raise ValueError("existing completed69summary differs")
        else:
            write_json_exclusive(path,summary)
    print(json.dumps({"successful":len(result["successful"]),"remaining":len(result["unresolved"]),"failures":len(failures)}))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-new",type=int)
    args=parser.parse_args()
    run(args.max_new)
