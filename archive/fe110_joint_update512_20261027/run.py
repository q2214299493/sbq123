"""Update frozen-threshold joint coverage from the actual512-frame train split."""
from __future__ import annotations

from collections import Counter
import importlib.metadata
import inspect
from pathlib import Path
import sys

import numpy as np
from threadpoolctl import threadpool_limits
import yaml

from archive.fe110_joint_coverage_20261023.prioritize import records
from archive.fe110_joint_coverage_20261023.run import load_training
from archive.fe110_joint_update_20261024.run import checked_cache, classify_gaps
from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.adsorption.reico_environment_audit import describe, read_geometry
from scripts.adsorption.reico_joint_coverage import fixed_threshold_soap, joint_force_table, missing_environment_groups, require_training
from scripts.adsorption.reico_stratified_audit import CachedSOAP
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/joint_update512_20261027_v1.json"


def scope():
    config = load_json_object(CONFIG)
    paths = {key: ROOT / item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen input changed " + key)
    for key in ("manifest", "package_verification", "prior_summary"):
        if not source_file_manifest_valid(load_json_object(paths[key])):
            raise ValueError("source binding stale " + key)
    return config, paths, ROOT / config["output"]


def unchanged_prefix(training, prior):
    if len(training) != 512 or len(prior) != 485:
        raise ValueError("expected512/485 reference counts")
    for row, old in zip(training[:485], prior, strict=True):
        for key in ("sample_id", "partition", "structure_sha256", "graph_signature", "joint_signature",
                    "joint_by_scale", "movable_fmax_eV_A", "magnetic_review_level", "family_id", "source_group"):
            if row[key] != old[key]:
                raise ValueError("prior485 reference changed " + key)


def classify_current_gaps(groups, quarantined, excluded_target):
    result = classify_gaps(groups, quarantined)
    for row in result:
        row["excluded_completed_target_label_ids"] = sorted(set(row["sample_ids"]) & {excluded_target})
        if row["excluded_completed_target_label_ids"] and row["gap_category"] == "UNSELECTED_LOCAL_ENVIRONMENT":
            row["gap_category"] = "EXCLUDED_TARGET_LABEL_PRESENT"
        row["qualified_DFT_forces_for_missing_geometries"] = "UNKNOWN_NOT_IMPUTED"
    return result


def soap_runtime(config, descriptor):
    sys.path.insert(0, str(ROOT / config["descriptor_runtime"]))
    from dscribe.descriptors import SOAP
    import dscribe.ext
    import sparse
    version = importlib.metadata.version("dscribe")
    if version != descriptor["dscribe"]:
        raise ValueError("SOAP version differs from frozen caches")
    soap = SOAP(**descriptor["soap"])
    if soap.get_number_of_features() != 544:
        raise ValueError("SOAP feature dimension differs")
    files = [Path(inspect.getfile(SOAP)), Path(dscribe.ext.__file__), Path(sparse.__file__)]
    return soap, files, {name: importlib.metadata.version(name) for name in ("dscribe", "sparse", "ase", "numpy", "scipy")}


def descriptor_inventory(pool, training, atoms, old_inventory, output, soap):
    old = {r["sample_id"]: r for r in old_inventory["files"]}
    all_rows = {r["sample_id"]: r for r in pool + training}
    known = [r for r in all_rows.values() if r["sample_id"] in old]
    checked_cache(known, old_inventory)
    descriptor = old_inventory["descriptor"]
    near = descriptor["near_Fe_A"]
    replay = []
    # Validate the discovered runtime against one bound old cache per composition.
    for comp in sorted({r["composition"] for r in pool}):
        row = next(r for r in pool if r["composition"] == comp)
        a = read_geometry(row)
        record = describe(row, a, CachedSOAP(544), Path(old[row["sample_id"]]["path"]).parent, near)
        from scripts.adsorption.reico_environment_audit import local_centers
        values = soap.create(a, centers=local_centers(a, near), n_jobs=1)
        values /= np.linalg.norm(values, axis=1)[:, None]
        difference = float(np.max(np.abs(values - record["vectors"])))
        if difference > 1e-10:
            raise ValueError("fresh/cached SOAP mismatch")
        replay.append({"sample_id": row["sample_id"], "maximum_absolute_difference": difference})
    inventory, new = [], []
    for row in all_rows.values():
        sid = row["sample_id"]
        if sid in old:
            path = Path(old[sid]["path"])
            describe(row, atoms[sid] if sid in atoms else read_geometry(row), CachedSOAP(544), path.parent, near)
            inventory.append({**old[sid], "structure_sha256": row["structure_sha256"], "new_descriptor": False})
        else:
            if row["partition"] != "train" or sid not in atoms:
                raise ValueError("new descriptor outside actual training data")
            describe(row, atoms[sid], soap, output / "cache", near)
            path = output / "cache" / (row["structure_sha256"] + ".npz")
            inventory.append({"sample_id": sid, "path": str(path), "sha256": sha256_file(path),
                              "structure_sha256": row["structure_sha256"], "new_descriptor": True})
            new.append(sid)
    return {"descriptor": descriptor, "files": inventory}, new, replay


def run():
    config, paths, output = scope()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "summary.json").exists():
        result = load_json_object(output / "summary.json")
        if not source_file_manifest_valid(result) or not source_file_manifest_valid(load_json_object(output / "output_inventory.json")):
            raise ValueError("completed coverage evidence changed")
        return result
    base = load_json_object(paths["base_config"])
    if config["force_edges_eV_A"] != base["force_edges_eV_A"] or config["radius_scales"] != base["radius_scales"]:
        raise ValueError("force bins or chemical cutoffs changed")
    manifest = load_json_object(paths["manifest"])
    train = manifest["splits"]["train"]  # Protected labels never enter coverage calculations.
    require_training(train)
    rules = yaml.safe_load(paths["analysis_rules"].read_text(encoding="utf-8"))["connectivity"]
    atoms, training, label_files = load_training(train, paths["manifest"], rules, config["radius_scales"])
    prior = load_json_object(paths["prior_training"])["frames"]
    unchanged_prefix(training, prior)
    excluded = load_json_object(paths["excluded_target_qc"])["samples"]
    if len(excluded) != 1 or excluded[0]["sample_id"] != config["excluded_target_label"] or excluded[0]["data_qc_status"] == "PASS":
        raise ValueError("excluded completed target review changed")
    pool = load_json_object(paths["pool"])["frames"]
    require_training(pool)
    if len(pool) != config["expected_pool"]:
        raise ValueError("fixed1597 training pool changed")
    old_inventory = load_json_object(paths["cache_inventory"])
    soap, runtime_files, versions = soap_runtime(config, old_inventory["descriptor"])
    dependencies = [CONFIG, *paths.values(), Path(__file__), Path(__file__).with_name("verify.py"),
        ROOT / "scripts/adsorption/reico_joint_coverage.py", ROOT / "scripts/adsorption/reico_environment_audit.py",
        ROOT / "scripts/adsorption/reico_chemical_environments.py", ROOT / "scripts/adsorption/reico_force_coverage.py",
        ROOT / "archive/fe110_joint_coverage_20261023/run.py", ROOT / "archive/fe110_joint_update_20261024/run.py",
        *runtime_files, *label_files]
    save_once(output / "input_binding.json", {"source_files": source_file_manifest(dependencies), "runtime_versions": versions})
    print("validated512training labels;unchanged485prefix;computing16newCPU descriptors", flush=True)
    inventory, new, replay = descriptor_inventory(pool, training, atoms, old_inventory, output, soap)
    if len(new) != config["expected_new_descriptors"]:
        raise ValueError("expected exactly16new reference descriptors")
    save_once(output / "descriptor_inventory.json", inventory)
    save_once(output / "descriptor_validation.json", {"runtime_versions": versions, "old_cache_replays": replay,
        "new_descriptor_ids": new, "new_descriptor_count": len(new), "old_cache_checks": len(inventory["files"])-len(new),
        "source_files": source_file_manifest([Path(r["path"]) for r in inventory["files"]])})
    cache = {r["sample_id"]: r for r in inventory["files"]}
    with threadpool_limits(limits=2):
        soap_report, scores = fixed_threshold_soap(records(pool, cache), records(training, cache), load_json_object(paths["prior_soap"]))
    score_map = {r["sample_id"]: r for r in scores}
    pool = [{**r, **score_map[r["sample_id"]]} for r in pool]
    selected = {r["sample_id"] for r in load_json_object(paths["selection"])["selected"] if r["partition"] == "train"}
    original_quarantines = set(config["original_selected_quarantines"])
    current = {r["sample_id"] for r in training}
    if selected-current != original_quarantines or (original_quarantines | {config["excluded_target_label"]}) & current:
        raise ValueError("selected-label quarantine boundary changed")
    chemical, missing = missing_environment_groups(pool, training, selected)
    classified = classify_current_gaps(missing, original_quarantines, config["excluded_target_label"])
    table = joint_force_table(training, config["force_edges_eV_A"])
    prior_summary = load_json_object(paths["prior_summary"])
    per_comp = {}
    for comp in chemical:
        gaps = [g for g in classified if g["composition"] == comp]
        per_comp[comp] = {"training_frames": table[comp]["frames"],
            "prior_missing_joint_types": prior_summary["per_composition"][comp]["current_missing_joint_types"],
            "missing_joint_types": len(gaps), "robust_missing_groups_all_scales": sum(g["robust_missing_frames_all_scales"] > 0 for g in gaps),
            "prior_SOAP_outliers": prior_summary["SOAP_with_fixed_prior_thresholds"][comp]["above_internal_threshold"],
            "SOAP_outliers": soap_report[comp]["above_internal_threshold"],
            "low_force_le_0p05": table[comp]["low_force_le_0p05"],
            "low_force_source_groups": table[comp]["low_force_source_groups"],
            "low_force_joint_strata": table[comp]["low_force_joint_strata"],
            "minimum_movable_fmax_eV_A": table[comp]["fmax_range_eV_A"][0]}
    outputs = {"training_environments_local_only.json": {"frames": training, "is_training_package": False},
        "training_joint_force.json": table, "missing_environments.json": {"groups": classified},
        "chemical_coverage.json": chemical, "SOAP_frame_scores.json": {"frames": scores}}
    for name, value in outputs.items():
        save_once(output / name, value)
    summary = {"status": "512_TRAIN_JOINT_COVERAGE_COMPLETE", "training_frames": 512, "prior_training_frames": 485,
        "new_training_frames": 27, "pool_frames": len(pool), "per_composition": per_comp,
        "prior_missing_joint_types": prior_summary["missing_joint_types"], "missing_joint_types": len(classified),
        "newly_covered_joint_types": prior_summary["missing_joint_types"]-len(classified),
        "gap_categories": dict(Counter(g["gap_category"] for g in classified)),
        "remaining_SOAP_outliers": sum(r["above_internal_threshold"] for r in soap_report.values()),
        "SOAP_with_fixed_prior_thresholds": soap_report, "force_edges_eV_A": config["force_edges_eV_A"],
        "radius_scales": config["radius_scales"], "new_descriptor_count": len(new), "cached_descriptor_replays": 4,
        "excluded_original_selected_labels": sorted(original_quarantines), "excluded_completed_target": config["excluded_target_label"],
        "unreviewed_original_selected_train_labels": 0, "magnetic_levels": dict(Counter(r["magnetic_review_level"] for r in training)),
        "training_package_unchanged": True, "reserved_labels_used_for_coverage_or_ranking": False,
        "new_DFT_GPU_training_or_submission": False, "model_accuracy_or_speedup_verified": False,
        "source_files": source_file_manifest([output / "input_binding.json", output / "descriptor_inventory.json",
            output / "descriptor_validation.json", *[output / name for name in outputs]])}
    save_once(output / "summary.json", summary)
    save_once(output / "output_inventory.json", {"source_files": source_file_manifest([
        output / "summary.json", output / "input_binding.json", output / "descriptor_inventory.json",
        output / "descriptor_validation.json", *[output / name for name in outputs]])})
    print({k: summary[k] for k in ("training_frames", "missing_joint_types", "newly_covered_joint_types", "remaining_SOAP_outliers")}, flush=True)
    return summary


if __name__ == "__main__":
    run()
