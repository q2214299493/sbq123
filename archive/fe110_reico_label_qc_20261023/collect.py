"""Collect only the exact DONE checkpoint; no new scheduler actions or remote writes."""
from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from archive.fe110_reico_sampling93_20261022.submit import DEST, HOST, checked_batch
from scripts.adsorption.collect_completed_batch import collect_one
from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.submission import submission_status

OUTPUT = Path("calculations/fe110_reico_pilot300_20261022/force_label_qc_20261023_v1")


def requested_rows() -> list[dict]:
    checked_batch()
    snapshot = load_json_object(OUTPUT / "scheduler_snapshot.json")
    checkpoint_path = DEST / "initial_submission_checkpoint.json"
    if sha256_file(checkpoint_path) != snapshot["checkpoint_sha256"]:
        raise ValueError("original checkpoint changed")
    checkpoint = load_json_object(checkpoint_path)
    receipts = {r["sample_id"]: r for r in checkpoint["records"]}
    rows = []
    for job in snapshot["jobs"]:
        receipt = receipts[job["sample_id"]]
        if submission_status(DEST/job["sample_id"]) != {k:v for k,v in receipt.items() if k != "sample_id"}:
            raise ValueError("original submission receipt changed")
        if job["job_id"] != receipt["job_id"] or job["remote_dir"] != receipt["remote_dir"]:
            raise ValueError("snapshot job/target differs from original receipt")
        if job["status"] == "DONE":
            rows.append({"name": job["sample_id"], "job_id": job["job_id"], "remote_dir": job["remote_dir"],
                         "workdir": str((DEST/job["sample_id"]).resolve()), "potcar_sha256": receipt["potcar_sha256"]})
    return rows


def identity_path() -> Path:
    result = subprocess.run(["ssh", "-G", HOST], capture_output=True, text=True, check=True)
    # Read configuration/file existence only, never key contents.
    candidates = [Path(line.split(" ",1)[1]).expanduser() for line in result.stdout.splitlines() if line.startswith("identityfile ")]
    return next(p for p in candidates if p.is_file())


def main():
    rows, identity = requested_rows(), identity_path()
    results, failures = [], []
    write_json(OUTPUT/"collection_status.json", {"status":"RUNNING", "requested":len(rows)})
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect_one, row, HOST, identity, OUTPUT/"collection"):row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                receipt = future.result()
                if receipt["submission"] != row:
                    raise ValueError("resumed collection belongs to different input scope")
                results.append({"sample_id":row["name"], "job_id":row["job_id"],
                                "receipt_sha256":sha256_file(OUTPUT/"collection"/row["name"]/"collection.json")})
                print(f"COLLECTED {len(results)}/{len(rows)} {row['name']}", flush=True)
            except Exception as error:
                failures.append({"sample_id":row["name"],"job_id":row["job_id"],"error":str(error)})
                print(f"BLOCKED {row['name']}: {error}", flush=True)
            write_json(OUTPUT/"collection_status.json", {"status":"RUNNING", "requested":len(rows),
                                                        "collected":len(results), "failed":len(failures)})
    result = {"status":"COMPLETE" if not failures else "PARTIAL_FAILURE", "requested":len(rows),
              "collected":results,"failures":failures,"new_submission":False,"remote_writes":False}
    write_json(OUTPUT/"collection_summary.json",result)
    write_json(OUTPUT/"collection_status.json", {"status":result["status"],"collected":len(results),"failed":len(failures)})
    print(json.dumps({"status":result["status"],"collected":len(results),"failed":len(failures)}))


if __name__ == "__main__":
    main()
