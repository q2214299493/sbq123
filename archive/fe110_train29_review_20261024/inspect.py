"""Freeze the exact29 remaining train-only submissions and query one checkpoint."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from archive.fe110_reico_followup_20261024.collect import check_snapshot, save_once
from archive.fe110_train45_review_20261024.inspect import scope as previous_scope
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, source_file_manifest
from scripts.scheduler_evidence import _parse_lsf_bjobs

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/train29_review_20261024_v1.json"
HOST = "sunboquan-codex"


def remaining_rows(rows, previous, selected):
    reviewed = {r["sample_id"] for r in previous}
    if len(reviewed) != len(previous):
        raise ValueError("duplicate previously reviewed sample")
    remaining = [r for r in rows if r["name"] not in reviewed]
    ids = {r["name"] for r in remaining}
    if (len(remaining) != 29 or len(ids) != 29
            or any(selected[sid]["partition"] != "train" for sid in ids)):
        raise ValueError("exact29 train-only remaining scope changed")
    return remaining


def scope():
    config = load_json_object(CONFIG)
    paths = {key: ROOT / item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen input changed: " + key)
    _, _, selected, older, rows, _ = previous_scope()
    previous = load_json_object(paths["previous_labels"])["samples"]
    addition = load_json_object(paths["previous_new_labels"])["samples"]
    if (len(previous) != 256 or len(addition) != 16
            or previous != older + addition):
        raise ValueError("previous256-label checkpoint differs from reviewed240+16")
    remaining = remaining_rows(rows, previous, selected)
    groups = load_json_object(paths["previous_contribution"])["remaining_of_original40_groups"]
    ids = {r["name"] for r in remaining}
    if len(groups) != 27 or {sid for g in groups for sid in g["unreviewed_selected_input_ids"]} != ids:
        raise ValueError("remaining29 no longer match27 original gap groups")
    return config, paths, selected, previous, remaining, groups


def snapshot():
    config, paths, _, _, rows, _ = scope()
    output = ROOT / config["output"]
    output.mkdir(parents=True, exist_ok=True)
    sources = source_file_manifest([CONFIG, *paths.values(), Path(__file__),
        ROOT / "archive/fe110_train45_review_20261024/inspect.py",
        ROOT / "archive/fe110_completed_label_qc_20261024/run.py"])
    save_once(output / "scope_binding.json", {"source_files": sources, "requested": rows})
    target = output / "scheduler_snapshot.json"
    if target.exists():
        saved = check_snapshot(load_json_object(target))
        if saved["requested"] != rows:
            raise ValueError("saved29-job scope changed")
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
    snapshot()
