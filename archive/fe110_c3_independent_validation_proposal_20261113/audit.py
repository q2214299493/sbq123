"""Read existing sources for a proposal; never write geometries or run calculations."""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
import yaml
from ase import Atoms

from archive.fe110_10b_lowforce_20261023.legacy_helpers import pose_distance, pose_variants
from archive.fe110_c3_targeted_relaxation_20261023.prepare import timing_reference
from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_isomers import (
    review, surface_pose_symmetries, transfer_pose,
)
from scripts.adsorption.reico_chemical_environments import canonical_graph, connectivity_edges
from scripts.artifact_io import sha256_file, source_file_manifest, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUT = BASE / "c3_independent_validation_proposal_20261113_v1"
PACKAGE = BASE / "combined_force_package_20261113_v1"
CARE = ROOT / "calculations/fe110_care8_isomers_20260716"
PRIOR = BASE / "independent_nearstable_inventory_20261113_v1"
TARGET_GRAPH = "C,C,C,H,H,O|010001001110000"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def graph(pose, rules):
    symbols = expanded_symbols(pose)
    indices = [i for i, symbol in enumerate(symbols) if symbol != "Fe"]
    ads_symbols = [symbols[i] for i in indices]
    atoms = Atoms(symbols=symbols, scaled_positions=pose.frac, cell=pose.cell, pbc=True)
    edges = connectivity_edges(atoms, indices, rules["covalent_radius_scale"],
                               rules["minimum_bond_distance_angstrom"])
    counts = Counter("-".join(sorted((ads_symbols[a], ads_symbols[b]))) for a, b in edges)
    return {"canonical_signature": canonical_graph(ads_symbols, edges),
            "symbols_local": ads_symbols, "edges_local_0based": edges,
            "geometric_bond_counts": dict(counts),
            "method": "project covalent-radius contacts; not electronic bond orders"}


def references(manifest, slab):
    operations = surface_pose_symmetries(slab)
    result = []
    for split, rows in manifest["splits"].items():
        for row in rows:
            if row["composition"] != "C3H2O":
                continue
            path = PACKAGE / row["structure_path"]
            if sha256_file(path) != row["structure_sha256"]:
                raise ValueError("frozen reference geometry hash mismatch")
            pose = read_poscar(path)
            if not np.allclose(pose.cell, slab.cell, atol=1e-6, rtol=0):
                raise ValueError("reference lattice incompatible with pose RMSD audit")
            result.append({"split": split, "id": row["sample_id"],
                           "family_id": row.get("family_id"),
                           "path": path, "variants": pose_variants(pose, operations)})
    if len(operations) != 36 or Counter(r["split"] for r in result) != {
        "train": 150, "development": 9, "heldout": 4,
    }:
        raise ValueError("unexpected frozen C3 scope; review before extending audit")
    return result, operations


def isolation(pose, refs):
    result = {}
    for split in ("train", "development", "heldout"):
        distance, name = min((pose_distance(pose, r["variants"]), r["id"])
                             for r in refs if r["split"] == split)
        result[split] = {"nearest_sample_id": name, "adsorbate_RMSD_A": distance,
                         "within0p20A": distance <= .20}
    return result


def validate_bound_inputs(before, prior, care, slab_path):
    if before != load(OUT / "request_context.json")["frozen_hashes_before"]:
        raise ValueError("frozen packages changed since this request began")
    if sha256_file(PRIOR / "source_plan.json") != load(PRIOR / "final_validation.json")["source_plan_sha256"]:
        raise ValueError("prior source plan binding changed")
    if prior["C3_nontraining_trajectory_scope"]["intact_nearstable_usable_sources_verified"] != 0:
        raise ValueError("prior gap changed; do not reuse this proposal")
    if sha256_file(slab_path) != care["source_slab_sha256"]:
        raise ValueError("CARE transfer slab changed")


def verify_target_references(manifest, rules):
    if any(r["composition"] == "C3H2O" for r in manifest["quarantined_observed_heldout"]):
        raise ValueError("additional quarantined C3 geometries need isolation review")
    target24 = [r for r in manifest["splits"]["train"] if str(r.get("source_job_id")) == "9924387"]
    if len(target24) != 24:
        raise ValueError("new536 target reference changed")
    graphs = Counter(graph(read_poscar(PACKAGE / r["structure_path"]), rules)["canonical_signature"] for r in target24)
    if graphs != {TARGET_GRAPH: 24}:
        raise ValueError("0099 target graph differs from proposal")
    return graphs


def main():
    before = frozen_hashes()
    manifest = load(PACKAGE / "training_manifest.json")
    old_manifest = load(BASE / "combined_force_package_20261027_v3/training_manifest.json")
    prior = load(PRIOR / "source_plan.json")
    care = load(CARE / "candidate_manifest.json")
    slab_path = ROOT / care["source_slab"]
    validate_bound_inputs(before, prior, care, slab_path)
    slab = read_poscar(slab_path)
    refs, operations = references(manifest, slab)
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))["connectivity"]
    seed = next(r for r in care["candidates"] if r["name"].startswith("05_"))
    upstream = Path(seed["source_poscar"]).parents[4]
    csv_path = upstream / "fe48_adsorption_candidate_manifest.csv"
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        cache = list(csv.DictReader(handle))
    sources = [Path(__file__), OUT / "request_context.json", CARE / "candidate_manifest.json",
               PRIOR / "source_plan.json", PRIOR / "final_validation.json",
               PRIOR / "registry_source_evidence.json", PRIOR / "physical_inventory.json",
               rules_path, slab_path, csv_path, upstream / "README.md",
               ROOT / "configs/fe110_reico_pilot/geometry_v1.json",
               ROOT / "scripts/adsorption/reico_random_geometry.py",
               ROOT / "scripts/adsorption/build_fe110_care_isomers.py",
               ROOT / "scripts/adsorption/reico_chemical_environments.py",
               ROOT / "archive/fe110_10b_lowforce_20261023/legacy_helpers.py"]
    candidates, poses = [], {}
    selected = [("05_", k) for k in range(3)] + [("07_", 2), ("08_", 0)]
    for prefix, config in selected:
        record = next(r for r in care["candidates"] if r["name"].startswith(prefix))
        raw_path = Path(record["source_poscar"]).parent.parent / f"config_{config}" / "POSCAR"
        xyz = raw_path.with_name("structure.extxyz")
        if config == int(record["care_config_id"]) and sha256_file(raw_path) != record["source_poscar_sha256"]:
            raise ValueError("canonical upstream pose changed")
        csv_row = next(r for r in cache if r["code"] == record["care_code"] and int(r["care_config_id"]) == config)
        raw = read_poscar(raw_path)
        mapped, source_order = transfer_pose(raw, slab)  # In memory only; no POSCAR written.
        mapped_review = review(raw, mapped, source_order)
        if graph(raw, rules)["canonical_signature"] != graph(mapped, rules)["canonical_signature"]:
            raise ValueError("virtual transfer changed molecular graph")
        with xyz.open(encoding="utf-8") as handle:
            count, properties = handle.readline().strip(), handle.readline().strip()
        if "forces:" in properties or "energy=" in properties:
            raise ValueError("new source label metadata requires explicit review")
        candidate_id = record["name"].replace(f"cfg{record['care_config_id']}", f"cfg{config}")
        pose = mapped
        existing_path = None
        if config == int(record["care_config_id"]):
            existing_path = CARE / "revised" / record["name"] / "POSCAR"
            original_path = CARE / record["name"] / "POSCAR"
            original = read_poscar(original_path)
            pose = read_poscar(existing_path)
            existing_review = review(original, pose, list(range(45, 51)))
            sources.extend([original_path, existing_path])
        else:
            existing_review = None
        signature = graph(pose, rules)
        if prefix == "05_" and signature["canonical_signature"] != TARGET_GRAPH:
            raise ValueError("target seed is not the 0099 nearstable training graph")
        if prefix == "05_":
            motif = "C2_short_bridge_C3_top_O_hollow" if config in (0, 1) else "C2_long_bridge_C3_top_O_long_bridge"
            role = "same_motif_backup_with_low_height_warning" if config == 0 else "primary_target_proposal_seed"
        elif prefix == "07_":
            motif, role = "separate_POVFFVOJ_isomer", "separate_isomer_reserve_not_target_replacement"
        else:
            motif, role = "historical_XXNRTDXE", "existing_DFT_negative_controls_no_new_budget"
        candidates.append({
            "candidate_id": candidate_id, "composition": "C3H2O", "exact_smiles": record["exact_smiles"],
            "care_code": record["care_code"], "care_level": record["care_level"],
            "config_id": config, "upstream_source": source_file_manifest([raw_path, xyz]),
            "source_export_atom_count": int(count), "export_property_line": properties,
            "export_geometry_gate_only": csv_row["geometry_gate"],
            "stored_DFT_forces_or_energy_in_export": False,
            "Fe48_source_graph": graph(raw, rules), "virtual_Fe45_transfer_review": mapped_review,
            "virtual_transfer_RMSD_to_frozen_partitions": isolation(mapped, refs),
            "proposed_pose_file": str(existing_path) if existing_path else None,
            "proposed_pose_kind": "existing_revised_Fe45" if existing_path else "in_memory_Fe45_transfer_audit_only",
            "existing_revised_geometry_review": existing_review,
            "graph": signature, "proposed_pose_RMSD_to_frozen_partitions": isolation(pose, refs),
            "motif_group_provisional_geometric": motif, "proposed_role": role,
            "same_coordinate_compatible_DFT_label": "none verified in audited sources; not an exhaustive server-wide absence claim",
            "scientific_acceptance": False, "generated_structure_written": False,
        })
        poses[candidate_id] = pose
        sources.extend([raw_path, xyz])
    q = manifest["quarantined_observed_heldout"]
    target24_graphs = verify_target_references(manifest, rules)
    pair_distances = []
    target_ids = [c["candidate_id"] for c in candidates if c["candidate_id"].startswith("05_")]
    for i, first in enumerate(target_ids):
        for second in target_ids[i + 1:]:
            pair_distances.append({"first": first, "second": second,
                                   "adsorbate_RMSD_A": pose_distance(poses[first], pose_variants(poses[second], operations)),
                                   "RMSD_does_not_prove_distinct_binding_mode": True})
    db = ROOT / "data/project_registry.sqlite3"
    db_before = sha256_file(db)
    query = ("SELECT scheduler_job_id,remote_directory FROM jobs WHERE "
             "remote_directory LIKE '%c3_targeted_relaxation_20261023%' OR "
             "remote_directory LIKE '%C3H2O_POVFFVOJ%' OR remote_directory LIKE '%FLJNAOY%'")
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        registry_matches = [dict(zip(("scheduler_job_id", "remote_directory"), r, strict=True)) for r in conn.execute(query)]
    if sha256_file(db) != db_before:
        raise ValueError("registry changed during read-only snapshot")
    old_plan_path = ROOT / "calculations/fe110_c3_targeted_relaxation_20261023/screen80_v2/plan.json"
    old_plan = load(old_plan_path)
    timings = timing_reference(ROOT)
    if timings != old_plan["timing_references"]:
        raise ValueError("native timing evidence no longer matches old plan")
    sources.extend([old_plan_path, ROOT / "archive/fe110_c3_targeted_relaxation_20261023/prepare.py"])
    sources.extend(ROOT / "calculations/fe110_c3_existing_recovery_20261023/collection_v1" / r["job_id"] / "OUTCAR" for r in timings)
    after = frozen_hashes()
    if before != after:
        raise ValueError("frozen packages changed during audit")
    evidence = {
        "document_kind": "C3_INDEPENDENT_VALIDATION_SUPPLEMENT_PROPOSAL_EVIDENCE",
        "status": "PROPOSAL_ONLY_BLOCKED_THIRD_DISTINCT_MOTIF",
        "frozen_hashes_before": before, "frozen_hashes_after": after,
        "split_counts": {"512": {k: len(v) for k, v in old_manifest["splits"].items()},
                         "536": {k: len(v) for k, v in manifest["splits"].items()},
                         "quarantined_16_compositions": dict(Counter(r["composition"] for r in q))},
        "C3_reference_counts": dict(Counter(r["split"] for r in refs)),
        "reference_structure_files": source_file_manifest([r["path"] for r in refs]),
        "surface_symmetries": len(operations), "permutations_per_symmetry": 12,
        "geometric_duplicate_threshold_A": .20, "connectivity_rules": rules,
        "C3_gap_from_hash_bound_prior_source_plan": prior["C3_nontraining_trajectory_scope"],
        "excluded_training_lineage": prior["excluded_training_lineage"],
        "new536_24_target_graphs": dict(target24_graphs), "candidates": candidates,
        "target_pair_distances": pair_distances,
        "independent_target_binding_mode_count_supported": 2,
        "third_target_mode": "Needs confirmation: no verified third non-equivalent target-graph motif",
        "source_family_basis": "CARE exact graph/code/config source versus random REICO slab/count/seed source; not a claim of blind model-selection independence",
        "registry_snapshot": {"read_only": True, "database_sha256": db_before,
                              "query": query, "matches": registry_matches,
                              "does_not_prove_absence_of_unregistered_jobs": True},
        "historical_05_07_input_plan": {"sha256": sha256_file(old_plan_path),
                                         "submitted_in_plan": old_plan["submitted"],
                                         "reuse_does_not_grant_new_execution_authority": True},
        "raw_OUTCAR_verified_timing_references": timings,
        "conditional_DFT_budget": {
            "ready_or_submitted_jobs_now": 0, "approved_compute_budget_now": 0,
            "condition": "three reviewed non-equivalent target-graph modes, source isolation and fresh explicit execution authority",
            "proposed_screen_relaxations": 3, "cores_per_job": 32, "max_ionic_steps_per_job": 80,
            "max_parallel_jobs": 1, "proposed_wall_time_cap_hours_per_job": 12,
            "proposed_allocated_core_hour_cap": 1152,
            "historical_analogy_core_hour_range": [3 * min(r["allocated_core_hours_estimate"] for r in timings),
                                                    3 * max(r["allocated_core_hours_estimate"] for r in timings)],
            "timing_reference_is_not_completion_guarantee": True,
            "extra_static_single_points": 0, "automatic_retries_or_continuation": False,
            "10_to_20_single_points_alone_close_nearstable_gap": False,
        },
        "new_calculation_inputs_or_structures_written": False,
        "training_model_inference_relaxation_or_DFT_run": False,
        "existing_packages_partitions_or_protocols_modified": False,
        "scientific_acceptance_granted": False,
        "RSI": {"entry_calls": 1, "process_exit_code": load(OUT / "rsi_process_receipt.json")["process_exit_code"],
                "failure": "store and temporary run output overlap; rejected before assistant startup",
                "research_suggestions_or_policy_actions_produced": False, "retried": False},
        "source_files": source_file_manifest(list(dict.fromkeys(sources))),
    }
    write_json_exclusive(OUT / "proposal_evidence.json", evidence)
    print(json.dumps({"status": evidence["status"], "candidates": len(candidates),
                      "reference_C3_geometries": len(refs), "frozen_unchanged": before == after,
                      "historical_three_job_core_hours": evidence["conditional_DFT_budget"]["historical_analogy_core_hour_range"]}))


if __name__ == "__main__":
    main()
