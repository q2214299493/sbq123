"""Review-only reduction of 189 gaps; never construct or execute calculations."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

from archive.fe110_combined_force_package_20261023.prepare import isolate
from archive.fe110_joint_coverage_20261023.prioritize import records
from archive.fe110_joint_update_20261024.run import checked_cache
from archive.fe110_targeted_shortlist_20261025.analyze import geometry, scope
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.adsorption.reico_environment_audit import nearest, stack
from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, write_json_exclusive,
)


def complete_link_groups(items, distance, cutoff=1.0):
    """Deterministic greedy grouping with a bounded diameter; no chaining."""
    if cutoff <= 0:
        raise ValueError("positive cutoff required")
    groups = []
    for item in sorted(items, key=lambda x: x["sample_id"]):
        if item.get("partition") != "train":
            raise ValueError("only training geometries may enter grouping")
        choices = []
        for index, group in enumerate(groups):
            if any((item["composition"], item["graph_signature"]) !=
                   (other["composition"], other["graph_signature"]) for other in group):
                continue
            diameter = max(distance(item, other) for other in group)
            if diameter <= cutoff:
                choices.append((diameter, index))
        if choices:
            groups[min(choices)[1]].append(item)
        else:
            groups.append([item])
    return groups


def choose(group, distance):
    persistent = [r for r in group if r["robust_missing_frames_all_scales"] > 0]
    connected = group[0]["adsorbate_component_count"] == 1
    if connected and persistent:
        chosen = min(persistent, key=lambda r: (-r["novelty_ratio"], r["sample_id"]))
        return chosen, "ROUND1_CONNECTED_PERSISTENT"
    if any(r["novelty_ratio"] > 1 + 1e-9 for r in group):
        chosen = min(group, key=lambda r: (-r["novelty_ratio"], r["sample_id"]))
        return chosen, "RESERVE_SOAP_OUTLIER"
    chosen = min(group, key=lambda r: (
        max(distance(r, x) for x in group), r["sample_id"]))
    return chosen, "DEFER_NO_FORCE_ERROR_EVIDENCE"


def eligible_items(missing, pool, scores, selected_ids, training):
    train_ids = {r["sample_id"] for r in training}
    train_hashes = {r["structure_sha256"] for r in training}
    items, quarantined = [], []
    for gap in missing:
        sid = gap["representative_id"]
        row = {**pool[sid], **scores[sid], **gap, "sample_id": sid}
        if row["partition"] != "train" or row["geometry_guard_failures"]:
            raise ValueError("invalid source partition or geometry guards")
        if gap["quarantined_selected_input_ids"]:
            quarantined.append(gap)
            continue
        if sid in selected_ids | train_ids or row["structure_sha256"] in train_hashes:
            raise ValueError("proposed new label already selected or labelled")
        items.append(row)
    if len(items) != 187 or len(quarantined) != 2:
        raise ValueError("quarantine boundary changed")
    return items, quarantined


def distance_function(items, cache, thresholds):
    descriptors = {r["sample_id"]: stack([r]) for r in records(items, cache)}
    pair_values = {}

    def distance(a, b):
        if a["sample_id"] == b["sample_id"]:
            return 0.0
        key = tuple(sorted((a["sample_id"], b["sample_id"])))
        if key not in pair_values:
            da, db = descriptors[key[0]], descriptors[key[1]]
            value = max(float(np.max(v)) / thresholds[a["composition"]][role]
                        for query, reference in [(da, db), (db, da)]
                        for role, v in nearest(query, reference).items())
            if not np.isfinite(value) or value < -1e-10:
                raise ValueError("nonfinite or negative descriptor distance")
            pair_values[key] = max(0.0, value)
        return pair_values[key]

    return distance, pair_values


def run(root: Path, output: Path):
    if output.exists():
        raise FileExistsError("use a fresh output directory; preserve previous evidence")
    config_path, config, paths = scope(root)
    summary = load_json_object(paths["joint_summary"])
    training = load_json_object(paths["training"])["frames"]
    pool = {r["sample_id"]: r for r in load_json_object(paths["pool"])["frames"]}
    scores = {r["sample_id"]: r for r in load_json_object(paths["soap_scores"])["frames"]}
    missing = load_json_object(paths["missing_groups"])["groups"]
    if len(missing) != 189 or len(training) != 485:
        raise ValueError("source checkpoint changed")
    pilot = paths["joint_summary"].parent.parent
    inventory_path = pilot / "joint_coverage_20261023_v3/descriptor_inventory.json"
    selection_path = pilot / "sampling93_v1/selection/selected_frames.json"
    old_shortlist_path = pilot / "targeted_shortlist_20261025_v1/shortlist_local_only.json"
    selected_ids = {r["sample_id"] for r in load_json_object(selection_path)["selected"]}
    items, quarantined = eligible_items(missing, pool, scores, selected_ids, training)
    cache, cache_paths = checked_cache(items, load_json_object(inventory_path))
    thresholds = {c: v["fixed_thresholds"] for c, v in
                  summary["SOAP_with_fixed_prior_thresholds"].items()}
    distance, pair_values = distance_function(items, cache, thresholds)
    clusters, assignment, proposed, reserves = [], [], [], []
    for index, group in enumerate(complete_link_groups(items, distance), 1):
        candidate, action = choose(group, distance)
        diameter = max(distance(a, b) for a in group for b in group)
        if diameter > 1 + 1e-12:
            raise ValueError("cluster chaining exceeded fixed threshold")
        cid = f"cluster_{index:03d}"
        row = {"cluster_id": cid, "composition": candidate["composition"],
            "representative_id": candidate["sample_id"], "action": action,
            "joint_type_count": len(group), "pool_frames": sum(r["pool_frames"] for r in group),
            "graph_signature": candidate["graph_signature"],
            "adsorbate_component_count": candidate["adsorbate_component_count"],
            "maximum_mutual_SOAP_ratio": diameter,
            "member_type_representatives": [r["sample_id"] for r in group]}
        clusters.append(row)
        for member in group:
            assignment.append({"composition": member["composition"],
                "joint_signature": member["joint_signature"], "cluster_id": cid,
                "action": action, "original_representative_id": member["sample_id"],
                "candidate_representative_id": candidate["sample_id"],
                "mutual_SOAP_ratio_to_representative": distance(member, candidate),
                "sample_ids": member["sample_ids"]})
        if action == "DEFER_NO_FORCE_ERROR_EVIDENCE":
            continue
        target = proposed if action == "ROUND1_CONNECTED_PERSISTENT" else reserves
        target.append({**candidate, "cluster_id": cid, "proposed_action": action,
            "DFT_force": "UNKNOWN", "electronic_convergence": "NOT_LABELLED",
            "magnetic_grade": "NOT_LABELLED_NO_GRADE_ASSIGNED",
            "is_execution_request": False})
    for gap in quarantined:
        assignment.append({**gap, "action": "KEEP_EXISTING_QUARANTINE_REVIEW_ONLY"})
    if len(assignment) != 189:
        raise ValueError("lost missing-type disposition")
    old = load_json_object(old_shortlist_path)
    optimization = [r for r in old["candidates"] if r["sample_id"] in
                    {"family_0099_step020", "family_0023_step020"}]
    if len(optimization) != 2:
        raise ValueError("reviewed optimization sources missing")
    rules = yaml.safe_load(paths["rules"].read_text(encoding="utf-8"))["connectivity"]
    check_rows, checks = [], []
    for row in proposed + reserves + optimization:
        result = geometry(row, rules)
        check_rows.append({**row, "symbols": result["symbols"], "split": "train"})
        checks.append({"sample_id": row["sample_id"], "structure_path": row["structure_path"],
            "structure_sha256": row["structure_sha256"], **result})
    coverage = load_json_object(paths["coverage_config"])
    prior_path = root / coverage["prior_manifest"]
    reserved = reserved_geometries(load_json_object(root / coverage["inventory"]),
        load_json_object(prior_path), prior_path.parent, coverage["reserved_geometry_catalogs"])
    slab_path = root / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    kept, isolation = isolate(check_rows, root, reserved, read_poscar(slab_path), .20)
    if len(kept) != len(check_rows) or isolation["geometry_conflicts"]:
        raise ValueError("reserved geometry isolation failed")
    if any(sha256_file(paths[k]) != config["inputs"][k]["sha256"]
           for k in ("training", "frozen_manifest")):
        raise ValueError("original training sources changed")
    output.mkdir(parents=True)
    source_paths = [Path(__file__), config_path, *paths.values(), inventory_path,
        selection_path, old_shortlist_path, slab_path,
        root / "archive/fe110_targeted_shortlist_20261025/analyze.py",
        root / "archive/fe110_joint_update_20261024/run.py",
        root / "archive/fe110_joint_coverage_20261023/prioritize.py",
        root / "archive/fe110_combined_force_package_20261023/prepare.py",
        root / "scripts/adsorption/reico_environment_audit.py", *cache_paths]
    result = {"input_missing_types": 189, "quarantine_only_types": 2,
        "unselected_types": 187, "environment_clusters": len(clusters),
        "cluster_actions": dict(Counter(r["action"] for r in clusters)),
        "round1_new_single_points": len(proposed), "reserve_single_points": len(reserves),
        "round1_single_points_by_composition": dict(Counter(r["composition"] for r in proposed)),
        "optimization_source_proposals": len(optimization),
        "round1_joint_types_in_approximate_clusters": sum(r["joint_type_count"] for r in clusters
            if r["action"] == "ROUND1_CONNECTED_PERSISTENT"),
        "method": "same composition and exact distance graph;greedy complete-link;maximum symmetric per-element nearest SOAP distance / unchanged internal threshold <=1",
        "selection_priority": "connected and persistent across3radius scales first;SOAP-only outliers reserve;other groups deferred,not claimed covered",
        "new_force_bins_known": False, "DFT_force_error_used": False,
        "geometry_approximation_is_force_equivalence": False,
        "clusters_are_mandatory_DFT_tasks": False,
        "minimum_or_sufficient_label_count_proven": False,
        "all189_discrete_types_covered_by_round1": False,
        "reserved_energies_or_forces_used": False,
        "frozen_training_or_magnetic_grades_changed": False,
        "paused05_07_resumed": False, "new_DFT_GPU_training_submission": False,
        "source_files": source_file_manifest(source_paths)}
    for name, obj in {"summary.json": result, "clusters.json": {"clusters": clusters},
        "all189_dispositions.json": {"types": assignment},
        "proposals.json": {"round1_new_single_points": proposed,
            "reserve_single_points": reserves, "optimization_sources_already_labelled": optimization,
            "quarantines_unchanged": quarantined, "execution_authorized": False},
        "geometry.json": {"candidates": checks}, "isolation.json": isolation,
        "pair_distances.json": {"pairs": [{"a": a, "b": b, "ratio": v}
            for (a, b), v in sorted(pair_values.items())]}}.items():
        write_json_exclusive(output / name, obj)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.evidence_root.resolve(), arguments.output.resolve())
