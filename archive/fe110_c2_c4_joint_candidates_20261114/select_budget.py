"""A review-only, family-diverse batch; never write scientific inputs or submit."""
from __future__ import annotations

from collections import Counter
from math import ceil
from pathlib import Path

from archive.fe110_c2_c4_gap_inventory_20261114.network import export_csv
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from .audit import SLAB
from .collect_sources import OUT
from .geometry import distance_metrics, iron_maps, nearest, packed_pose


def choose(records, path_refs, operations, maps, maximum=20):
    candidates = [r for r in records if r["candidate_class"] == "NEW_SP_REVIEW_CANDIDATE"]
    selected, packed, deferred = [], [], []
    while candidates and len(selected) < maximum:
        formulas = {r["composition"] for r in selected}
        candidates.sort(key=lambda r: (bool(r["family_risk_note"]), r["composition"] in formulas,
                                       -r["robust_missing_frames_all_scales"], -r["pool_frames_of_joint_type"],
                                       -(r["historical512_SOAP_ratio"] or 0), r["candidate_id"]))
        row = candidates.pop(0)
        pose = read_poscar(Path(row["source_path"]))
        match = nearest(pose, packed)
        existing = nearest(pose, path_refs)
        reason = rejection_reason(row, selected, match, existing)
        if reason:
            deferred.append({"candidate_id": row["candidate_id"], "reason": reason,
                             "nearest_selected": match, "nearest_existing_path": existing})
            continue
        current = {**row, "rank": len(selected) + 1, "nearest_existing_DFT_path_label": existing,
                   "nearest_earlier_selected": match, "selection_method": "uncovered_target_composition,robust_gap_extent,family_diversity;no_DFT_error_or_new536_inference",
                   "admission_status": "PROPOSAL_ONLY;future_raw_SCF_coordinate_force_magnetism_and_compatibility_QC_required"}
        selected.append(current)
        packed.append({**packed_pose(pose, operations, maps), "id": row["candidate_id"], "source": row["source_path"]})
    return selected, packed, deferred


def rejection_reason(row, selected, match, existing):
    if any(r["family_id"] == row["family_id"] for r in selected):
        return "one_representative_per_trajectory_family_in_first_batch"
    if match["full_RMSD_A"] is not None and match["full_RMSD_A"] < .10:
        return "surface_symmetry_adsorbate_movableFe_near_duplicate_below0p10A"
    if existing["full_RMSD_A"] is not None and existing["full_RMSD_A"] <= 1e-7:
        return "possible_same_coordinate_existing_path_force_label;review_atommap_before_any_new_DFT"
    return None


def budget_rows(selected, statistics):
    result = []
    for row in selected:
        observed = statistics[row["composition"]]
        cap = ceil(2 * observed["p90_seconds"] / 900) / 4
        result.append({"rank": row["rank"], "candidate_id": row["candidate_id"], "composition": row["composition"],
                       "family_id": row["family_id"], "source_path": row["source_path"], "structure_sha256": row["source_sha256"],
                       "proposed_new_single_points": 1, "reference_MPI_ranks": 32,
                       "median_reference_core_hour_estimate": observed["median_seconds"] * 32 / 3600,
                       "per_composition_p90_core_hour_reference": observed["p90_seconds"] * 32 / 3600,
                       "proposed_walltime_cap_hours": cap, "proposed_allocated_corehour_cap": 32 * cap,
                       "cap_formula": "2*empirical_composition_p90 rounded upward to0.25hour;proposal only",
                       "nearest_protected_ads_pose_RMSD_A": row["isolation"]["protected"]["minimum_ads_pose_RMSD_A_any_reference"],
                       "nearest_train_full_RMSD_A": row["isolation"]["train536"]["full_RMSD_A"],
                       "nearest_existing_path_full_RMSD_A": row["nearest_existing_DFT_path_label"]["full_RMSD_A"],
                       "largest_C_C_component": row["geometry"]["graph"]["largest_C_C_connected_component"],
                       "adsorbate_components": row["geometry"]["graph"]["adsorbate_components"],
                       "binding_sites": ";".join(f"{s['atom']}#{s['index_1based']}:{s['geometric_site']}:Fe{s['nearest_Fe_index_1based']}@{s['nearest_Fe_A']:.4f}A" for s in row["geometry"]["binding_sites"]),
                       "existing_same_coordinate_label": "not found in audited labels;no neighbor forces imputed",
                       "DFT_residual_force": "UNKNOWN_UNLABELLED;stored_ML_force_not_used_as_DFT_truth",
                       "execution_authorized_or_submitted": False})
    return result


def run():
    audit_path = OUT / "coordinate_site_isolation_audit_v4.json"
    paths_path = OUT / "reaction_path_reuse_audit.json"
    cost_path = OUT / "static_cost_references.json"
    audit = load_json_object(audit_path)
    paths = load_json_object(paths_path)
    slab = read_poscar(SLAB)
    operations = surface_pose_symmetries(slab)
    maps = iron_maps(slab, operations)
    path_rows = paths["newly_bound_existing_first_steps"] + paths["existing_last_step_labels"]
    path_refs = []
    for row in path_rows:
        source = Path(row["structure_path"])
        path_refs.append({**packed_pose(read_poscar(source), operations, maps), "id": row.get("candidate_id", row.get("sample_id")), "source": str(source)})
    selected, packed, deferred = choose(audit["records"], path_refs, operations, maps)
    budget = budget_rows(selected, load_json_object(cost_path)["statistics"])
    scenarios = []
    for size in (10, 15, 20):
        prefix = budget[:size]
        if len(prefix) != size:
            continue
        types = {r["joint_signature"] for r in selected[:size]}
        scenarios.append({"single_points": size, "compositions": dict(Counter(r["composition"] for r in prefix)),
                          "unique_families": len({r["family_id"] for r in prefix}),
                          "conditional_new_default_joint_types_if_every_label_admitted": len(types),
                          "conditional_remaining_default_joint_gaps_of178": 178 - len(types),
                          "sum_median_reference_core_hours": sum(r["median_reference_core_hour_estimate"] for r in prefix),
                          "sum_per_composition_p90_reference_core_hours": sum(r["per_composition_p90_core_hour_reference"] for r in prefix),
                          "proposed_allocated_corehour_cap": sum(r["proposed_allocated_corehour_cap"] for r in prefix),
                          "C4_label_or_independent_C3_nearstable_gap_closed": False,
                          "geometry_coverage_is_not_force_accuracy_or_optimization_speedup": True})
    pairwise = []
    for i, reference in enumerate(packed):
        for j in range(i):
            if reference["key"] == packed[j]["key"]:
                pairwise.append({"first": selected[j]["candidate_id"], "second": selected[i]["candidate_id"],
                                 **distance_metrics(reference["pose"], packed[j])})
    write_json_exclusive(OUT / "single_point_candidates_and_budget_v2.json", {
        "status": "GEOMETRIC_EXPLORATION_RESERVE_NOT_TARGET_COMPLETE_OR_EXECUTION_READY", "selected": selected,
        "budget": budget, "scenarios": scenarios, "deferred": deferred, "selected_same_composition_pairwise_metrics": pairwise,
        "no_preset_carbon_quotas": True, "candidate_selection_not_proven_optimal": True,
        "C4_existing_coordinate_candidates": 0, "C4_required_source": "Needs confirmation;no invented coordinates",
        "new_DFT_training_inference_or_structure_generation": False,
        "source_files": source_file_manifest([Path(__file__), Path(__file__).with_name("geometry.py"), audit_path, paths_path, cost_path, SLAB])})
    export_csv(OUT / "single_point_candidates_and_budget_v2.csv", budget, list(budget[0]) if budget else ["candidate_id"])
    print({"selected": len(selected), "unique_families": len({r["family_id"] for r in selected}),
           "compositions": dict(Counter(r["composition"] for r in selected)), "scenarios": scenarios}, flush=True)


if __name__ == "__main__":
    run()
