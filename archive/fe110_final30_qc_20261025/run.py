"""Recover the final30 receipt-backed labels using existing native QC owners."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil

from archive.fe110_completed_label_qc_20261024.run import pending_rows, process_one
from archive.fe110_reico_followup_20261024.collect import check_snapshot, save_once
from archive.fe110_reico_label_qc_20261023.collect import identity_path
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, source_file_manifest, source_file_manifest_valid

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/fe110_reico_pilot/final30_qc_20261025_v1.json"


def validate_scope(rows, selected, previous, config):
    ids = {r["name"] for r in rows}
    previous_ids = {r["sample_id"] for r in previous}
    partitions = Counter(selected[sid]["partition"] for sid in ids)
    if (len(ids) != len(rows) or len(rows) != config["expected_remaining"]
            or len(previous_ids) != len(previous) or len(previous) != config["previous_reviewed"]
            or ids & previous_ids or dict(partitions) != config["expected_partitions"]):
        raise ValueError("exact final scope, partition counts or previous review changed")


def scope(config_path=DEFAULT_CONFIG):
    config = load_json_object(config_path)
    paths = {key: ROOT / item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen input changed: " + key)
    selected = load_json_object(paths["selection"])["selected"]
    by_id = {r["sample_id"]: r for r in selected}
    previous_doc = load_json_object(paths["previous_labels"])
    if not source_file_manifest_valid(previous_doc):
        raise ValueError("previous cumulative label binding changed")
    previous = previous_doc["samples"]
    checkpoint = load_json_object(paths["checkpoint"])
    if checkpoint["batch_sha256"] != sha256_file(paths["batch"]):
        raise ValueError("receipt checkpoint differs from original batch")
    rows = pending_rows(selected, previous, checkpoint)
    validate_scope(rows, by_id, previous, config)
    groups = [g for g in load_json_object(paths["gaps"])["groups"] if g["unreviewed_selected_input_ids"]]
    return config, paths, by_id, previous, rows, groups


def snapshot(config_path=DEFAULT_CONFIG):
    config, paths, _, _, rows, _ = scope(config_path)
    current = check_snapshot(load_json_object(paths["snapshot"]))
    if current["requested"] != rows or any(r["status"] != "DONE" for r in current["jobs"]):
        raise ValueError("frozen30 DONE snapshot differs from native receipt scope")
    output = ROOT / config["output"]
    output.mkdir(parents=True, exist_ok=True)
    target = output / "scheduler_snapshot.json"
    if target.exists():
        if sha256_file(target) != sha256_file(paths["snapshot"]):
            raise ValueError("preserve changed scheduler evidence")
    else:
        shutil.copyfile(paths["snapshot"], target)
    save_once(output / "scope_binding.json", {"source_files": source_file_manifest([
        config_path, *paths.values(), Path(__file__),
        ROOT / "archive/fe110_completed_label_qc_20261024/run.py"]), "requested": rows})
    return config, paths, current


def collect(smoke=False, config_path=DEFAULT_CONFIG):
    config, paths, current = snapshot(config_path)
    _, _, selected, _, rows, _ = scope(config_path)
    output = ROOT / config["output"]
    statuses = {r["job_id"]: r["status"] for r in current["jobs"]}
    done = [{**row, "status": statuses[row["job_id"]]} for row in rows]
    done.sort(key=lambda r: (selected[r["name"]]["partition"] != "train", r["name"]))
    sources = [config_path, Path(__file__), output / "scope_binding.json", output / "scheduler_snapshot.json",
        ROOT / "archive/fe110_completed_label_qc_20261024/run.py",
        ROOT / "archive/fe110_reico_followup_20261024/review.py",
        ROOT / "scripts/adsorption/collect_completed_batch.py", ROOT / "scripts/adsorption/reico_probe_review.py",
        ROOT / "scripts/aqcat25_calibration.py", ROOT / "scripts/neb_agent/utils_vasp.py",
        ROOT / "scripts/vasp_result_gate.py"]
    binding_doc = {"source_files": source_file_manifest(sources), "requested": done,
        "reserved_labels": "Physical QC only;never admitted to adaptive training coverage"}
    save_once(output / "main_collection_binding.json", binding_doc)
    inputs = {r["sample_id"]: r["input_hashes"] for r in load_json_object(paths["batch"])["samples"]}
    identity = identity_path()
    if smoke:
        done = done[:1]
    reviewed, failures = [], []
    for start in range(0, len(done), config["batch_size"]):
        chunk = done[start:start + config["batch_size"]]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {}
            for row in chunk:
                failure_path = output / "case_failures" / (row["name"] + ".json")
                if failure_path.exists():
                    failures.append(load_json_object(failure_path))
                    continue
                futures[pool.submit(process_one, row, selected[row["name"]], inputs[row["name"]], output,
                                    identity, current, sha256_json(binding_doc))] = row
            for future in as_completed(futures):
                row = futures[future]
                try:
                    label = future.result()
                    reviewed.append(label)
                    print(f"QC {len(reviewed)}/{len(done)} {row['name']} {label['data_qc_status']}", flush=True)
                except Exception as error:
                    failure = {"sample_id": row["name"], "job_id": row["job_id"], "error": str(error),
                        "automatic_retry": False}
                    save_once(output / "case_failures" / (row["name"] + ".json"), failure)
                    failures.append(failure)
                    print(f"BLOCKED {row['name']}: {error}", flush=True)
        if not smoke:
            save_once(output / f"batch_{start // config['batch_size'] + 1:03d}.json", {
                "requested": [r["name"] for r in chunk],
                "reviewed": sorted(r["sample_id"] for r in reviewed if r["sample_id"] in {v["name"] for v in chunk}),
                "binding_sha256": sha256_json(binding_doc)})
    reviewed.sort(key=lambda r: r["sample_id"])
    label_path = output / ("smoke_labels_local_only.json" if smoke else "new_label_qc_local_only.json")
    save_once(label_path, {"samples": reviewed, "source_files": source_file_manifest([
        config_path, output / "main_collection_binding.json", output / "scheduler_snapshot.json",
        *[output / "case_qc" / (r["sample_id"] + ".json") for r in reviewed]])})
    summary = {"status": "QC_COMPLETE" if not failures else "PARTIAL_FAILURE", "checked_at": current["checked_at"],
        "requested_DONE": len(done), "reviewed": len(reviewed),
        "qc_counts": dict(Counter(r["data_qc_status"] for r in reviewed)),
        "partition_counts": dict(Counter(r["partition"] for r in reviewed)), "failures": failures,
        "scheduler_counts": current["status_counts"], "new_DFT_GPU_training_or_submission": False,
        "source_files": source_file_manifest([label_path, config_path, output / "main_collection_binding.json"])}
    save_once(output / ("smoke_summary.json" if smoke else "qc_summary.json"), summary)
    print({k: v for k, v in summary.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("smoke", "process"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    collect(args.action == "smoke", args.config)
