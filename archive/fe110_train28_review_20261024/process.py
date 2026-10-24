"""Collect and natively review only DONE jobs in the configured train-only checkpoint."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from archive.fe110_completed_label_qc_20261024.run import process_one
from archive.fe110_reico_label_qc_20261023.collect import identity_path
from archive.fe110_train45_review_20261024.process_main import prioritized_done
from scripts.artifact_io import load_json_object, sha256_json, source_file_manifest
from .run import DEFAULT_CONFIG, ROOT, save_once, scope, snapshot


def collect(config_path=DEFAULT_CONFIG):
    config, paths, current = snapshot(config_path)
    _, _, selected, _, _, groups = scope(config_path)
    output = ROOT / config["output"]
    done = prioritized_done(current["jobs"], groups)
    sources = [config_path, Path(__file__), output / "scope_binding.json", output / "scheduler_snapshot.json",
        ROOT / "archive/fe110_train45_review_20261024/process_main.py",
        ROOT / "archive/fe110_completed_label_qc_20261024/run.py",
        ROOT / "archive/fe110_reico_followup_20261024/review.py",
        ROOT / "scripts/adsorption/collect_completed_batch.py", ROOT / "scripts/adsorption/reico_probe_review.py",
        ROOT / "scripts/aqcat25_calibration.py", ROOT / "scripts/neb_agent/utils_vasp.py",
        ROOT / "scripts/vasp_result_gate.py"]
    binding_doc = {"source_files": source_file_manifest(sources), "requested": done,
        "priority": "One DONE representative per remaining gap first;all other DONE retained"}
    save_once(output / "main_collection_binding.json", binding_doc)
    inputs = {r["sample_id"]: r["input_hashes"] for r in load_json_object(paths["batch"])["samples"]}
    identity = identity_path() if done else None
    reviewed, failures = [], []
    for row in done:
        failure_path = output / "case_failures" / (row["name"] + ".json")
        if failure_path.exists():
            failures.append(load_json_object(failure_path))
            continue
        try:
            label = process_one(row, selected[row["name"]], inputs[row["name"]], output,
                                identity, current, sha256_json(binding_doc))
            reviewed.append(label)
            print(f"QC {row['name']} job{row['job_id']} {label['data_qc_status']}", flush=True)
        except Exception as error:
            failure = {"sample_id": row["name"], "job_id": row["job_id"], "error": str(error),
                "automatic_retry": False}
            save_once(failure_path, failure)
            failures.append(failure)
            print(f"BLOCKED {row['name']}: {error}", flush=True)
    reviewed.sort(key=lambda r: r["sample_id"])
    label_path = output / "new_label_qc_local_only.json"
    save_once(label_path, {"samples": reviewed, "source_files": source_file_manifest([
        config_path, output / "main_collection_binding.json", output / "scheduler_snapshot.json",
        *[output / "case_qc" / (r["sample_id"] + ".json") for r in reviewed]])})
    summary = {"status": "QC_COMPLETE" if not failures else "PARTIAL_FAILURE", "checked_at": current["checked_at"],
        "requested_DONE": len(done), "reviewed": len(reviewed),
        "qc_counts": dict(Counter(r["data_qc_status"] for r in reviewed)),
        "partition_counts": dict(Counter(r["partition"] for r in reviewed)), "failures": failures,
        "scheduler_counts": current["status_counts"], "new_DFT_GPU_training_or_submission": False,
        "source_files": source_file_manifest([label_path, config_path, output / "main_collection_binding.json"])}
    save_once(output / "qc_summary.json", summary)
    print({k: v for k, v in summary.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    collect()
