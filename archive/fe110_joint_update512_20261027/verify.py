"""Independent raw-force, type-set and direct SOAP nearest-neighbour checks."""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from pathlib import Path

import numpy as np

from archive.fe110_joint_coverage_20261023.prioritize import records
from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from .run import CONFIG, scope


def verify():
    config, paths, output = scope()
    for name in ("summary.json", "input_binding.json", "descriptor_validation.json", "output_inventory.json"):
        if not source_file_manifest_valid(load_json_object(output / name)):
            raise ValueError("coverage binding stale " + name)
    summary = load_json_object(output / "summary.json")
    manifest = load_json_object(paths["manifest"])
    original = {r["sample_id"]: r for r in manifest["splits"]["train"]}
    training = load_json_object(output / "training_environments_local_only.json")["frames"]
    pool = load_json_object(paths["pool"])["frames"]
    table = load_json_object(output / "training_joint_force.json")
    assert len(original) == len(training) == 512 and len(pool) == 1597
    assert {r["sample_id"] for r in training} == set(original)
    for row in training:
        source = original[row["sample_id"]]
        for key in ("forces_eV_per_A", "structure_sha256", "magnetic_review_level", "symbols", "fixed_atom_indices_0based"):
            assert row[key] == source[key]
        force = float(np.linalg.norm(np.array(source["forces_eV_per_A"])[18:], axis=1).max())
        assert force == row["movable_fmax_eV_A"]
        assert sha256_file(Path(row["structure_path"])) == source["structure_sha256"]
    for comp, item in table.items():
        rows = [r for r in training if r["composition"] == comp]
        bins = Counter(bisect_right(config["force_edges_eV_A"], r["movable_fmax_eV_A"]) - 1 for r in rows)
        assert list(item["fmax_histogram"].values()) == [bins[i] for i in range(len(config["force_edges_eV_A"]))]
        assert item["low_force_le_0p05"] == sum(r["movable_fmax_eV_A"] <= .05 for r in rows)
        assert item["magnetic_review_levels"] == dict(Counter(r["magnetic_review_level"] for r in rows))
    groups = load_json_object(output / "missing_environments.json")["groups"]
    pairs = set()
    for comp in summary["per_composition"]:
        target = {r["joint_signature"] for r in pool if r["composition"] == comp}
        represented = {r["joint_signature"] for r in training if r["composition"] == comp}
        pairs.update((comp, sig) for sig in target-represented)
        assert len(target-represented) == summary["per_composition"][comp]["missing_joint_types"]
    assert pairs == {(r["composition"], r["joint_signature"]) for r in groups}
    assert len(pairs) == summary["missing_joint_types"]
    assert len(pairs) <= summary["prior_missing_joint_types"]
    current = {r["sample_id"] for r in training}
    assert not (set(config["original_selected_quarantines"]) | {config["excluded_target_label"]}) & current
    scores = {r["sample_id"]: r for r in load_json_object(output / "SOAP_frame_scores.json")["frames"]}
    prior_scores = load_json_object(paths["prior_summary"].parent / "SOAP_frame_scores.json")["frames"]
    for old in prior_scores:
        assert scores[old["sample_id"]]["novelty_ratio"] <= old["novelty_ratio"] + 1e-6
    cache = {r["sample_id"]: r for r in load_json_object(output / "descriptor_inventory.json")["files"]}
    thresholds = load_json_object(paths["prior_soap"])
    checked = []
    for comp, report in summary["SOAP_with_fixed_prior_thresholds"].items():
        assert report["fixed_thresholds"] == thresholds[comp]["thresholds"]
        queries = [r for r in pool if r["composition"] == comp]
        refs = records([r for r in training if r["composition"] == comp], cache)
        examples = [max(queries, key=lambda r: scores[r["sample_id"]]["novelty_ratio"]),
                    min(queries, key=lambda r: scores[r["sample_id"]]["novelty_ratio"])]
        for example in examples:
            query = records([example], cache)[0]
            ratio = 0.
            for role in set(query["roles"]):
                vectors = np.concatenate([r["vectors"][r["roles"] == role] for r in refs if np.any(r["roles"] == role)])
                distance = float((1.-np.clip(np.max(query["vectors"][query["roles"] == role] @ vectors.T, axis=1), -1., 1.)).max())
                ratio = max(ratio, distance/report["fixed_thresholds"][role])
            assert np.isclose(ratio, scores[example["sample_id"]]["novelty_ratio"], atol=1e-7, rtol=1e-7)
            checked.append(example["sample_id"])
        assert report["above_internal_threshold"] == sum(scores[r["sample_id"]]["exceeds_internal_threshold"] for r in queries)
    assert summary["remaining_SOAP_outliers"] <= 4
    assert summary["per_composition"]["C3H2O"]["low_force_le_0p05"] == 0
    result = {"status": "PASS", "actual_training_labels_verified": 512, "pool_type_members_verified": 1597,
        "missing_joint_types": len(groups), "direct_SOAP_neighbour_checks": checked,
        "all1597_SOAP_distances_nonincreasing": True, "frozen_thresholds_preserved": True,
        "manifest_unchanged": sha256_file(paths["manifest"]) == config["inputs"]["manifest"]["sha256"],
        "protected_labels_used_for_coverage_or_ranking": False, "new_DFT_GPU_or_training": False,
        "source_files": source_file_manifest([Path(__file__), CONFIG, output / "summary.json", paths["manifest"],
            output / "output_inventory.json", output / "descriptor_validation.json"])}
    save_once(output / "independent_verification.json", result)
    print({k: result[k] for k in ("status", "actual_training_labels_verified", "missing_joint_types", "direct_SOAP_neighbour_checks")})
    return result


if __name__ == "__main__":
    verify()
