"""Refresh geometric coverage against frozen536, reusing existing evidence only."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

from archive.fe110_joint_coverage_20261023.run import load_training
from scripts.adsorption.reico_joint_coverage import joint_force_table, missing_environment_groups
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .collect import BASE, OUT, ROOT

SIDECAR = BASE / "energy_reaction_sidecar_20261113_v1"
OLD = BASE / "joint_update512_20261027_v1"


def force_maximum(row: dict) -> float:
    forces = np.asarray(row["forces_eV_per_A"], dtype=float)
    fixed = set(row["fixed_atom_indices_0based"])
    movable = [i for i in range(len(forces)) if i not in fixed]
    if forces.ndim != 2 or forces.shape[1] != 3 or not movable or not np.isfinite(forces).all():
        raise ValueError("invalid physical force array")
    return float(np.linalg.norm(forces[movable], axis=1).max())


def label_status(labels: list[dict], protected: bool = False) -> str:
    if protected or any(r.get("partition") in {"development", "heldout", "quarantine", "final_test"} for r in labels):
        return "PROTECTED_NO_TRAINING"
    if not labels:
        return "NO_SAME_COORDINATE_DFT_LABEL_IN_AUDITED_CATALOG"
    if any(r.get("energy_force_evidence_ready_for_review") for r in labels):
        return "EXISTING_E_F_LOCALMAG_REVIEW_CANDIDATE_NOT_NEW_ADMISSION"
    if any(r.get("coordinate_force_match") and r.get("electronic_raw_pass")
           and r.get("compatibility", {}).get("active_PBE_Fe45_sigma0p20_branch_observed") for r in labels):
        return "EXISTING_E_F_MAGNETIC_OR_CELL_REVIEW_REQUIRED"
    return "EXISTING_LABEL_QC_OR_COMPATIBILITY_BLOCKED"


def protected_scope(manifest: dict) -> tuple[set, set]:
    rows = [r for split, values in manifest["splits"].items() if split != "train" for r in values]
    rows.extend(manifest["quarantined_observed_heldout"])
    return ({r["structure_sha256"] for r in rows}, {r["family_id"] for r in rows if r.get("family_id")})


def training_reference(train, old, manifest_path, rules, scales):
    """Reuse unchanged512 and enrich only the 24 already admitted geometries."""
    previous = {r["sample_id"]: r for r in old}
    if len(previous) != 512 or len(train) != 536:
        raise ValueError("unexpected frozen reference counts")
    training = []
    for row in train:
        if row["sample_id"] not in previous:
            continue
        cached = previous[row["sample_id"]]
        for key in ("structure_sha256", "source_OUTCAR_sha256", "forces_eV_per_A", "composition"):
            if cached[key] != row[key]:
                raise ValueError("unchanged512 prefix mismatch: " + key)
        training.append(cached)
    new = [r for r in train if r["sample_id"] not in previous]
    _, enriched, new_files = load_training(new, manifest_path, rules, scales)
    training.extend(enriched)
    if len(training) != 536 or len(new) != 24:
        raise ValueError("unexpected reference extension")
    return training, new_files


def run():
    config_path = ROOT / "configs/fe110_reico_pilot/joint_update512_20261027_v1.json"
    config = load_json_object(config_path)
    paths = {name: ROOT / value["path"] for name, value in config["inputs"].items()}
    for name in ("pool", "manifest", "selection", "analysis_rules"):
        if sha256_file(paths[name]) != config["inputs"][name]["sha256"]:
            raise ValueError("historical source binding changed: " + name)
    manifest_path = BASE / "combined_force_package_20261113_v1/training_manifest.json"
    manifest = load_json_object(manifest_path)
    old = load_json_object(OLD / "training_environments_local_only.json")["frames"]
    rules = yaml.safe_load(paths["analysis_rules"].read_text(encoding="utf-8"))["connectivity"]
    training, new_files = training_reference(manifest["splits"]["train"], old, manifest_path, rules, config["radius_scales"])
    pool = load_json_object(paths["pool"])["frames"]
    scores_path = OLD / "SOAP_frame_scores.json"
    scores = {r["sample_id"]: r for r in load_json_object(scores_path)["frames"]}
    if len(scores) != len(pool) or set(scores) != {r["sample_id"] for r in pool}:
        raise ValueError("historical512 SOAP score scope mismatch")
    pool = [{**r, **scores[r["sample_id"]]} for r in pool]
    selected = {r["sample_id"] for r in load_json_object(paths["selection"])["selected"] if r["partition"] == "train"}
    dimensions, groups = missing_environment_groups(pool, training, selected)
    # Rename legacy helper's historical column names to reflect the actual reference.
    for values in dimensions.values():
        for counts in values.values():
            counts["frozen536_covered"] = counts.pop("current366_covered")
            counts["historical_selected_covered"] = counts.pop("original233_covered")
    labels_path = SIDECAR / "energy_label_sidecar_final_v2.json"
    labels = load_json_object(labels_path)["records"]
    by_hash = defaultdict(list)
    by_id = defaultdict(list)
    bound = set(new_files) | {scores_path}
    for record in labels:
        by_id[record["sample_id"]].append(record)
        p = Path(record["structure_path"])
        if p.is_file():
            by_hash[sha256_file(p)].append(record)
            bound.add(p)
    protected_hashes, protected_families = protected_scope(manifest)
    headers_path = OUT / "local_geometry_headers.json"
    headers = {r["path"]: r for r in load_json_object(headers_path)["records"]}
    bindings = []
    for row in pool:
        header = headers.get(str(Path(row["structure_path"]).resolve()))
        if not header or header.get("sha256") != row["structure_sha256"]:
            raise ValueError("pool geometry hash not present in actual header inventory: " + row["sample_id"])
        matched = by_hash.get(row["structure_sha256"], [])
        protected = row["structure_sha256"] in protected_hashes or row["family_id"] in protected_families
        status = label_status(matched, protected)
        bindings.append({"sample_id": row["sample_id"], "family_id": row["family_id"],
                         "composition": row["composition"], "structure_path": row["structure_path"],
                         "structure_sha256": row["structure_sha256"], "label_status": status,
                         "geometry_binding_method": "EXACT_FILE_SHA256_NOT_ID_ALONE",
                         "physical_labels": [{k: r.get(k) for k in (
                             "sample_id", "pool", "partition", "source_job_id", "physical_label_key",
                             "DFT_ionic_step", "coordinate_force_match", "electronic_raw_pass",
                             "raw_magnetic_grade", "raw_positive_Fe_local_moments", "flags",
                             "energy_force_evidence_ready_for_review")} for r in matched],
                         "same_ID_other_geometry_labels": len(by_id[row["sample_id"]]) - sum(
                             r["sample_id"] == row["sample_id"] for r in matched),
                         "protected_exact_hash_or_family": protected,
                         "symmetry_near_duplicate_check": "NOT_RECOMPUTED;REQUIRED_BEFORE_FUTURE_ADMISSION",
                         "prior_geometry_guard_failures": row["geometry_guard_failures"],
                         "new_training_admission": False})
    indexed = {r["sample_id"]: r for r in bindings}
    for group in groups:
        members = [indexed[name] for name in group["sample_ids"]]
        group["same_coordinate_label_status_counts"] = dict(Counter(r["label_status"] for r in members))
        group["representative_binding"] = indexed[group["representative_id"]]
        group["SOAP_reference"] = "HISTORICAL512_FIXED_THRESHOLDS;NOT_FRESH536_SOAP"
        group["DFT_force_of_missing_frames"] = "SEE_SAME_COORDINATE_BINDINGS;NEVER_IMPUTE_NEIGHBOR_FORCES"
        group["new_DFT_budget"] = "CONDITIONAL_AFTER_COMPATIBILITY_ISOLATION_AND_DEDUP;NOT_ALLOCATED"
        bound.add(Path(indexed[group["representative_id"]]["structure_path"]))
    per_comp = {}
    for comp in sorted({r["composition"] for r in pool}):
        rows = [g for g in groups if g["composition"] == comp]
        per_comp[comp] = {"missing_geometric_joint_types": len(rows),
                          "robust_missing_groups_all_three_scales": sum(g["robust_missing_frames_all_scales"] > 0 for g in rows),
                          "frames_in_missing_types": sum(g["pool_frames"] for g in rows),
                          "label_statuses_in_missing_types": dict(Counter(indexed[s]["label_status"] for g in rows for s in g["sample_ids"]))}
    write_json_exclusive(OUT / "reico_pool_label_bindings_v3.json", {"records": bindings,
                          "status_counts": dict(Counter(r["label_status"] for r in bindings)),
                          "exact_hash_mapping_is_not_complete_symmetry_isolation": True,
                          "source_files": source_file_manifest([labels_path, headers_path, paths["pool"], manifest_path])})
    write_json_exclusive(OUT / "reico536_coverage_v3.json", {
        "status": "READ_ONLY_GEOMETRIC_REFRESH_NO_SOAP_OR_MODEL_EXECUTION", "training_frames": len(training),
        "pool_frames": len(pool), "missing_geometric_joint_types": len(groups),
        "per_composition": per_comp, "dimensions": dimensions, "groups": groups,
        "force_table": joint_force_table(training, config["force_edges_eV_A"]),
        "SOAP_recomputed": False, "historical_SOAP_ratios_not_new536_force_uncertainty": True,
        "revision": "v3 refreshes source binding after extracting protected-scope helper;uses actual512 SOAP scores;v1/v2 superseded",
        "radius_scales": config["radius_scales"], "connectivity_rules": rules,
        "new_DFT_or_training_or_inference": False,
        "source_files": source_file_manifest(sorted(bound | {Path(__file__), manifest_path, labels_path,
                                               headers_path, paths["pool"], config_path,
                                               OLD / "training_environments_local_only.json"}))})
    print({"missing536": len(groups), "per_composition": per_comp}, flush=True)


if __name__ == "__main__":
    run()
