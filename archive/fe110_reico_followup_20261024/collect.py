"""Collect exact outstanding receipt-backed labels; no remote writes or job actions."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from archive.fe110_reico_label_qc_20261023.collect import identity_path
from scripts.adsorption.collect_completed_batch import collect_one
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, source_file_manifest, write_json
from scripts.neb_agent.submission import submission_status
from scripts.scheduler_evidence import _parse_lsf_bjobs

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT/"configs/fe110_reico_pilot/followup_20261024_v1.json"
HOST = "sunboquan-codex"


def save_once(path, data):
    if path.exists():
        if load_json_object(path) != data:
            raise ValueError(f"preserve changed checkpoint: {path}")
    else:
        write_json(path, data)


def check_snapshot(saved):
    if saved["stdout_sha256"] != sha256_text(saved["stdout"]):
        raise ValueError("scheduler stdout hash changed")
    if saved["returncode"] or any(r["status"] == "UNKNOWN_QUERY_RESULT" for r in saved["jobs"]):
        raise ValueError("scheduler query incomplete; preserve snapshot and use a fresh checkpoint after recovery")
    for row in saved["jobs"]:
        if _parse_lsf_bjobs(saved["stdout"], row["job_id"]) != row["status"]:
            raise ValueError("scheduler status differs from raw output")
    return saved


def scope(config_path=CONFIG):
    config = load_json_object(config_path)
    paths = {k: ROOT/v["path"] for k,v in config["inputs"].items()}
    for key,path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError(f"frozen input changed: {key}")
    manifest = load_json_object(paths["manifest"])
    selected = load_json_object(paths["selection"])["selected"]
    admitted = {r["sample_id"] for rows in manifest["splits"].values() for r in rows}
    needed = [r for r in selected if r["sample_id"] not in admitted]
    checkpoint = load_json_object(paths["checkpoint"])
    receipts = {r["sample_id"]: r for r in checkpoint["records"]}
    if len(receipts) != len(checkpoint["records"]):
        raise ValueError("duplicate success receipt")
    submitted = []
    for row in needed:
        if row["sample_id"] not in receipts:
            continue
        receipt = receipts[row["sample_id"]]
        directory = paths["checkpoint"].parent/row["sample_id"]
        if (receipt["server_alias"] != HOST or receipt["scheduler"] != "LSF"
                or submission_status(directory) != {k:v for k,v in receipt.items() if k != "sample_id"}):
            raise ValueError("exact submitted job receipt changed")
        submitted.append({"name": row["sample_id"], "job_id": receipt["job_id"],
                          "remote_dir": receipt["remote_dir"], "workdir": str(directory),
                          "potcar_sha256": receipt["potcar_sha256"]})
    return config, paths, needed, submitted


def snapshot(output, paths, rows):
    path = output/"scheduler_snapshot.json"
    sources = source_file_manifest([CONFIG, paths["checkpoint"], paths["manifest"], paths["selection"], Path(__file__)])
    save_once(output/"collection_binding.json", {"source_files": sources, "requested": rows})
    if path.exists():
        saved = load_json_object(path)
        if saved["requested"] != rows:
            raise ValueError("scheduler checkpoint scope differs")
        return check_snapshot(saved)
    argv = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST,
            "bjobs", "-a", *[r["job_id"] for r in rows]]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    jobs = []
    for row in rows:
        try:
            status = _parse_lsf_bjobs(result.stdout, row["job_id"])
        except ValueError:
            status = "UNKNOWN_QUERY_RESULT"
        jobs.append({**row, "status": status})
    saved = {"checked_at": datetime.now(timezone.utc).isoformat(), "command": argv,
             "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
             "stdout_sha256": sha256_text(result.stdout), "requested": rows, "jobs": jobs,
             "status_counts": dict(Counter(r["status"] for r in jobs)), "source_files": sources,
             "new_submission": False, "remote_writes": False}
    save_once(path, saved)
    print(json.dumps({"queried": len(rows), "checked_at": saved["checked_at"],
                      "scheduler_counts": saved["status_counts"], "returncode": result.returncode}), flush=True)
    return check_snapshot(saved)


def run(maximum=None):
    config, paths, needed, rows = scope()
    output = ROOT/config["output"]
    output.mkdir(parents=True, exist_ok=True)
    current = snapshot(output, paths, rows)
    done = [{k:v for k,v in r.items() if k != "status"} for r in current["jobs"] if r["status"] == "DONE"]
    if maximum is not None:
        done = done[:maximum]
    identity = identity_path()
    collected, failures = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect_one, row, HOST, identity, output/"collection"): row for row in done}
        for future in as_completed(futures):
            row = futures[future]
            try:
                receipt = future.result()
                if receipt["submission"] != row:
                    raise ValueError("collection belongs to different exact input scope")
                collected.append({"sample_id": row["name"], "job_id": row["job_id"],
                                  "receipt_sha256": sha256_file(output/"collection"/row["name"]/"collection.json")})
                print(f"COLLECTED {len(collected)}/{len(done)} {row['name']}", flush=True)
            except Exception as error:
                failures.append({"sample_id": row["name"], "job_id": row["job_id"], "error": str(error)})
                print(f"BLOCKED {row['name']}: {error}", flush=True)
            write_json(output/"collection_status.json", {"requested": len(done), "collected": len(collected), "failures": failures})
    result = {"status": "COMPLETE" if not failures else "PARTIAL_FAILURE", "requested": len(done),
              "collected": sorted(collected, key=lambda r:r["sample_id"]), "failures": failures,
              "not_in_current_package": dict(Counter(r["partition"] for r in needed)),
              "without_success_receipts": [{k:r[k] for k in ("sample_id", "partition", "composition")}
                                           for r in needed if r["sample_id"] not in {v["name"] for v in rows}],
              "new_submission_or_remote_write": False}
    save_once(output/("collection_smoke.json" if maximum is not None else "collection_summary.json"), result)
    print(json.dumps({"status":result["status"], "collected":len(collected), "failures":len(failures)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maximum", type=int)
    args = parser.parse_args()
    run(args.maximum)
