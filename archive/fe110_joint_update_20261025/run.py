"""Update the training-only joint audit with isolated PASS labels and frozen SOAP."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from archive.fe110_joint_coverage_20261023.prioritize import records
from archive.fe110_joint_coverage_20261023.run import enrich, save_once
from scripts.adsorption.reico_environment_audit import read_geometry
from scripts.adsorption.reico_joint_coverage import (
    fixed_threshold_soap, joint_force_table, missing_environment_groups, require_training,
)
from scripts.artifact_io import load_json_object, source_file_manifest, source_file_manifest_valid
from archive.fe110_joint_update_20261024.run import checked_cache, classify_gaps, merge_training
from .prepare import CONFIG, ROOT, prepare


def run():
    config, paths = prepare()
    output = ROOT / config["output"]
    output.mkdir(parents=True, exist_ok=True)
    sources = source_file_manifest([CONFIG, *paths.values(), Path(__file__),
        ROOT / "archive/fe110_joint_update_20261025/prepare.py",
        ROOT / "archive/fe110_joint_update_20261024/run.py",
        ROOT / "archive/fe110_joint_coverage_20261023/prioritize.py",
        ROOT / "archive/fe110_joint_coverage_20261023/run.py",
        ROOT / "scripts/adsorption/reico_joint_coverage.py",
        ROOT / "scripts/adsorption/reico_chemical_environments.py",
        ROOT / "scripts/adsorption/reico_environment_audit.py",
        ROOT / "scripts/adsorption/reico_force_coverage.py"])
    save_once(output / "input_binding.json", {"source_files": sources})
    if (output / "summary.json").exists():
        previous = load_json_object(output / "summary.json")
        if not source_file_manifest_valid(previous) or not source_file_manifest_valid(load_json_object(output / "output_inventory.json")):
            raise ValueError("completed update binding changed")
        print({"status": "REUSED_VERIFIED_COMPLETE", "training_frames": previous["training_frames"]})
        return
    additions = load_json_object(paths["additions"])
    if not source_file_manifest_valid(additions):
        raise ValueError("isolated training candidates changed")
    isolation = load_json_object(paths["isolation"])
    if isolation["geometry_conflicts"] or isolation["quarantined_sample_ids"]:
        raise ValueError("unresolved geometry isolation conflicts")
    prior = load_json_object(paths["prior_training"])["frames"]
    raw_new = additions["samples"]
    merge_training(prior, raw_new)  # Reject contamination before reading any new geometry.
    if len(prior) != config["expected_prior_frames"] or len(raw_new) != config["expected_additions"]:
        raise ValueError("expected440 prior and45 isolated training additions")
    base = load_json_object(paths["base_config"])
    rules = yaml.safe_load(paths["analysis_rules"].read_text(encoding="utf-8"))["connectivity"]
    new = [enrich({**r, "source_group": "reico_" + r["family_id"]}, read_geometry(r), rules,
                  base["radius_scales"]) for r in raw_new]
    training = merge_training(prior, new)
    if any(r["joint_signature"] != old["joint_signature"] for r, old in zip(training[:len(prior)], prior, strict=True)):
        raise ValueError("prior environment classification changed")
    pool = load_json_object(paths["pool"])["frames"]
    require_training(pool)
    cache, cache_paths = checked_cache(pool + training, load_json_object(paths["cache_inventory"]))
    save_once(output / "cache_binding.json", {"source_files": source_file_manifest(cache_paths),
        "reused_cache_files": len(cache_paths), "new_descriptors_computed": 0})
    pool_desc, train_desc = records(pool, cache), records(training, cache)
    print(f"validated{len(training)}training frames;cached SOAP comparison over{len(pool)}pool frames", flush=True)
    soap, scores = fixed_threshold_soap(pool_desc, train_desc, load_json_object(paths["prior_soap"]))
    score_map = {r["sample_id"]: r for r in scores}
    scored_pool = [{**r, **score_map[r["sample_id"]]} for r in pool]
    selected_ids = {r["sample_id"] for r in load_json_object(paths["selection"])["selected"] if r["partition"] == "train"}
    current_ids = {r["sample_id"] for r in training}
    missing_ids = selected_ids - current_ids
    quarantined = set(config["excluded_training_sample_ids"])
    published_exclusions = {r["sample_id"] for r in load_json_object(paths["quarantine_authority"])["exception_details"]
                            if r["partition"] == "train" and r["data_qc_status"] != "PASS"}
    if quarantined != published_exclusions or not quarantined <= missing_ids:
        raise ValueError("quarantine boundary changed")
    pending_ids = missing_ids - quarantined
    chemical, missing = missing_environment_groups(scored_pool, training, selected_ids)
    classified = classify_gaps(missing, quarantined)
    table = joint_force_table(training, base["force_edges_eV_A"])
    pending_geometry = [r for r in pool if r["sample_id"] in pending_ids]
    if pending_geometry or pending_ids:
        raise ValueError("all original selected training labels must already be reviewed")
    prior_summary = load_json_object(paths["prior_summary"])
    per_composition = {}
    for comp in chemical:
        prior_count = prior_summary["chemical_coverage"][comp]["joint_signature"]["current_missing"]
        groups = [g for g in classified if g["composition"] == comp]
        per_composition[comp] = {"prior_frames": sum(r["composition"] == comp for r in prior),
            "current_frames": table[comp]["frames"], "prior_missing_joint_types": prior_count,
            "current_missing_joint_types": len(groups), "newly_covered_joint_types": prior_count - len(groups),
            "gap_categories": dict(Counter(g["gap_category"] for g in groups)),
            "robust_missing_groups_all_cutoffs": sum(g["robust_missing_frames_all_scales"] > 0 for g in groups),
            "prior_SOAP_gap_frames": prior_summary["SOAP_with_fixed_prior_thresholds"][comp]["above_internal_threshold"],
            "current_SOAP_gap_frames": soap[comp]["above_internal_threshold"],
            "low_force_le_0p05": table[comp]["low_force_le_0p05"],
            "low_force_source_groups": table[comp]["low_force_source_groups"],
            "low_force_joint_strata": table[comp]["low_force_joint_strata"],
            "magnetic_review_levels": table[comp]["magnetic_review_levels"]}
    outputs = {"audit_training_view_local_only.json": {"frames": training, "is_training_package": False},
        "training_joint_force.json": table, "missing_environments.json": {"groups": classified},
        "chemical_coverage_native.json": chemical, "SOAP_frame_scores.json": {"frames": scores},
        "completion_boundary.json": {"unreviewed_selected_ids": sorted(pending_ids),
            "quarantined_ids_excluded": sorted(quarantined), "all_original_selected_labels_reviewed": True,
            "training_package_changed": False, "no_DFT_force_imputed_for_missing_geometries": True}}
    for name, data in outputs.items():
        save_once(output / name, data)
    summary = {"status": "TRAINING_JOINT_COVERAGE_UPDATE_COMPLETE", "training_frames": len(training),
        "prior_training_frames": len(prior), "added_training_frames": len(new), "pool_frames": len(pool),
        "original_selected_train": len(selected_ids), "selected_train_in_current_view": len(selected_ids & current_ids),
        "selected_train_not_in_view": len(missing_ids), "unreviewed_selected_train": len(pending_ids),
        "quarantined_selected_train": sorted(quarantined), "per_composition": per_composition,
        "chemical_coverage": chemical, "SOAP_with_fixed_prior_thresholds": soap,
        "prior_missing_joint_types": prior_summary["missing_joint_types"], "missing_joint_types": len(classified),
        "gap_categories": dict(Counter(g["gap_category"] for g in classified)),
        "all_original_selected_labels_reviewed": not pending_ids,
        "newly_covered_joint_types": prior_summary["missing_joint_types"] - len(classified),
        "training_force_by_composition": {c: {k: v for k, v in row.items() if k not in {"strata", "sample_ids"}} for c, row in table.items()},
        "force_edges_eV_A": base["force_edges_eV_A"], "radius_scales": base["radius_scales"],
        "new_descriptor_calculations": 0, "frozen366package_changed": False,
        "reserved_labels_used_for_coverage_or_ranking": False, "new_DFT_GPU_training_or_submission": False,
        "source_files": sources + source_file_manifest([output / "cache_binding.json", *[output / name for name in outputs]])}
    save_once(output / "summary.json", summary)
    save_once(output / "output_inventory.json", {"source_files": source_file_manifest([
        output / "summary.json", output / "input_binding.json", output / "cache_binding.json", *[output / name for name in outputs]])})
    print({k: summary[k] for k in ("training_frames", "added_training_frames", "prior_missing_joint_types",
        "missing_joint_types", "gap_categories", "newly_covered_joint_types")}, flush=True)


if __name__ == "__main__":
    run()
