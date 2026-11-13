"""Merge incremental evidence and export sidecar views; never alter a dataset."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from .audit import Sources, inspect_row, roles_and_groups, source_rows
from .collect import OUT


def recover_final_records():
    previous = load_json_object(OUT / "energy_label_sidecar_v2.json")
    records = previous["records"]
    sources = Sources()
    additional = load_json_object(OUT / "remote_additional_evidence.json")
    sources.remote.update({r["OUTCAR_sha256"]: r for r in additional["results"] if r.get("expected_hash_matches")})
    items = {(x["pool"], x["row"]["sample_id"]): x for x in source_rows()}
    replaced = 0
    for index, record in enumerate(records):
        if "EXISTING_RAW_SOURCE_RECOVERY_REQUIRED_NOT_NEW_DFT" in record["flags"]:
            records[index] = inspect_row(items[(record["pool"], record["sample_id"])], sources)
            replaced += 1
    groups = roles_and_groups(records)
    write_json_exclusive(OUT / "energy_label_sidecar_final_v2.json", {
        "status": "READ_ONLY_INCREMENTAL_EVIDENCE_NOT_ADMISSION", "records": records,
        "relative_energy_groups_same_OUTCAR": groups, "additional_existing_sources_recovered": replaced,
        "absolute_AQ_energy_target_ready": False, "old_magnetic_grades_not_changed": True,
        "source_files": source_file_manifest([OUT / "energy_label_sidecar_v2.json", OUT / "remote_additional_evidence.json", Path(__file__)])})
    return records


def unique_labels(records):
    indexed = defaultdict(list)
    for record in records:
        key = record.get("physical_label_key") or str(record.get("source_OUTCAR_sha256")) + ":unresolved:" + record["sample_id"]
        indexed[key].append(record)
    result = []
    for key, aliases in indexed.items():
        energies = {r["E_TOTEN_eV"] for r in aliases if r.get("E_TOTEN_eV") is not None}
        if len(energies) > 1:
            raise ValueError("same physical label has inconsistent stored energies")
        protected = any(r.get("partition") in ("quarantine", "heldout", "final_test", "development") for r in aliases)
        train_exposed = any(r.get("partition") == "train" for r in aliases)
        ready = any(r.get("energy_force_evidence_ready_for_review") for r in aliases)
        result.append({"physical_label_key": key, "representative_sample_id": aliases[0]["sample_id"],
                       "composition": aliases[0].get("composition"), "E_TOTEN_eV": next(iter(energies), None),
                       "source_OUTCAR_sha256": aliases[0].get("source_OUTCAR_sha256"),
                       "DFT_ionic_step": aliases[0].get("DFT_ionic_step"),
                       "aliases": [{"pool": r["pool"], "sample_id": r["sample_id"], "partition": r.get("partition")} for r in aliases],
                       "raw_E_F_local_magnetic_evidence_ready": ready,
                       "existing_train_exposure": train_exposed, "protected_partition_exposure": protected,
                       "train_and_protected_conflict": train_exposed and protected,
                       "future_energy_reuse_review_candidate": ready and train_exposed and not protected,
                       "absolute_AQ_energy_target_ready": False, "training_admission": False,
                       "existing_label_no_duplicate_DFT": True})
    return result


def export_csv(path, rows, columns):
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def coverage_rows(reactions):
    barriers = reactions["registered_energy_references"]["existing_barriers"]
    return [
        {"environment": "CO_C-O_cleavage", "documented_source": barriers[0]["barrier_set_id"], "existing_evidence": "accepted_IS_TS_FS_energy_reference",
         "reuse_action": "reuse_existing_reference;recover_frame_labels_before_training", "gap": "broader_oxygenated_C2_C3_C-O_paths_not_established", "new_single_point": "not_needed_for_existing_reference"},
        {"environment": "C_plus_H_to_CH", "documented_source": "C-H path image02-image06;heldout R1,R2,S1,S2,F1,F2", "existing_evidence": "5_training_diagnostics+6_protected_validation+accepted_barrier",
         "reuse_action": "reuse_E_F_diagnostics;preserve6validation;magnetic_scope_review", "gap": "no_atom_resolved_moment_tables_in11static_outputs", "new_single_point": "conditional_only_after_legacy_magnetic_admission_review"},
        {"environment": "CH_plus_H_to_CH2", "documented_source": next(b["barrier_set_id"] for b in barriers if 'ch_h_to_ch2' in b['barrier_set_id']), "existing_evidence": "accepted_barrier_and_existing_NEB_pointers",
         "reuse_action": "reuse_reference;extract_existing_path_frames_first", "gap": "path_frames_not_yet_converted_to_reviewed_energy_training_manifest", "new_single_point": "do_not_recompute_existing_path_before_source_extraction"},
        {"environment": "C2HO_plus_H_O-H_formation", "documented_source": next(b["barrier_set_id"] for b in barriers if 'c2ho_oh' in b['barrier_set_id']), "existing_evidence": "accepted_IS_TS_FS_energy_reference",
         "reuse_action": "reuse_reference_with_partial_Hessian_scope_preserved", "gap": "does_not_cover_all_OH_water_or_other_C2_C3_H_transfers", "new_single_point": "not_needed_for_existing_reference"},
        {"environment": "CH_plus_CO_C-C_formation", "documented_source": "job9994246_images01-06_opt207", "existing_evidence": "6same-frame_raw_E_F+8scalar_profile_points;not_accepted_barrier",
         "reuse_action": "reuse_diagnostics;review_missing_local_magnetism;no_TS_promotion", "gap": "missing_local_moments;path_sampling_gap_does_not_automatically_prove_model_error", "new_single_point": "conditional_after_source_and_scientific_scope_review"},
        {"environment": "surface_H_migration", "documented_source": "registered_INT06_MID_ISA_paths", "existing_evidence": "existing_NEB_Dimer_source_pointers;no_accepted_barrier_in_snapshot",
         "reuse_action": "extract_existing_sources_before_new_DFT", "gap": "training_label_quality_and_connectivity_review_pending", "new_single_point": "Needs_confirmation_after_existing_source_review"},
        {"environment": "C2_plus_C1_to_C3_chain_growth", "documented_source": None, "existing_evidence": "no_documented_path_label_in_audited_registry_scope",
         "reuse_action": "Needs_confirmation_of_real_candidate_ID_and_source", "gap": "reaction_path_geometry_and_label_gap", "new_single_point": "needed_for_reviewed_novel_unlabelled_coordinates;count_TBD"},
        {"environment": "C3_H_transfer_or_C3_C-O_change", "documented_source": None, "existing_evidence": "REICO_C3_environments_are_not_documented_reaction_paths",
         "reuse_action": "Needs_confirmation_of_real_candidate_ID_and_source", "gap": "C3_reaction_event_and_path_segment_coverage", "new_single_point": "needed_for_reviewed_novel_unlabelled_coordinates;count_TBD"},
        {"environment": "CO_insertion", "documented_source": None, "existing_evidence": "CH+CO_C-C_coupling_does_not_establish_insertion_coverage",
         "reuse_action": "Needs_confirmation;do_not_relabel_coupling_as_insertion", "gap": "explicit_insertion_bond_changes_and_candidate_path_missing", "new_single_point": "TBD_after_candidate_provenance_review"},
        {"environment": "independent_intact_C3_nearstable", "documented_source": "CARE_FLJNAOYG_cfg1_and_revised_cfg2_are_starting_candidates_only", "existing_evidence": "24low_force_training_frames_all_family0099;0independent_intact_nearstable_in_prior618frames",
         "reuse_action": "preserve0099training;do_not_use_fragments_or_unused_sibling_frames_as_independent", "gap": "nearstable_geometry_source_and_third_target_motif_missing", "new_single_point": "single_points_alone_cannot_guarantee_closing_geometry_gap"},
    ]


def run():
    records = recover_final_records()
    unique = unique_labels(records)
    reactions = load_json_object(OUT / "reaction_source_sidecar.json")
    near = load_json_object(OUT / "near_energy_source_sidecar.json")
    coverage = coverage_rows(reactions)
    frozen = [r for r in records if r["pool"] == "frozen536"]
    failures = [r for r in records if "SOURCE_QC_EXCLUSION_PRESERVED" in r["flags"]]
    summary = {
        "status": "READ_ONLY_SIDECAR_NO_DATA_OR_MODEL_ADMISSION", "records_with_aliases": len(records),
        "unique_existing_labels": len(unique), "duplicate_aliases_collapsed_only_in_sidecar": len(records) - len(unique),
        "unique_raw_E_F_local_magnetic_evidence_ready": sum(r["raw_E_F_local_magnetic_evidence_ready"] for r in unique),
        "future_training_energy_reuse_review_candidates": sum(r["future_energy_reuse_review_candidate"] for r in unique),
        "frozen536_raw_evidence_ready_by_split": dict(Counter(r["partition"] for r in frozen if r.get("energy_force_evidence_ready_for_review"))),
        "frozen536_flags": {str(k): v for k, v in Counter(tuple(r["flags"]) for r in frozen).items()},
        "train_protected_label_conflicts": sum(r["train_and_protected_conflict"] for r in unique),
        "near_force_existing_energy_rows_separate_source_only": len(near["records"]),
        "documented_C_H_static_labels": len(reactions["C_H_static_labels"]),
        "protected_TS_validation_labels": sum(r["protected_TS_validation"] for r in reactions["C_H_static_labels"]),
        "CH_CO_existing_final_raw_force_frames": len(reactions["CH_CO_path"]["labels"]),
        "registered_accepted_barrier_references": len(reactions["registered_energy_references"]["existing_barriers"]),
        "registered_scalar_anchors_raw_replayed": sum(r["raw_scalar_match"] is True for r in reactions["registered_energy_references"]["anchors"]),
        "absolute_AQ_energy_training_ready": 0, "source_QC_exclusions": failures,
        "new_single_points_requested_or_submitted": 0, "new_single_point_counts_for_unbound_gaps": "Needs confirmation",
        "energy_labels_are_not_final_adsorption_or_TS_acceptance": True,
        "source_files": source_file_manifest([OUT / "energy_label_sidecar_final_v2.json", OUT / "reaction_source_sidecar.json",
                                              OUT / "near_energy_source_sidecar.json", Path(__file__)])}
    write_json_exclusive(OUT / "energy_reuse_catalog_v2.json", {"records": unique, "new_admission": False,
                                                            "source_files": source_file_manifest([OUT / "energy_label_sidecar_final_v2.json"])})
    write_json_exclusive(OUT / "reaction_coverage_v2.json", {"rows": coverage, "scope": "frozen_label_pools+49registry_TS_vibration_records+documented_CHCO_path+prior_near_force_inventory",
                                                        "not_an_exhaustive_search_of_every_server_directory": True,
                                                        "source_files": source_file_manifest([OUT / "registry_ts_snapshot.json", OUT / "reaction_source_sidecar.json"])})
    export_csv(OUT / "energy_reuse_catalog_v2.csv", unique, ["physical_label_key", "representative_sample_id", "composition", "E_TOTEN_eV", "source_OUTCAR_sha256", "DFT_ionic_step", "raw_E_F_local_magnetic_evidence_ready", "existing_train_exposure", "protected_partition_exposure", "future_energy_reuse_review_candidate", "absolute_AQ_energy_target_ready", "training_admission"])
    export_csv(OUT / "reaction_coverage_v2.csv", coverage, ["environment", "documented_source", "existing_evidence", "reuse_action", "gap", "new_single_point"])
    write_json_exclusive(OUT / "sidecar_summary_v2.json", summary)
    print({k: v for k, v in summary.items() if k not in ["source_files", "source_QC_exclusions", "frozen536_flags"]}, flush=True)


if __name__ == "__main__":
    run()
