"""Write conditional gap proposals beside the audit; never create DFT inputs."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .collect import BASE, OUT
from .finalize import export_csv


def excluded_label(source, sample_id, reason, action):
    original = next(row for row in load_json_object(source)["samples"] if row["sample_id"] == sample_id)
    structure = Path(original["structure_path"])
    if not structure.is_absolute():
        structure = source.parent / structure
    if sha256_file(structure) != original["structure_sha256"]:
        raise ValueError("excluded candidate structure hash changed")
    return {
        "candidate_id": sample_id, "source_job_id": original["source_job_id"],
        "composition": original["composition"], "source_metadata": str(source),
        "structure_path": str(structure), "structure_sha256": original["structure_sha256"],
        "existing_label_status": original["data_qc_status"], "blocker": reason,
        "next_review": action, "single_point_condition": "selected_for_training_and_no_existing_compatible_label_after_review",
        "DFT_budget_now": 0, "conditional_budget_after_review": 1,
        "training_family_candidate_not_independent_acceptance": True,
        "scientific_acceptance_or_submission_authorized": False,
    }


def run():
    final30 = BASE / "final30_qc_20261025_v1/all_selected_label_qc_local_only.json"
    grouped = BASE / "grouped_qc_20261026_v2/all_frame_qc_local_only.json"
    proposals = [
        excluded_label(final30, "family_0028_step000", "nonpositive_Fe_local_moment_original_magnetic_exclusion",
                       "review_original_magnetic_branch_before_any_new_label"),
        excluded_label(final30, "family_0086_step000", "electronic_convergence_and_label_correspondence_failure",
                       "keep_rejected;review_if_this_training_geometry_is_needed"),
        excluded_label(grouped, "family_0021_step004", "original_static_electronic_quality_gate_failed",
                       "keep_rejected;ML_step004_is_not_DFT_ionic_step4"),
    ]
    coverage = load_json_object(OUT / "reaction_coverage_v2.json")["rows"]
    for row in coverage:
        if row["documented_source"] is None or row["environment"] == "independent_intact_C3_nearstable":
            proposals.append({"candidate_id": None, "source_job_id": None, "composition": "Needs confirmation",
                              "environment": row["environment"], "source_metadata": str(OUT / "reaction_coverage_v2.json"),
                              "structure_path": None, "structure_sha256": None, "existing_label_status": row["existing_evidence"],
                              "blocker": row["gap"], "next_review": row["reuse_action"],
                              "single_point_condition": "reviewed_real_coordinates_and_connectivity_then_existing_label_search",
                              "DFT_budget_now": 0, "conditional_budget_after_review": "Needs confirmation",
                              "scientific_acceptance_or_submission_authorized": False})
    write_json_exclusive(OUT / "single_point_gap_proposals.json", {
        "status": "CONDITIONAL_PROPOSALS_ONLY_NO_NEW_CALCULATIONS", "records": proposals,
        "new_DFT_requested_or_submitted": 0, "budget_allocation_authorized": False,
        "missing_local_moments_in_17_existing_reaction_labels_is_review_first_not_17_automatic_recalculations": True,
        "source_files": source_file_manifest([final30, grouped, OUT / "reaction_coverage_v2.json", Path(__file__),
                                              *[Path(row["structure_path"]) for row in proposals if row["structure_path"]]])})
    export_csv(OUT / "single_point_gap_proposals.csv", proposals,
               ["candidate_id", "source_job_id", "composition", "environment", "structure_path", "structure_sha256",
                "existing_label_status", "blocker", "next_review", "single_point_condition", "DFT_budget_now",
                "conditional_budget_after_review"])
    rows = load_json_object(OUT / "energy_label_sidecar_final_v2.json")["records"]
    flagged = [row for row in rows if row["pool"] == "frozen536" and "COMPATIBILITY_REVIEW_REQUIRED" in row["flags"]]
    from .audit import CLEAN_CELL

    cells = [np.asarray(read(row["structure_path"], format="vasp").cell) for row in flagged]
    write_json_exclusive(OUT / "cell_precision_review_note.json", {
        "affected_frozen_rows": len(flagged), "max_cell_difference_A": max(float(np.max(np.abs(cell - CLEAN_CELL))) for cell in cells),
        "all_equal_clean_cell_rounded_6_decimals": all(np.array_equal(cell, np.round(CLEAN_CELL, 6)) for cell in cells),
        "interpretation": "strict_1e-9A_guard_flags_serialization_precision;not_proof_of_a_different_physical_branch",
        "required_action": "review_original_input_cell_and_serialization;no_recalculation_justified_by_this_flag_alone",
        "old_scientific_grades_unchanged": True,
        "source_files": source_file_manifest([OUT / "energy_label_sidecar_final_v2.json", Path(__file__)])})
    print({"conditional_existing_failed_label_candidates": 3, "unbound_environment_or_geometry_gaps": len(proposals) - 3,
           "new_single_points_requested": 0, "cell_precision_flags": len(flagged)})


if __name__ == "__main__":
    run()
