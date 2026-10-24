"""Prioritize distinct gap groups, then retain all completed labels for native QC."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from archive.fe110_completed_label_qc_20261024.run import process_one
from archive.fe110_reico_label_qc_20261023.collect import identity_path
from scripts.artifact_io import load_json_object, sha256_json, source_file_manifest, source_file_manifest_valid
from .inspect import CONFIG, ROOT, save_once, scope, snapshot


def prioritized_done(jobs, groups):
    done = {r["name"]: r for r in jobs if r["status"] == "DONE"}
    if len(done) != sum(r["status"] == "DONE" for r in jobs):
        raise ValueError("duplicate completed sample")
    first, seen = [], set()
    for group in groups:
        available = sorted(set(group["unreviewed_selected_input_ids"]) & set(done) - seen)
        if available:
            first.append(done[available[0]])
            seen.add(available[0])
    return first + [r for sid, r in sorted(done.items()) if sid not in seen]


def run(smoke=False):
    config, paths, current = snapshot()
    _, _, selected, _, _, groups = scope()
    output = ROOT / config["output"]
    done = prioritized_done(current["jobs"], groups)
    source_files = source_file_manifest([CONFIG, Path(__file__), output / "scope_binding.json",
        output / "scheduler_snapshot.json", output / "collection_binding.json", output / "smoke_labels_local_only.json",
        ROOT / "archive/fe110_train45_review_20261024/process.py", ROOT / "archive/fe110_completed_label_qc_20261024/run.py",
        ROOT / "archive/fe110_reico_followup_20261024/review.py", ROOT / "scripts/adsorption/collect_completed_batch.py",
        ROOT / "scripts/adsorption/reico_probe_review.py", ROOT / "scripts/aqcat25_calibration.py",
        ROOT / "scripts/neb_agent/utils_vasp.py", ROOT / "scripts/vasp_result_gate.py"])
    binding_doc = {"source_files": source_files, "requested": done, "priority": "One DONE representative per gap first;all other DONE retained"}
    save_once(output / "main_collection_binding.json", binding_doc)
    binding = sha256_json(binding_doc)
    smoke_binding = load_json_object(output / "collection_binding.json")
    if not source_file_manifest_valid(smoke_binding):
        raise ValueError("preserved smoke source binding changed")
    smoke_labels = load_json_object(output / "smoke_labels_local_only.json")
    if not source_file_manifest_valid(smoke_labels):
        raise ValueError("preserved smoke QC changed")
    smoke_ids = {r["sample_id"] for r in smoke_labels["samples"]}
    identity = identity_path()
    inputs = {r["sample_id"]: r["input_hashes"] for r in load_json_object(paths["batch"])["samples"]}
    if smoke:
        done = done[:1]
    reviewed, failures = [], []
    for start in range(0, len(done), config["batch_size"]):
        chunk = done[start:start + config["batch_size"]]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(process_one, row, selected[row["name"]], inputs[row["name"]], output,
                                   identity, current, sha256_json(smoke_binding) if row["name"] in smoke_ids else binding): row for row in chunk}
            for future in as_completed(futures):
                row = futures[future]
                try:
                    label = future.result()
                    reviewed.append(label)
                    print(f"QC {len(reviewed)}/{len(done)} {row['name']} {label['data_qc_status']}", flush=True)
                except Exception as error:
                    failure = {"sample_id": row["name"], "job_id": row["job_id"], "error": str(error)}
                    save_once(output / "case_failures" / (row["name"] + ".json"), failure)
                    failures.append(failure)
                    print(f"BLOCKED {row['name']}: {error}", flush=True)
    reviewed.sort(key=lambda r: r["sample_id"])
    failures.sort(key=lambda r: r["sample_id"])
    label_path = output / ("smoke_labels_local_only.json" if smoke else "new_label_qc_local_only.json")
    save_once(label_path, {"samples": reviewed, "source_files": source_file_manifest([CONFIG,
        output / "main_collection_binding.json", output / "scheduler_snapshot.json",
        *[output / "case_qc" / (r["sample_id"] + ".json") for r in reviewed]])})
    summary = {"status": "QC_COMPLETE" if not failures else "PARTIAL_FAILURE", "checked_at": current["checked_at"],
        "requested_DONE": len(done), "reviewed": len(reviewed), "qc_counts": dict(Counter(r["data_qc_status"] for r in reviewed)),
        "partition_counts": dict(Counter(r["partition"] for r in reviewed)), "failures": failures,
        "scheduler_counts": current["status_counts"], "new_DFT_GPU_training_or_submission": False,
        "source_files": source_file_manifest([label_path, CONFIG, output / "main_collection_binding.json"])}
    save_once(output / ("smoke_summary.json" if smoke else "qc_summary.json"), summary)
    print({k: v for k, v in summary.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    run(args.smoke)
