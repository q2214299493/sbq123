"""Combine existing geometric and chemical-event sources, without admission."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .collect import BASE, OUT
from .coverage import SIDECAR
from .network import export_csv


def component_sizes(symbols: list[str], edges: list) -> dict:
    """Keep total C, C-C skeleton and C in an organic component distinct."""
    def components(nodes, pairs):
        unseen = set(nodes)
        result = []
        adjacency = {i: set() for i in nodes}
        for a, b in pairs:
            if a in adjacency and b in adjacency:
                adjacency[a].add(b)
                adjacency[b].add(a)
        while unseen:
            reached = set()
            pending = [min(unseen)]
            while pending:
                i = pending.pop()
                if i not in reached:
                    reached.add(i)
                    pending.extend(adjacency[i] - reached)
            unseen -= reached
            result.append(reached)
        return result
    carbon = [i for i, symbol in enumerate(symbols) if symbol == "C"]
    organic = components(range(len(symbols)), edges)
    skeleton = components(carbon, edges)
    return {"total_C": len(carbon), "largest_C_C_connected_component": max(map(len, skeleton), default=0),
            "carbon_counts_per_adsorbate_component": sorted((sum(symbols[i] == "C" for i in group) for group in organic), reverse=True),
            "adsorbate_components": len(organic), "symbols_local": symbols, "edges_local_0based": edges,
            "interpretation": "covalent-radius geometric contacts;not electronic bond order"}


def run():
    coverage_path = OUT / "reico536_coverage_v3.json"
    bindings_path = OUT / "reico_pool_label_bindings_v3.json"
    coverage = load_json_object(coverage_path)
    bindings = {r["sample_id"]: r for r in load_json_object(bindings_path)["records"]}
    pool_path = BASE / "joint_coverage_20261023_v3/pool_environments.json"
    pool = {r["sample_id"]: r for r in load_json_object(pool_path)["frames"]}
    bound = {Path(__file__), coverage_path, bindings_path, pool_path}
    choices = {}
    for composition in coverage["per_composition"]:
        groups = [g for g in coverage["groups"] if g["composition"] == composition
                  and g["robust_missing_frames_all_scales"] > 0
                  and g["representative_binding"]["label_status"] == "NO_SAME_COORDINATE_DFT_LABEL_IN_AUDITED_CATALOG"]
        for group in groups[:(3 if composition == "C3H2O" else 2)]:
            choices[group["representative_id"]] = ("P1", "cutoff-robust joint geometric gap;not established force error")
    for name in ("family_0013_step016", "family_0028_step001", "family_0028_step002"):
        choices[name] = ("P1_REVIEW", "historical512 SOAP outlier;source-family dedup and magnetic risk review first")
    candidates = []
    for name, (priority, reason) in choices.items():
        row = pool[name]
        binding = bindings[name]
        geometry = Path(row["structure_path"])
        if sha256_file(geometry) != row["structure_sha256"]:
            raise ValueError("chosen source geometry changed")
        metadata = Path(row["frame_metadata_path"])
        if sha256_file(metadata) != row["frame_metadata_sha256"]:
            raise ValueError("chosen source metadata changed")
        stored = load_json_object(metadata)
        if stored["structure_sha256"] != row["structure_sha256"]:
            raise ValueError("stored prediction geometry mismatch")
        atoms = read(geometry, format="vasp")
        record = {"candidate_id": name, "candidate_kind": "EXISTING_REICO_GEOMETRY", "priority": priority,
                  "composition": row["composition"], "family_id": row["family_id"], "source": str(geometry),
                  "structure_sha256": row["structure_sha256"], "source_metadata": str(metadata),
                  "source_metadata_sha256": row["frame_metadata_sha256"], "source_ML_step": row["step"],
                  "stored_ML_fmax_eV_A": stored.get("ML_movable_fmax_eV_A"),
                  "stored_prediction_is_not_new536_prediction": True,
                  "chemical_graph": component_sizes(atoms.get_chemical_symbols()[45:], row["adsorbate_edges_local_0based"]),
                  "existing_label_status": binding["label_status"], "physical_labels": binding["physical_labels"],
                  "proposed_role": "FUTURE_TRAINING_REVIEW_ONLY_NOT_INDEPENDENT_VALIDATION",
                  "selection_reason": reason,
                  "compatibility": "geometry on existing Fe45 branch;DFT settings/magnetism require actual label",
                  "admission_blockers": ["fresh536 force-error/novelty ranking not executed", "symmetry/near-duplicate isolation pending",
                                         "deduplicate trajectory families", "no same-coordinate compatible DFT label established"],
                  "new_DFT_budget": "0 now;one SP per finally selected unique coordinate only after review",
                  "dataset_or_partition_change": False}
        candidates.append(record)
        bound.update([geometry, metadata])
    bad_path = SIDECAR / "single_point_gap_proposals.json"
    bad = [r for r in load_json_object(bad_path)["records"] if r.get("structure_path")]
    for row in bad:
        path = Path(row["structure_path"])
        if sha256_file(path) != row["structure_sha256"]:
            raise ValueError("excluded label geometry changed")
        candidates.append({"candidate_id": row["candidate_id"], "candidate_kind": "EXISTING_LABEL_BLOCKED",
                           "priority": "P0_QC_REVIEW_NOT_AUTOMATIC_RECALCULATION", "composition": row["composition"],
                           "source": str(path), "structure_sha256": row["structure_sha256"],
                           "existing_label_status": row["existing_label_status"], "admission_blockers": [row["blocker"]],
                           "selection_reason": row["next_review"], "new_DFT_budget": row["single_point_condition"],
                           "proposed_role": "TRAINING_LINEAGE_QC_REVIEW_NOT_NEW_INDEPENDENT_CASE"})
        bound.add(path)
    reaction_path = SIDECAR / "reaction_source_sidecar.json"
    reactions = load_json_object(reaction_path)
    labels = reactions["C_H_static_labels"] + reactions["CH_CO_path"]["labels"]
    path_rows = []
    for row in labels:
        geometry = Path(row["structure_path"])
        protected = row.get("protected_TS_validation", False)
        record = {"candidate_id": row["sample_id"], "candidate_kind": "EXISTING_SAME_COORDINATE_PATH_LABEL",
                  "priority": "PROTECTED_NO_TRAINING" if protected else "P0_REUSE_REVIEW_BEFORE_NEW_DFT",
                  "composition": row["composition"], "source": row["source_OUTCAR_path"],
                  "source_OUTCAR_sha256": row["source_OUTCAR_sha256"], "DFT_ionic_step": row["DFT_ionic_step"],
                  "source_byte_range": row["source_byte_range"], "structure_path": str(geometry),
                  "structure_sha256": sha256_file(geometry), "coordinate_force_match": row["coordinate_force_match"],
                  "electronic_raw_pass": row["electronic_raw_pass"], "compatibility": row["compatibility"],
                  "raw_magnetic_grade": row["raw_magnetic_grade"], "chemical_event": row["chemical_event"],
                  "existing_label_status": "E_F_AND_BRANCH_VERIFIED_LOCAL_MAGNETISM_MISSING",
                  "proposed_role": row["permitted_use"], "protected_TS_validation": protected,
                  "admission_blockers": ["preserve legacy magnetic scope;no automatic promotion", "whole-path/family isolation required"],
                  "new_DFT_budget": "0 for existing label;magnetic scope review before considering any recomputation",
                  "force_definition": "raw atomic TOTAL-FORCE;not NEB spring/projected force"}
        path_rows.append(record)
        bound.add(geometry)
    near_path = BASE / "independent_nearstable_inventory_20261113_v1/source_plan.json"
    near = load_json_object(near_path)
    external = [r for r in near["near_force_candidate_references"] if r["proposed_role"] == "external_C2_isomer_force_candidate_not_admitted"]
    near_rows = []
    for name in ("job9927794_opt066", "job9927514_opt048"):
        row = next(r for r in external if r["candidate_id"] == name)
        near_rows.append({"candidate_id": name, "candidate_kind": "EXISTING_EXTERNAL_C2_NEARSTABLE_LABEL",
                         "priority": "P0_INDEPENDENT_VALIDATION_REVIEW_NO_TRAINING", "composition": "C2H3",
                         "source": row["source_OUTCAR"], "source_OUTCAR_sha256": row["source_OUTCAR_sha256"],
                         "DFT_ionic_step": row["ionic_step"], "source_byte_range": row["OUTCAR_byte_range"],
                         "raw_force_table_sha256": row["raw_force_table_sha256"], "source_XDATCAR": row["source_XDATCAR"],
                         "source_XDATCAR_sha256": row["source_XDATCAR_sha256"],
                         "movable_DFT_fmax_eV_A": row["movable_fmax_eV_A"], "chemical_connection": "[C]-CH3;not [CH]-[CH2]",
                         "existing_label_status": "EXISTING_COORDINATE_FORCE_AND_POSITIVE_LOCAL_FE_REVIEWED",
                         "proposed_role": "INDEPENDENT_ISOMER_FORCE_STRESS_PROPOSAL_NOT_TRAINING",
                         "prior_geometry_isolation": row["geometry_isolation"],
                         "admission_blockers": ["formal terminal evidence pending for11C"] if "9927514" in name else [],
                         "new_DFT_budget": "0;reuse existing labels within documented scope"})
    proposal_path = BASE / "c3_independent_validation_proposal_20261113_v1/proposal_evidence.json"
    proposal = load_json_object(proposal_path)
    seeds = []
    for row in proposal["candidates"]:
        source = row["proposed_pose_file"] or row["upstream_source"][0]["path"]
        path = Path(source)
        seeds.append({"candidate_id": row["candidate_id"], "candidate_kind": "EXISTING_C3_INDEPENDENT_SEED_NOT_NEARSTABLE_LABEL",
                      "priority": "P1_SOURCE_GAP_REVIEW", "composition": "C3H2O", "source": source,
                      "structure_sha256": sha256_file(path), "source_pose_kind": row["proposed_pose_kind"],
                      "chemical_graph": row["graph"], "proposed_role": row["proposed_role"],
                      "existing_label_status": row["same_coordinate_compatible_DFT_label"],
                      "compatibility": "Fe48 upstream cannot serve as active Fe45 DFT label" if not row["proposed_pose_file"] else "existing revised Fe45 geometry only;no compatible DFT label established",
                      "admission_blockers": ["no verified independent nearstable geometry", "target three-mode gate not complete",
                                             "source lineage/whole-path isolation required"],
                      "new_DFT_budget": "Needs confirmation;SP on arbitrary seed does not create a stable endpoint"})
        bound.add(path)
    network_path = OUT / "reaction_network_sources.json"
    network = load_json_object(network_path)
    bound.update([bad_path, reaction_path, near_path, proposal_path, network_path])
    records = candidates + path_rows + near_rows + seeds
    write_json_exclusive(OUT / "candidate_inventory_v2.json", {
        "status": "READ_ONLY_CANDIDATE_SOURCES_NOT_ADMISSION_OR_EXECUTION_PACKAGE", "records": records,
        "counts_by_kind": dict(Counter(r["candidate_kind"] for r in records)),
        "C2_external_low_force_frames": len(external), "C2_external_source_trajectories": len({r["source_job_id"] for r in external}),
        "reaction_source_proposals_without_coordinates": network["representative_proposals"],
        "accepted_scalar_barrier_sets": reactions["registered_energy_references"]["existing_barriers"],
        "accepted_scalar_anchors_not_automatic_force_labels": reactions["registered_energy_references"]["anchors"],
        "new_DFT_budget_allocated": 0, "training_or_inference_or_geometry_generation": False,
        "source_files": source_file_manifest(sorted(bound))})
    export_csv(OUT / "candidate_inventory_v2.csv", records, ["candidate_id", "candidate_kind", "priority", "composition", "family_id", "source",
               "structure_sha256", "source_OUTCAR_sha256", "DFT_ionic_step", "existing_label_status", "proposed_role",
               "selection_reason", "compatibility", "admission_blockers", "new_DFT_budget"])
    export_csv(OUT / "existing_path_labels_v2.csv", path_rows, ["candidate_id", "composition", "chemical_event", "source", "source_OUTCAR_sha256",
               "DFT_ionic_step", "structure_path", "structure_sha256", "coordinate_force_match", "electronic_raw_pass",
               "raw_magnetic_grade", "protected_TS_validation", "proposed_role", "new_DFT_budget"])
    print({"candidate_counts": dict(Counter(r["candidate_kind"] for r in records)), "C2_external_frames": len(external),
           "path_labels": len(path_rows), "protected_path_labels": sum(r["protected_TS_validation"] for r in path_rows)}, flush=True)


if __name__ == "__main__":
    run()
