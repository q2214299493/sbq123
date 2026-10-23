"""Replay real static labels and independently count the updated audit view."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from pathlib import Path

import numpy as np

from scripts.adsorption.reico_probe_review import validate_static
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from .collect import save_once


def verify(output, receipt_name="independent_verification.json"):
    summary = load_json_object(output/"summary.json")
    labels = load_json_object(output/"new_label_qc_local_only.json")
    assert source_file_manifest_valid(summary) and source_file_manifest_valid(labels)
    snapshot = load_json_object(output/"scheduler_snapshot.json")
    assert len(snapshot["jobs"]) == 79
    done = {r["name"] for r in snapshot["jobs"] if r["status"] == "DONE"}
    assert done == {r["sample_id"] for r in labels["samples"]}
    for row in labels["samples"]:
        directory = Path(row["structure_path"]).parent
        for name,digest in row["input_output_hashes"].items():
            assert sha256_file(directory/name) == digest
        replay = validate_static(directory, row["symbols"])
        for key in ("forces_eV_per_A", "local_magnetization_muB", "total_magnetization_muB", "SCF", "toten_eV_force_label_only"):
            assert row[key] == replay[key]
    paths = {Path(r["path"]).name:Path(r["path"]) for r in summary["source_files"]}
    config = load_json_object(next(p for p in paths.values() if p.name == "followup_20261024_v1.json"))
    root = Path(__file__).resolve().parents[2]
    # Source evidence is rooted at the actual primary output, also during release replay.
    evidence_root = output.parents[2]
    manifest_path = evidence_root/config["inputs"]["manifest"]["path"]
    assert sha256_file(manifest_path) == config["inputs"]["manifest"]["sha256"]
    original = load_json_object(manifest_path)["splits"]["train"]
    old_ids = {r["sample_id"] for r in original}
    training = load_json_object(output/"audit_training_view_local_only.json")["frames"]
    new_train = [r for r in labels["samples"] if r["partition"] == "train" and r["data_qc_status"] == "PASS"]
    assert {r["sample_id"] for r in training} == old_ids | {r["sample_id"] for r in new_train}
    source = {r["sample_id"]:r for r in original+new_train}
    assert len(training) == len(source) == 378
    table = load_json_object(output/"training_joint_force.json")
    edges = [0,.05,.1,.5,1,2,5,10]
    for comp,item in table.items():
        rows = [r for r in training if r["composition"] == comp]
        values = [float(np.linalg.norm(np.array(source[r["sample_id"]]["forces_eV_per_A"])[18:],axis=1).max()) for r in rows]
        counts = Counter(bisect_right(edges,value)-1 for value in values)
        assert list(item["fmax_histogram"].values()) == [counts[i] for i in range(len(edges))]
        assert item["low_force_le_0p05"] == sum(value <= .05 for value in values)
    base_config = load_json_object(evidence_root/config["inputs"]["prior_joint_config"]["path"])
    pool = load_json_object(evidence_root/base_config["output"]/"pool_environments.json")["frames"]
    selected = load_json_object(evidence_root/config["inputs"]["selection"]["path"])["selected"]
    selected_ids = {r["sample_id"] for r in selected if r["partition"] == "train"}
    future = training+[r for r in pool if r["sample_id"] in selected_ids-{t["sample_id"] for t in training}]
    assert len(future) == 487
    missing = conditional = 0
    for comp in summary["chemical_coverage"]:
        target = {r["joint_signature"] for r in pool if r["composition"] == comp}
        current = {r["joint_signature"] for r in training if r["composition"] == comp}
        planned = {r["joint_signature"] for r in future if r["composition"] == comp}
        missing += len(target-current)
        conditional += len(target-planned)
    assert missing == summary["missing_joint_types"] == 284 and conditional == 187
    candidates = load_json_object(output/"targeted_candidates.json")
    assert len(candidates["geometry_backups"]) == len(candidates["priority_low_force_sources"]) == 2
    for row in candidates["geometry_backups"]+candidates["priority_low_force_sources"]:
        assert sha256_file(Path(row["structure_path"])) == row["structure_sha256"]
    result = {"status":"PASS", "new_static_replays":len(labels["samples"]),
              "audit_training_frames":len(training), "joint_missing_types":missing,
              "conditional_joint_missing_types":conditional, "candidate_structure_hashes_checked":4,
              "source_checkout":str(root), "original366manifest_unchanged":True,
              "source_files":source_file_manifest([Path(__file__), output/"summary.json", output/"new_label_qc_local_only.json",
                                                  Path(validate_static.__code__.co_filename)])}
    save_once(output/receipt_name, result)
    print({k:v for k,v in result.items() if k != "source_files"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", default="independent_verification.json")
    args = parser.parse_args()
    verify(args.output, args.receipt)
