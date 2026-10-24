"""Resume receipt-backed train-label collection using a frozen checkpoint config."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from archive.fe110_reico_followup_20261024.collect import check_snapshot, save_once
from archive.fe110_train45_review_20261024.inspect import scope as original_scope
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, source_file_manifest
from scripts.scheduler_evidence import _parse_lsf_bjobs

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/fe110_reico_pilot/train28_review_20261024_v1.json"
HOST = "sunboquan-codex"


def scope(config_path):
    config = load_json_object(config_path)
    paths = {key: ROOT / item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen input changed: " + key)
    _, _, selected, original, submitted, groups = original_scope()
    previous = load_json_object(paths["previous_labels"])["samples"]
    reviewed = {r["sample_id"] for r in previous}
    if (len(reviewed) != len(previous) or len(previous) != config["previous_reviewed"]
            or previous[:len(original)] != original):
        raise ValueError("previous cumulative review differs from frozen history")
    rows = [r for r in submitted if r["name"] not in reviewed]
    if (len(rows) != config["expected_remaining"]
            or any(selected[r["name"]]["partition"] != "train" for r in rows)):
        raise ValueError("remaining original training-only scope changed")
    return config, paths, selected, previous, rows, groups


def snapshot(config_path=DEFAULT_CONFIG):
    config, paths, _, _, rows, _ = scope(config_path)
    output = ROOT / config["output"]
    sources = source_file_manifest([config_path, *paths.values(), Path(__file__),
        ROOT / "archive/fe110_train45_review_20261024/inspect.py",
        ROOT / "archive/fe110_completed_label_qc_20261024/run.py"])
    save_once(output / "scope_binding.json", {"source_files": sources, "requested": rows})
    target = output / "scheduler_snapshot.json"
    if target.exists():
        saved = check_snapshot(load_json_object(target))
        if saved["requested"] != rows:
            raise ValueError("saved checkpoint scope changed")
        return config, paths, saved
    argv = ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST,
            "bjobs", "-a", *[r["job_id"] for r in rows]]
    response = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    jobs = []
    for row in rows:
        try:
            status = _parse_lsf_bjobs(response.stdout, row["job_id"])
        except ValueError:
            status = "UNKNOWN_QUERY_RESULT"
        jobs.append({**row, "status": status})
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "command": argv,
        "returncode": response.returncode, "stdout": response.stdout, "stderr": response.stderr,
        "stdout_sha256": sha256_text(response.stdout), "requested": rows, "jobs": jobs,
        "status_counts": dict(Counter(r["status"] for r in jobs)), "new_submission": False, "remote_writes": False}
    save_once(target, result)
    print({"scope": len(jobs), "checked_at": result["checked_at"], "queue": result["status_counts"]}, flush=True)
    return config, paths, check_snapshot(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    snapshot(args.config)
