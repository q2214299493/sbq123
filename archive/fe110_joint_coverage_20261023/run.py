"""Frozen 366-frame joint audit. Local descriptors only; no DFT/model execution."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import yaml

from scripts.adsorption.force_finetune import validate_label_row
from scripts.adsorption.reico_chemical_environments import chemical_environment
from scripts.adsorption.reico_environment_audit import describe, read_geometry, train_inventory
from scripts.adsorption.reico_force_coverage import checked_forces, matched_force_difference
from scripts.adsorption.reico_joint_coverage import fixed_threshold_soap, joint_force_table, missing_environment_groups
from scripts.adsorption.reico_selection import frame_distance
from scripts.adsorption.reico_stratified_audit import CachedSOAP
from scripts.artifact_io import sha256_file, sha256_json, source_file_manifest, source_file_manifest_valid, write_json


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/joint_coverage_v1.json"


def load(path):
    return json.loads(Path(path).read_bytes())


def save_once(path, data):
    if path.exists():
        if load(path) != data:
            raise ValueError(f"refusing changed checkpoint: {path}")
    else:
        write_json(path, data)


def enrich(row, atoms, rules, scales):
    return {**row, **chemical_environment(atoms, rules),
            "joint_by_scale": {str(s): chemical_environment(atoms, rules, scale=s)["joint_signature"] for s in scales}}


def descriptors(rows, atoms, old, old_cache, cache_hashes, own_cache, soap, cached, inventory):
    result = []
    for row in rows:
        path = old_cache / (row["structure_sha256"]+".npz")
        # Ignore extra files not bound by the prior training-cache inventory.
        reused = path.exists() and row["structure_sha256"] in cache_hashes
        if reused:
            if sha256_file(path) != cache_hashes[row["structure_sha256"]]:
                raise ValueError("old descriptor cache hash changed")
            record = describe(row, atoms[row["sample_id"]], cached, old_cache, old["descriptor"]["near_Fe_A"])
        else:
            record = describe(row, atoms[row["sample_id"]], soap, own_cache, old["descriptor"]["near_Fe_A"])
            path = own_cache / path.name
        if not np.allclose(np.linalg.norm(record["vectors"], axis=1), 1., atol=1e-10, rtol=0):
            raise ValueError("SOAP normalization failed")
        record["partition"] = "train"
        result.append(record)
        inventory.append({"sample_id": row["sample_id"], "path": str(path), "sha256": sha256_file(path),
                          "reused_prior_cache": reused})
    return result


def pair_review(rows, atoms, maximum):
    pairs = []
    for i, one in enumerate(rows):
        for two in rows[i+1:]:
            if one["composition"] != two["composition"]:
                continue
            first, second = atoms[one["sample_id"]], atoms[two["sample_id"]]
            if frame_distance(first, second) >= maximum:
                continue
            pairs.append({"first": one["sample_id"], "second": two["sample_id"],
                          "composition": one["composition"], "same_source_group": one["source_group"] == two["source_group"],
                          "magnetic_review_levels": [one["magnetic_review_level"], two["magnetic_review_level"]],
                          "same_joint_stratum": one["joint_signature"] == two["joint_signature"],
                          **matched_force_difference(first, second, one["forces_eV_per_A"], two["forces_eV_per_A"])})
    return sorted(pairs, key=lambda r: (-r["adsorbate"]["vector_RMSE_difference_eV_A"], r["first"], r["second"]))


def load_training(training, manifest_path, rules, scales):
    atoms, rows, files = {}, [], []
    for row in training:
        if row.get("split") != "train" or row.get("partition") != "train":
            raise ValueError("reserved label in training scope")
        validate_label_row(manifest_path.parent, row)
        geometry = {**row, "structure_path": str(manifest_path.parent/row["structure_path"])}
        current = read_geometry(geometry)
        if current[45:].get_chemical_formula() != row["composition"]:
            raise ValueError("composition mismatch")
        forces = checked_forces(current, row["forces_eV_per_A"])
        rows.append(enrich({**geometry, "family_id": row.get("family_id", row["calculation_group"]),
                            "source_group": row["calculation_group"],
                            "movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max())}, current, rules, scales))
        atoms[row["sample_id"]] = current
        files += [manifest_path.parent/row["structure_path"], manifest_path.parent/row["label_source"]["path"]]
    return atoms, rows, files


def run(config_path=CONFIG, smoke=False):
    from dscribe.descriptors import SOAP

    config = load(config_path)
    paths = {key: ROOT/item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError(f"input binding mismatch: {key}")
    output = ROOT/config["output"]
    if smoke:
        output = output.parent/(output.name+"_smoke")
    output.mkdir(parents=True, exist_ok=True)
    sources = source_file_manifest([config_path, *paths.values(), Path(__file__),
                                   ROOT/"scripts/adsorption/reico_joint_coverage.py",
                                   ROOT/"scripts/adsorption/reico_environment_audit.py",
                                   ROOT/"scripts/adsorption/reico_chemical_environments.py",
                                   ROOT/"scripts/adsorption/reico_force_coverage.py",
                                   ROOT/"scripts/adsorption/reico_selection.py",
                                   ROOT/"scripts/adsorption/force_finetune.py",
                                   ROOT/"scripts/adsmind_lite/relaxed_analysis.py"])
    save_once(output/"input_binding.json", {"source_files": sources, "smoke": smoke})
    if (output/"summary.json").exists():
        summary = load(output/"summary.json")
        if not source_file_manifest_valid(summary):
            raise ValueError("completed audit binding stale")
        if not source_file_manifest_valid(load(output/"output_inventory.json")):
            raise ValueError("completed outputs changed")
        return {"status": "REUSED_VERIFIED_COMPLETE", "training_frames": summary["training_frames"]}

    manifest = load(paths["manifest"])
    if not source_file_manifest_valid(manifest):
        raise ValueError("assembled package source binding stale")
    training = manifest["splits"]["train"]  # Never open reserved structures or label files.
    if len(training) != 366:
        raise ValueError("expected frozen 366-frame training package")
    pool, selected = train_inventory(load(paths["inventory"]), load(paths["selection"]))
    prior_frames = load(paths["prior_frames"])["frames"]
    if {r["sample_id"] for r in pool} != {r["sample_id"] for r in prior_frames}:
        raise ValueError("prior training scope differs")
    old = load(paths["prior_coverage"])
    if importlib.metadata.version("dscribe") != old["descriptor"]["dscribe"]:
        raise ValueError("SOAP version differs")
    old_cache = paths["prior_coverage"].parent/"descriptor_cache"/sha256_json(old["descriptor"])
    prior_caches = load(paths["prior_cache_inventory"])["files"]
    by_id = {r["sample_id"]: r for r in pool}
    cache_hashes = {by_id[r["sample_id"]]["structure_sha256"]: r["sha256"] for r in prior_caches}
    rules = yaml.safe_load(paths["analysis_rules"].read_text(encoding="utf-8"))["connectivity"]
    scales = config["radius_scales"]
    if smoke:
        training = [next(r for r in training if r["composition"] == comp and r["source_collection"] == source)
                    for comp, source in [("C2HO", "legacy_control_20261019"), ("C2H2O", "reviewed_reico_statics137"),
                                         ("C2H3", "10B_legacy_total_only6"), ("C3H2O", "reviewed_reico_statics137")]]
        pool = [next(r for r in pool if r["composition"] == comp) for comp in sorted({r["composition"] for r in training})]
    atoms, train_rows, label_files = load_training(training, paths["manifest"], rules, scales)
    print(f"validated {len(train_rows)} training labels", flush=True)
    pool_rows = []
    for i, row in enumerate(pool):
        current = read_geometry(row)
        atoms[row["sample_id"]] = current
        pool_rows.append(enrich(row, current, rules, scales))
        if (i+1) % 400 == 0:
            print(f"pool contacts {i+1}/{len(pool)}", flush=True)
    cache_inventory = []
    soap, cached = SOAP(**old["descriptor"]["soap"]), CachedSOAP(old["descriptor_features"])
    # Descriptor parameters are hash-bound in the inventory; keep Windows paths short.
    own_cache = output/"cache"
    train_desc = descriptors(train_rows, atoms, old, old_cache, cache_hashes, own_cache, soap, cached, cache_inventory)
    pool_desc = descriptors(pool_rows, atoms, old, old_cache, cache_hashes, own_cache, soap, cached, cache_inventory)
    print("descriptors verified; comparing composition-specific environments", flush=True)
    soap_report, scores = fixed_threshold_soap(pool_desc, train_desc, load(paths["prior_soap"]))
    score_map = {r["sample_id"]: r for r in scores}
    for row in pool_rows:
        row.update(score_map[row["sample_id"]])
    selected_ids = {r["sample_id"] for r in selected}
    chemical, missing = missing_environment_groups(pool_rows, train_rows, selected_ids)
    table = joint_force_table(train_rows, config["force_edges_eV_A"])
    save_once(output/"training_joint_force.json", table)
    save_once(output/"missing_environments.json", {"groups": missing})
    save_once(output/"training_environments.json", {"frames": [{k:v for k,v in r.items() if k != "forces_eV_per_A"} for r in train_rows]})
    save_once(output/"pool_environments.json", {"frames": pool_rows})
    print("joint tables saved; checking nearby labeled pairs", flush=True)
    pairs = pair_review(train_rows, atoms, config["near_pair_A"])
    save_once(output/"nearby_force_pairs.json", {"pairs": pairs})
    save_once(output/"descriptor_inventory.json", {"descriptor": old["descriptor"], "files": cache_inventory})
    summary = {"status": "SMOKE_PASS" if smoke else "JOINT_AUDIT_COMPLETE", "completed_utc": datetime.now(timezone.utc).isoformat(),
               "training_frames": len(train_rows), "pool_frames": len(pool_rows), "original_selected_training_frames": len(selected_ids),
               "chemical_coverage": chemical, "SOAP_with_fixed_prior_thresholds": soap_report,
               "training_force_by_composition": {c:{k:v for k,v in item.items() if k not in ("strata", "sample_ids")}
                                                 for c,item in table.items()},
               "missing_joint_strata": len(missing),
               "missing_strata_with_existing_selected_inputs": sum(bool(r["original_selected_labels_not_in_package"]) for r in missing),
               "missing_strata_with_robust_examples": sum(r["robust_missing_frames_all_scales"] > 0 for r in missing),
               "near_pairs": len(pairs), "near_pairs_below_0p1_A": sum(r["geometry_RMSD_A"] < .1 for r in pairs),
               "near_pairs_force_RMSE_above_1_eV_A": sum(r["adsorbate"]["vector_RMSE_difference_eV_A"] > 1 for r in pairs),
               "new_descriptor_training_frames": sum(not r["reused_prior_cache"] for r in cache_inventory[:len(train_rows)]),
               "source_files": sources+source_file_manifest(label_files+[Path(r["path"]) for r in cache_inventory]),
               "reserved_labels_used": False, "selection_weights_or_magnetic_tiers_changed": False,
               "new_DFT_or_model_execution": False, "force_of_unlabeled_candidates_known": False}
    save_once(output/"summary.json", summary)
    save_once(output/"output_inventory.json", {"source_files": source_file_manifest(list(output.glob("*.json")))})
    return {k: summary[k] for k in ("status", "training_frames", "pool_frames", "missing_joint_strata", "near_pairs")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.config, args.smoke)))
    except Exception as error:
        config = load(args.config)
        output = ROOT/config["output"]
        if args.smoke:
            output = output.parent/(output.name+"_smoke")
        write_json(output/("failure_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".json"),
                   {"error": str(error), "type": type(error).__name__})
        raise


if __name__ == "__main__":
    main()
