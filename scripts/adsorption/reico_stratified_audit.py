"""Read cached training SOAP and audit composition/graph/Fe-contact strata only."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from scripts.adsmind_lite.relaxed_analysis import connectivity_change
from scripts.adsorption.reico_chemical_environments import chemical_environment, stratum_summary
from scripts.adsorption.reico_dataset_audit import load, overlaps, reserved_geometries
from scripts.adsorption.reico_environment_audit import (
    calibrate, coverage_summary, describe, frame_scores, nearest, read_geometry, stack, train_inventory,
)
from scripts.adsorption.reico_selection import frame_distance
from scripts.artifact_io import (
    sha256_file, sha256_json, source_file_manifest, source_file_manifest_valid, write_json,
)


class CachedSOAP:
    def __init__(self, features: int):
        self.features = features

    def get_number_of_features(self):
        return self.features

    def create(self, *args, **kwargs):
        raise ValueError("missing cache: this audit never recomputes SOAP")


def composition_soap(records: list[dict], selected_ids: set[str], quantile: float) -> tuple[dict, list[dict]]:
    if any(r.get("partition") != "train" for r in records):
        raise ValueError("SOAP stratification accepts training records only")
    reports, scores = {}, []
    for composition in sorted({r["composition"] for r in records}):
        subset = [r for r in records if r["composition"] == composition]
        references = stack([r for r in subset if r["sample_id"] in selected_ids])
        pool = stack(subset)
        thresholds, sensitivity = calibrate(references, quantile)
        distances = nearest(pool, references)
        current = frame_scores(subset, pool, distances, thresholds)
        scores.extend(current)
        reports[composition] = {"pool_frames": len(subset), "pool_families": len({r["family_id"] for r in subset}),
                                "selected_frames": sum(r["sample_id"] in selected_ids for r in subset),
                                "thresholds": thresholds, "quantile_sensitivity": sensitivity,
                                "coverage": coverage_summary(pool, distances, thresholds),
                                "SOAP_gap_frames": sum(r["exceeds_internal_threshold"] for r in current)}
    return reports, scores


def load_training(prior: Path, train: list, config: dict, output: Path) -> tuple[list, dict, list, dict]:
    old = load(prior / "coverage.json")
    cache = prior / "descriptor_cache" / sha256_json(old["descriptor"])
    soap = CachedSOAP(old["descriptor_features"])
    rules = yaml.safe_load(Path(config["analysis_rules"]).read_text(encoding="utf-8"))["connectivity"]
    records, atoms_by_id, chemistry, caches = [], {}, [], []
    for index, row in enumerate(train):
        atoms = read_geometry(row)
        if atoms[45:].get_chemical_formula() != row["composition"]:
            raise ValueError(f"composition metadata differs from geometry: {row['sample_id']}")
        path = cache / (row["structure_sha256"] + ".npz")
        if not path.is_file():
            raise ValueError(f"missing descriptor cache: {row['sample_id']}")
        descriptor = describe(row, atoms, soap, cache, old["descriptor"]["near_Fe_A"])
        descriptor["partition"] = row["partition"]
        if not np.allclose(np.linalg.norm(descriptor["vectors"], axis=1), 1., rtol=0, atol=1e-10):
            raise ValueError("cached SOAP not normalized")
        records.append(descriptor)
        atoms_by_id[row["sample_id"]] = atoms
        chemistry.append({**row, **chemical_environment(atoms, rules)})
        caches.append({"sample_id": row["sample_id"], "sha256": sha256_file(path)})
        if (index+1) % 200 == 0:
            write_json(output / "run_status.json", {"status": "RUNNING", "phase": "CACHE_AND_CHEMISTRY", "frames": index+1})
            print(f"cached descriptors/geometry {index+1}/{len(train)}", flush=True)
    return records, atoms_by_id, chemistry, {"cache_binding": old["descriptor"], "files": caches}


def summarize_chemistry(chemistry: list, scores: list, selected_ids: set, atoms: dict, config: dict) -> tuple[dict, list]:
    score_map = {r["sample_id"]: r for r in scores}
    initials = {}
    for row in chemistry:
        if row["step"] == 0:
            initials[row["family_id"]] = row
    if len(initials) != len({r["family_id"] for r in chemistry}):
        raise ValueError("missing original step0 for chemical-event comparison")
    for row in chemistry:
        row.update(score_map[row["sample_id"]])
        change = connectivity_change(len(atoms[row["sample_id"]])-45,
                                     initials[row["family_id"]]["adsorbate_edges_local_0based"],
                                     row["adsorbate_edges_local_0based"])
        row["event_relative_to_step0"] = change["chemical_event"]
    reports, candidates = {}, []
    for composition in sorted({r["composition"] for r in chemistry}):
        subset = [r for r in chemistry if r["composition"] == composition]
        reports[composition] = {key: stratum_summary(subset, selected_ids, key) for key in
                                ("graph_signature", "coordination_signature", "joint_signature")}
        reports[composition]["events_pool"] = dict(Counter(r["event_relative_to_step0"] for r in subset))
        reports[composition]["events_selected"] = dict(Counter(r["event_relative_to_step0"] for r in subset if r["sample_id"] in selected_ids))
        lookup = {r["sample_id"]: r for r in subset}
        selected_atoms = [atoms[r["sample_id"]] for r in subset if r["sample_id"] in selected_ids]
        for group in reports[composition]["joint_signature"]["strata"]:
            if group["selected_frames"]:
                continue
            row = lookup[group["representative_id"]]
            distance = min(frame_distance(atoms[row["sample_id"]], other) for other in selected_atoms)
            candidates.append({"sample_id": row["sample_id"], "family_id": row["family_id"], "composition": composition,
                               "structure_path": row["structure_path"], "structure_sha256": row["structure_sha256"],
                               "missing_joint_stratum": group, "novelty_ratio": row["novelty_ratio"],
                               "nearest_selected_RMSD_A": distance,
                               "within_original_RMSD_tolerance": distance < config["geometry_duplicate_A"],
                               "reserved_geometry_check": "NOT_CHECKED_NOT_DFT_READY",
                               "action": "DIAGNOSTIC_REPRESENTATIVE_ONLY_NO_DFT_OR_SELECTION_CHANGE"})
    return reports, candidates


def cutoff_sensitivity(train: list, atoms: dict, selected_ids: set, config: dict) -> dict:
    rules = yaml.safe_load(Path(config["analysis_rules"]).read_text(encoding="utf-8"))["connectivity"]
    report = {}
    for scale in config["diagnostic_radius_scales"]:
        rows = [{"sample_id": r["sample_id"], "family_id": r["family_id"], "composition": r["composition"],
                 "novelty_ratio": 0., **chemical_environment(atoms[r["sample_id"]], rules, scale=scale)} for r in train]
        report[str(scale)] = {}
        for composition in sorted({r["composition"] for r in rows}):
            subset = [r for r in rows if r["composition"] == composition]
            report[str(scale)][composition] = {key: {k: v for k, v in stratum_summary(subset, selected_ids, key).items() if k != "strata"}
                                              for key in ("graph_signature", "coordination_signature", "joint_signature")}
    return report


def inspect_priority_candidates(candidates: list, atoms: dict, prior_config: dict, inventory: dict, config: dict) -> list:
    prior_path = Path(prior_config["prior_manifest"]).resolve()
    reserved = reserved_geometries(inventory, load(prior_path), prior_path.parent, prior_config.get("reserved_geometry_catalogs", []))
    priority = []
    for composition in sorted({r["composition"] for r in candidates}):
        subset = sorted((r for r in candidates if r["composition"] == composition),
                        key=lambda r: (-r["missing_joint_stratum"]["pool_families"],
                                       -r["missing_joint_stratum"]["pool_frames"], -r["novelty_ratio"], r["sample_id"]))
        chosen_families = set()
        for row in subset:
            if row["family_id"] in chosen_families:
                continue
            conflicts = overlaps(atoms[row["sample_id"]], reserved, config["reserved_geometry_isolation_A"])
            priority.append({**row, "reserved_geometry_check": "OVERLAP" if conflicts else "NO_OVERLAP",
                             "reserved_geometry_overlaps": conflicts})
            chosen_families.add(row["family_id"])
            if len(chosen_families) >= config["priority_examples_per_composition"]:
                break
    return priority


def run(config_path: Path, output: Path) -> dict:
    config = load(config_path)
    prior = Path(config["prior_audit"])
    summary = load(prior / "audit_summary.json")
    if not source_file_manifest_valid(summary):
        raise ValueError("prior audit source binding is stale")
    if output.exists() and (output / "summary.json").exists():
        raise ValueError("completed audit already exists; choose a new directory")
    output.mkdir(exist_ok=True, parents=True)
    binding = {"config_sha256": sha256_file(config_path), "prior_audit_sha256": sha256_file(prior/"audit_summary.json")}
    if (output / "input_binding.json").exists() and load(output/"input_binding.json") != binding:
        raise ValueError("incomplete output belongs to different inputs")
    write_json(output / "input_binding.json", binding)
    inventory = load(Path(summary["config"]["inventory"]))
    selection_path = Path(summary["config"]["selection"])
    train, selected = train_inventory(inventory, load(selection_path))
    selected_ids = {r["sample_id"] for r in selected}
    records, atoms, chemistry, cache = load_training(prior, train, config, output)
    soap, scores = composition_soap(records, selected_ids, config["leave_family_out_quantile"])
    chemical, candidates = summarize_chemistry(chemistry, scores, selected_ids, atoms, config)
    sensitivity = cutoff_sensitivity(train, atoms, selected_ids, config)
    priority = inspect_priority_candidates(candidates, atoms, summary["config"], inventory, config)
    write_json(output / "composition_soap.json", soap)
    write_json(output / "chemical_strata.json", chemical)
    write_json(output / "frame_environments.json", {"frames": chemistry})
    write_json(output / "candidate_catalog.json", {"diagnostic_representatives": candidates, "priority_examples": priority})
    write_json(output / "cutoff_sensitivity.json", sensitivity)
    write_json(output / "cache_inventory.json", cache)
    if sha256_file(selection_path) != next(r["sha256"] for r in summary["source_files"] if Path(r["path"]) == selection_path.resolve()):
        raise ValueError("original selection changed during analysis")
    result = {"status": "AUDIT_COMPLETE", "completed_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "TRAIN_GEOMETRY_AND_CACHED_SOAP_ONLY", "training_frames": len(train),
              "selected_training_frames": len(selected), "composition_SOAP": soap,
              "chemical_strata": {comp: {key: {k:v for k,v in value.items() if k != "strata"} if "signature" in key else value
                                         for key,value in groups.items()} for comp,groups in chemical.items()},
              "diagnostic_representatives": len(candidates), "priority_examples": len(priority),
              "selected_list_changed": False, "reserved_labels_or_model_errors_used": False,
              "new_DFT_ML_or_training": False, "force_coverage_reviewed": False,
              "source_files": source_file_manifest([config_path, prior/"audit_summary.json", prior/"coverage.json", selection_path,
                                                    Path(summary["config"]["inventory"]), Path(config["analysis_rules"]), Path(__file__),
                                                    Path("scripts/adsorption/reico_chemical_environments.py"),
                                                    Path("scripts/adsmind_lite/relaxed_analysis.py")])}
    write_json(output / "summary.json", result)
    write_json(output / "run_status.json", {"status": "AUDIT_COMPLETE"})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.config, args.output)
    except Exception as error:
        args.output.mkdir(exist_ok=True, parents=True)
        write_json(args.output / ("failure_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".json"),
                   {"error": str(error), "type": type(error).__name__})
        raise
    print(json.dumps({k: result[k] for k in ("status", "training_frames", "diagnostic_representatives", "priority_examples")}))


if __name__ == "__main__":
    main()
