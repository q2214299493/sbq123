"""Collect frozen terminal static jobs in bounded batches; preserve every QC outcome."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from archive.fe110_reico_followup_20261024.collect import check_snapshot, save_once
from archive.fe110_reico_followup_20261024.review import review_case
from archive.fe110_reico_label_qc_20261023.collect import identity_path
from archive.fe110_reico_label_qc_20261023.review import scheduler_evidence
from scripts.adsorption.collect_completed_batch import FILES, collect_one
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, sha256_text, source_file_manifest
from scripts.neb_agent.submission import submission_status
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/completed_label_qc_20261024_v1.json"
HOST = "sunboquan-codex"


def pending_rows(selected, previous, checkpoint):
    """Use the exact successful directory, including explicitly reviewed fresh attempts."""
    selected_map = {r["sample_id"]: r for r in selected}
    previous_ids = {r["sample_id"] for r in previous}
    rows = []
    seen_ids, seen_jobs = set(), set()
    for receipt in checkpoint["records"]:
        sid = receipt["sample_id"]
        if sid in seen_ids or receipt["job_id"] in seen_jobs:
            raise ValueError("duplicate logical sample or scheduler job")
        seen_ids.add(sid)
        seen_jobs.add(receipt["job_id"])
        if sid not in selected_map:
            raise ValueError("receipt outside frozen selection")
        directory = Path(receipt["workdir"])
        if (receipt["server_alias"] != HOST or receipt["scheduler"] != "LSF"
                or receipt["status"] != "SUBMITTED"
                or submission_status(directory) != {k: v for k, v in receipt.items() if k not in {"sample_id", "workdir"}}):
            raise ValueError("exact native success receipt changed")
        if sid not in previous_ids:
            rows.append({"name": sid, "job_id": receipt["job_id"], "remote_dir": receipt["remote_dir"],
                         "workdir": str(directory), "potcar_sha256": receipt["potcar_sha256"]})
    return rows


def scope():
    config = load_json_object(CONFIG)
    paths = {key: ROOT / item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen input changed: " + key)
    selected = load_json_object(paths["selection"])["selected"]
    previous = load_json_object(paths["previous_labels"])["samples"]
    checkpoint = load_json_object(paths["checkpoint"])
    batch = load_json_object(paths["batch"])
    if checkpoint["batch_sha256"] != sha256_file(paths["batch"]):
        raise ValueError("checkpoint differs from original input batch")
    if {r["sample_id"] for r in batch["samples"]} != {r["sample_id"] for r in checkpoint["records"]}:
        raise ValueError("receipt scope differs from original input batch")
    return config, paths, selected, previous, pending_rows(selected, previous, checkpoint)


def snapshot():
    config, paths, _, _, rows = scope()
    output = ROOT / config["output"]
    output.mkdir(parents=True, exist_ok=True)
    sources = source_file_manifest([CONFIG, *paths.values(), Path(__file__),
        ROOT / "scripts/adsorption/collect_completed_batch.py",
        ROOT / "archive/fe110_reico_followup_20261024/review.py",
        ROOT / "scripts/adsorption/reico_probe_review.py",
        ROOT / "scripts/vasp_result_gate.py", ROOT / "scripts/aqcat25_calibration.py",
        ROOT / "scripts/neb_agent/utils_vasp.py"])
    save_once(output / "collection_binding.json", {"source_files": sources, "requested": rows})
    target = output / "scheduler_snapshot.json"
    if target.exists():
        saved = check_snapshot(load_json_object(target))
        if saved["requested"] != rows:
            raise ValueError("snapshot requested job scope changed")
        return config, paths, saved
    if not rows:
        raise ValueError("no unreviewed receipt-backed jobs to query")
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
    save_once(target, saved)
    print({"queried": len(jobs), "checked_at": saved["checked_at"], "queue": saved["status_counts"]}, flush=True)
    return config, paths, check_snapshot(saved)


def process_one(row, source, original_inputs, output, identity, current, binding):
    sid = row["name"]
    case_path = output / "case_qc" / (sid + ".json")
    directory = output / "collection" / sid
    expected = {k: v for k, v in row.items() if k != "status"}
    evidence = scheduler_evidence(current, row)
    validate_stored_lsf_evidence(evidence, required_status="DONE")
    receipt = collect_one(expected, HOST, identity, output / "collection")
    if receipt["submission"] != expected or receipt["job_id"] != row["job_id"]:
        raise ValueError("collection belongs to different exact submission")
    for name in ("POSCAR", "INCAR", "KPOINTS"):
        if sha256_file(directory / name) != original_inputs[name]:
            raise ValueError("collected input differs from original immutable batch")
    if case_path.exists():
        saved = load_json_object(case_path)
        if (saved["review_binding_sha256"] != binding or saved["source_job_id"] != row["job_id"]
                or any(sha256_file(directory / name) != saved["input_output_hashes"][name] for name in FILES)):
            raise ValueError("saved QC source or parser binding changed")
        return saved
    reviewed = review_case(source, receipt, directory, binding)
    reviewed["category"] = "COMPLETED_STATIC_BATCH_20261024"
    save_once(case_path, reviewed)
    return reviewed


def run(smoke=False):
    config, paths, current = snapshot()
    output = ROOT / config["output"]
    selected = {r["sample_id"]: r for r in load_json_object(paths["selection"])["selected"]}
    inputs = {r["sample_id"]: r["input_hashes"] for r in load_json_object(paths["batch"])["samples"]}
    done = [r for r in current["jobs"] if r["status"] == "DONE"]
    if smoke:
        done = done[:1]
    binding = sha256_json(load_json_object(output / "collection_binding.json"))
    identity = identity_path()
    all_rows, failures = [], []
    size = config["batch_size"]
    if size <= 0:
        raise ValueError("batch size must be positive")
    for start in range(0, len(done), size):
        chunk = done[start:start + size]
        rows, errors = [], []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {}
            for row in chunk:
                failure_path = output / "case_failures" / (row["name"] + ".json")
                if failure_path.exists():
                    errors.append(load_json_object(failure_path))
                    continue
                futures[pool.submit(process_one, row, selected[row["name"]], inputs[row["name"]],
                                    output, identity, current, binding)] = row
            for future in as_completed(futures):
                row = futures[future]
                try:
                    reviewed = future.result()
                    rows.append(reviewed)
                    print(f"QC {start + len(rows)}/{len(done)} {row['name']} {reviewed['data_qc_status']}", flush=True)
                except Exception as error:
                    failure = {"sample_id": row["name"], "job_id": row["job_id"],
                               "error": str(error), "stage": "COLLECTION_OR_QC", "automatic_retry": False}
                    save_once(output / "case_failures" / (row["name"] + ".json"), failure)
                    errors.append(failure)
                    print(f"BLOCKED {row['name']}: {error}", flush=True)
        rows.sort(key=lambda r: r["sample_id"])
        all_rows.extend(rows)
        failures.extend(errors)
        if not smoke:
            save_once(output / f"batch_{start // size + 1:03d}.json", {"requested": [r["name"] for r in chunk],
                "reviewed": [r["sample_id"] for r in rows], "qc_counts": dict(Counter(r["data_qc_status"] for r in rows)),
                "failures": errors, "binding_sha256": binding})
    all_rows.sort(key=lambda r: r["sample_id"])
    label_path = output / ("smoke_labels_local_only.json" if smoke else "new_label_qc_local_only.json")
    save_once(label_path, {"samples": all_rows, "source_files": source_file_manifest([
        CONFIG, output / "collection_binding.json", output / "scheduler_snapshot.json",
        *[output / "case_qc" / (r["sample_id"] + ".json") for r in all_rows]])})
    summary = {"status": "BATCH_QC_COMPLETE" if not failures else "PARTIAL_FAILURE", "checked_at": current["checked_at"],
        "requested_DONE": len(done), "reviewed": len(all_rows), "qc_counts": dict(Counter(r["data_qc_status"] for r in all_rows)),
        "partition_counts": dict(Counter(r["partition"] for r in all_rows)),
        "train_pass": sum(r["partition"] == "train" and r["data_qc_status"] == "PASS" for r in all_rows),
        "failures": failures, "scheduler_counts": current["status_counts"], "training_performed": False,
        "magnetic_global_ground_state_verified": False, "frozen_training_package_changed": False,
        "source_files": source_file_manifest([label_path, CONFIG, output / "scheduler_snapshot.json"])}
    save_once(output / ("smoke_summary.json" if smoke else "qc_summary.json"), summary)
    print({k: v for k, v in summary.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "smoke", "process"))
    args = parser.parse_args()
    snapshot() if args.action == "snapshot" else run(args.action == "smoke")
