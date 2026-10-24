"""Independently count raw-force bins, missing types and cached SOAP distances."""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from pathlib import Path

import numpy as np

from archive.fe110_joint_coverage_20261023.prioritize import records
from archive.fe110_joint_coverage_20261023.run import save_once
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from .run import CONFIG, ROOT


def verify(evidence_root=ROOT, receipt="independent_verification.json"):
    config_path = evidence_root / CONFIG.relative_to(ROOT)
    config = load_json_object(config_path)
    paths = {key: evidence_root / item["path"] for key, item in config["inputs"].items()}
    output = evidence_root / config["output"]
    summary = load_json_object(output / "summary.json")
    assert source_file_manifest_valid(summary)
    assert source_file_manifest_valid(load_json_object(output / "output_inventory.json"))
    for key, path in paths.items():
        assert sha256_file(path) == config["inputs"][key]["sha256"]
    prior = load_json_object(paths["prior_training"])["frames"]
    additions = load_json_object(paths["additions"])["samples"]
    training = load_json_object(output / "audit_training_view_local_only.json")["frames"]
    assert len(training) == 440 and training[:378] == prior
    assert {r["sample_id"] for r in training} == {r["sample_id"] for r in prior + additions}
    assert all(r["partition"] == "train" for r in training)
    source = {r["sample_id"]: r for r in load_json_object(paths["frozen_manifest"])["splits"]["train"]}
    source.update({r["sample_id"]: r for r in prior if "forces_eV_per_A" in r})
    source.update({r["sample_id"]: r for r in additions})
    assert len(source) == len(training)
    table = load_json_object(output / "training_joint_force.json")
    edges = summary["force_edges_eV_A"]
    assert edges == load_json_object(paths["base_config"])["force_edges_eV_A"]
    for comp, item in table.items():
        rows = [r for r in training if r["composition"] == comp]
        values = [float(np.linalg.norm(np.asarray(source[r["sample_id"]]["forces_eV_per_A"])[18:], axis=1).max()) for r in rows]
        assert all(np.isclose(value, row["movable_fmax_eV_A"], atol=1e-12, rtol=0) for value, row in zip(values, rows, strict=True))
        bins = Counter(bisect_right(edges, value) - 1 for value in values)
        assert list(item["fmax_histogram"].values()) == [bins[i] for i in range(len(edges))]
        assert item["low_force_le_0p05"] == sum(value <= .05 for value in values)
        assert item["magnetic_review_levels"] == dict(Counter(source[r["sample_id"]]["magnetic_review_level"] for r in rows))
    pool = load_json_object(paths["pool"])["frames"]
    selected = {r["sample_id"] for r in load_json_object(paths["selection"])["selected"] if r["partition"] == "train"}
    current_ids = {r["sample_id"] for r in training}
    quarantined = set(config["excluded_training_sample_ids"])
    assert not quarantined & current_ids
    pending = selected - current_ids - quarantined
    assert len(pending) == 45
    future = training + [r for r in pool if r["sample_id"] in pending]
    actual_missing, future_missing = 0, 0
    expected_pairs = set()
    for comp in summary["chemical_coverage"]:
        target = {r["joint_signature"] for r in pool if r["composition"] == comp}
        current = {r["joint_signature"] for r in training if r["composition"] == comp}
        projected = {r["joint_signature"] for r in future if r["composition"] == comp}
        assert len(target - current) == summary["per_composition"][comp]["current_missing_joint_types"]
        expected_pairs.update((comp, signature) for signature in target - current)
        actual_missing += len(target - current)
        future_missing += len(target - projected)
    groups = load_json_object(output / "missing_environments.json")["groups"]
    assert {(r["composition"], r["joint_signature"]) for r in groups} == expected_pairs
    assert actual_missing == len(groups) == summary["missing_joint_types"]
    assert future_missing == summary["conditional_missing_if45_unreviewed_pass"]
    assert Counter(r["gap_category"] for r in groups) == summary["gap_categories"]
    for group in groups:
        assert set(group["quarantined_selected_input_ids"]) <= quarantined
        assert set(group["unreviewed_selected_input_ids"]) <= pending
    scores = {r["sample_id"]: r for r in load_json_object(output / "SOAP_frame_scores.json")["frames"]}
    thresholds = load_json_object(paths["prior_soap"])
    cache = {r["sample_id"]: r for r in load_json_object(paths["cache_inventory"])["files"]}
    checked = []
    for comp, report in summary["SOAP_with_fixed_prior_thresholds"].items():
        assert report["fixed_thresholds"] == thresholds[comp]["thresholds"]
        candidates = [r for r in pool if r["composition"] == comp]
        assert report["above_internal_threshold"] == sum(scores[r["sample_id"]]["exceeds_internal_threshold"] for r in candidates)
        examples = [max(candidates, key=lambda r: scores[r["sample_id"]]["novelty_ratio"]),
                    min(candidates, key=lambda r: scores[r["sample_id"]]["novelty_ratio"])]
        references = records([r for r in training if r["composition"] == comp], cache)
        for example in examples:
            query = records([example], cache)[0]
            ratio = 0.
            for role in set(query["roles"]):
                vectors = np.concatenate([r["vectors"][r["roles"] == role] for r in references if np.any(r["roles"] == role)])
                query_vectors = query["vectors"][query["roles"] == role]
                distance = float((1. - np.clip(np.max(query_vectors @ vectors.T, axis=1), -1., 1.)).max())
                ratio = max(ratio, distance / report["fixed_thresholds"][role])
            assert np.isclose(ratio, scores[example["sample_id"]]["novelty_ratio"], atol=1e-7, rtol=1e-7)
            checked.append(example["sample_id"])
    result = {"status": "PASS", "training_frames": len(training), "new_training_labels": len(additions),
        "raw_force_bin_rows_independently_checked": len(training), "missing_joint_types": actual_missing,
        "conditional_missing_excluding_quarantines": future_missing, "SOAP_frame_distance_checks": checked,
        "frozen366package_unchanged": True, "source_checkout": str(ROOT),
        "source_files": source_file_manifest([Path(__file__), config_path, output / "summary.json",
            output / "output_inventory.json", paths["frozen_manifest"], paths["prior_training"], paths["additions"]])}
    save_once(output / receipt, result)
    print({k: v for k, v in result.items() if k != "source_files"})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=ROOT)
    parser.add_argument("--receipt", default="independent_verification.json")
    args = parser.parse_args()
    verify(args.evidence_root, args.receipt)
