"""Combine only existing isolated PASS train candidates; preserve their grades."""
from __future__ import annotations

from pathlib import Path

from archive.fe110_joint_update_20261024.run import merge_training
from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/joint_update_20261025_v1.json"


def combine_candidates(candidates, reports):
    rows = []
    for candidate, report in zip(candidates, reports, strict=True):
        if (report["geometry_conflicts"] or report["quarantined_sample_ids"]
                or report["threshold_A"] != .20 or report["reserved_geometries"] != 513
                or report["reserved_forces_or_energies_used"]):
            raise ValueError("existing isolation audit is incompatible or has conflicts")
        rows.extend(candidate["samples"])
    merge_training([], rows)
    return rows


def prepare():
    config = load_json_object(CONFIG)
    paths = {key: ROOT / item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen input changed: " + key)
    candidates, reports = [], []
    for batch in config["addition_batches"]:
        candidate = load_json_object(paths[batch["labels"]])
        if (not source_file_manifest_valid(candidate)
                or len(candidate["samples"]) != batch["expected_frames"]
                or not source_file_manifest_valid(load_json_object(paths[batch["binding"]]))):
            raise ValueError("existing label or isolation source binding changed")
        candidates.append(candidate)
        reports.append(load_json_object(paths[batch["isolation"]]))
    rows = combine_candidates(candidates, reports)
    prior = load_json_object(paths["prior_training"])["frames"]
    merge_training(prior, rows)
    if len(prior) != config["expected_prior_frames"] or len(rows) != config["expected_additions"]:
        raise ValueError("expected440 prior and45 isolated additions")
    output = ROOT / config["output"]
    source_files = source_file_manifest([CONFIG, Path(__file__), *paths.values()])
    paths["additions"] = output / "isolated_additions_local_only.json"
    paths["isolation"] = output / "reused_isolation_evidence.json"
    save_once(paths["additions"], {"samples": rows, "is_training_package": False,
        "source_files": source_files})
    save_once(paths["isolation"], {"geometry_conflicts": [], "quarantined_sample_ids": [],
        "threshold_A": .20, "reserved_geometries": 513, "reserved_forces_or_energies_used": False,
        "comparisons_in_reused_audits": sum(r["comparisons"] for r in reports),
        "new_geometry_comparisons": 0, "existing_isolation_audits_reused": len(reports),
        "method": "Reuse four hash-bound native clean-face Fe110 symmetry isolation audits",
        "source_files": source_files})
    print({"prior_frames": len(prior), "isolated_train_additions": len(rows),
        "prior_isolation_comparisons_reused": sum(r["comparisons"] for r in reports)}, flush=True)
    return config, paths


if __name__ == "__main__":
    prepare()
