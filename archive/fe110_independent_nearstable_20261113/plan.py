"""Bind a source-only acceptance plan; never modify splits or admit a dataset."""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

from archive.fe110_combined_force_package_20261023.prepare import save_once
from scripts.artifact_io import load_json_object as load
from scripts.artifact_io import sha256_file, source_file_manifest, source_file_manifest_valid
from .audit import CLEAN, PACKAGE, RULES, frozen_hashes
from .collect import BASE, OUTPUT, ROOT


def proposed_role(row):
    if row["adsorbate_component_count"] != 1:
        return "excluded_fragment_not_intact_target"
    if row["QC_errors"]:
        return "needs_magnetic_or_frame_review"
    matches = row.get("geometry_isolation", {})
    if matches.get("train", {}).get("within0p20A"):
        return "excluded_training_geometry_overlap"
    if matches.get("development", {}).get("within0p20A") or matches.get("heldout", {}).get("within0p20A"):
        return "historical_locked_partition_regression_only"
    if row["source_job_id"] == "9927793":
        return "existing_duplicate_of11B_no_new_independent_case"
    return "external_C2_isomer_force_candidate_not_admitted"


def old_C3_sources():
    root = BASE / "status_lowforce_check_20261023_v1"
    first = load(root / "existing_c3_9627285_trajectory.json")
    reuse = load(root / "existing_c3_previous_trajectory_reuse.json")
    diagnostic = ROOT / reuse["source_diagnostic"]
    if sha256_file(diagnostic) != reuse["source_diagnostic_sha256"]:
        raise ValueError("old C3 trajectory evidence changed")
    if first["intact_frames_fmax_le_0p05"] != 0 or any(r["intact_frames_below_0p05"] for r in reuse["cases"]):
        raise ValueError("old C3 intact-low-force conclusion differs")
    rebuilt = load(diagnostic)["cases"]
    return [{"job_id": first["source_job_id"], "frames": first["trajectory_frame_count"],
             "intact_low_force_frames": 0, "low_force_fragment_frames": first["all_frames_fmax_le_0p05"]},
            *[{"job_id": r["job_id"], "frames": len(r["frames"]), "intact_low_force_frames": 0,
               "all_low_force_frames": sum(f["fmax_movable_eV_A"] <= .05 for f in r["frames"])}
              for r in rebuilt]], diagnostic


def lineage_binding():
    evidence = load(OUTPUT / "registry_source_evidence.json")
    manifest = load(PACKAGE / "training_manifest.json")
    if any(not r.get("source_job_id") for r in manifest["splits"]["train"] if r["composition"] == "C2H3"):
        raise ValueError("target training source-job identity missing")
    training_jobs = {str(r["source_job_id"]) for r in manifest["splits"]["train"] if r.get("source_job_id")}
    records = {r["scheduler_job_id"]: r for r in evidence["records"]}
    for job in ("9927793", "9927794", "9927514"):
        if job in training_jobs:
            raise ValueError("external C2 source job present in training")
    if records["9927794"]["parent_calculation_id"] != records["9927513"]["calculation_id"]:
        raise ValueError("11B continuation parent binding differs")
    if records["9927793"]["parent_calculation_id"] != records["9927512"]["calculation_id"]:
        raise ValueError("11A continuation parent binding differs")
    root = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020"
    seed_manifest = load(root / "geometry_review_delivery_manifest.json")
    canonical_names = {seed_manifest["canonical"] + "/" + name + "/POSCAR" for name in ("11_A", "11_B", "11_C")}
    seeds = [r for r in seed_manifest["files"] if r["path"] in canonical_names]
    if len(seeds) != 3 or any(sha256_file(ROOT / r["path"]) != r["sha256"] for r in seeds):
        raise ValueError("canonical original seed binding changed")
    source_seeds = [str(ROOT / r["path"]) for r in seeds]
    return {"11_seed_cohort": "derived review group for three documented original construction seeds;not an existing REICO family ID",
            "canonical_seed_structures": seeds, "continuation_parents_verified": True,
            "jobs_absent_from_current_training_labels": True,
            "foundation_pretraining_exposure_audited": False,
            "historical_model_guided_geometry_exposure": True}, [root / "geometry_review_delivery_manifest.json",
                root / "candidates_v5/candidate_review.json", *map(Path, source_seeds)]


def guard_probes(rows):
    base = next(r for r in rows if r["candidate_id"] == "job9927794_opt066")
    assert proposed_role(base) == "external_C2_isomer_force_candidate_not_admitted"
    changed = copy.deepcopy(base)
    changed["geometry_isolation"]["train"]["within0p20A"] = True
    assert proposed_role(changed) == "excluded_training_geometry_overlap"
    changed = copy.deepcopy(base)
    changed["adsorbate_component_count"] = 2
    assert proposed_role(changed) == "excluded_fragment_not_intact_target"
    changed = copy.deepcopy(base)
    changed["geometry_isolation"]["heldout"]["within0p20A"] = True
    assert proposed_role(changed) == "historical_locked_partition_regression_only"
    return {"positive_external_source": True, "training_overlap_rejected": True,
            "fragment_rejected": True, "test_overlap_not_new_external_case": True}


def run():
    inventory = load(OUTPUT / "physical_inventory.json")
    if not source_file_manifest_valid(inventory) or frozen_hashes() != inventory["frozen_hashes_before_after"]:
        raise ValueError("physical inventory or frozen package binding changed")
    for summary in inventory["source_summaries"]:
        if not source_file_manifest_valid(summary):
            raise ValueError("physical source bytes changed")
    rows = [{**r, "proposed_role": proposed_role(r)} for r in inventory["near_force_candidates"]]
    legacy, diagnostic = old_C3_sources()
    lineage, seed_paths = lineage_binding()
    newer_C3 = [r for r in inventory["source_summaries"] if r["job_id"] in ("9925062", "9925065")]
    if sum(r["intact_C3_force_le0p05"] for r in newer_C3):
        raise ValueError("fresh C3 source has an unexpected intact-low-force candidate")
    rsi = Path("C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/runs/independent_nearstable_inventory_20261113_v1")
    receipt = load(rsi / "run_receipt.json")
    dependencies = [Path(__file__), OUTPUT / "physical_inventory.json", OUTPUT / "registry_source_evidence.json",
                    OUTPUT / "research_context.json", CLEAN, RULES, *seed_paths, diagnostic,
                    BASE / "status_lowforce_check_20261023_v1/existing_c3_9627285_trajectory.json",
                    BASE / "status_lowforce_check_20261023_v1/existing_c3_previous_trajectory_reuse.json",
                    BASE / "paired_relaxation2_20261027_v2/package/evidence/selection.json",
                    ROOT / "outputs/adsorption_acceptance_20261029_v1/analysis.json",
                    ROOT / "outputs/fe110_c2_registration_20261102_v1/analysis.json",
                    rsi / "run_receipt.json", rsi / "rsi_selection.json", rsi / "rsi_application.json",
                    ROOT / "archive/fe110_10b_lowforce_20261023/legacy_helpers.py",
                    ROOT / "archive/fe110_10b_lowforce_20261023/review.py",
                    ROOT / "archive/fe110_grouped_qc_20261026/review.py",
                    ROOT / "scripts/adsorption/reico_chemical_environments.py"]
    plan = {"document_kind": "independent_acceptance_source_plan_not_dataset_admission", "schema_version": 1,
            "status": "SOURCE_PLAN_REVIEWED_NO_EXECUTION", "read_only_sources": True,
            "candidate_role_counts": dict(Counter(r["proposed_role"] for r in rows)),
            "source_lineage": lineage, "near_force_candidate_references": rows,
            "existing_test_low_force_ids": [r["sample_id"] for r in inventory["existing_reserved_target_labels"] if r["fmax_eV_A"] <= .05],
            "representative_references": [
                {"id": "job9926807_opt069", "role": "local-moment-complete historical10A regression;overlaps locked heldout geometry;not new blind case"},
                {"id": "job9927794_opt066", "role": "external [C]-CH3 force stress representative;preexisting accepted endpoint;not vinyl substitute"},
                {"id": "job9927514_opt048", "role": "external [C]-CH3 force diagnostic;formal endpoint acceptance pending existing terminal evidence"}],
            "duplicate_representatives_not_added": ["job9927793_opt071", "job9910789_opt113", "job9910791_opt076"],
            "C3_nontraining_trajectory_scope": {"old_sources": legacy,
                "fresh_sources": [{k: r[k] for k in ("job_id", "source_frames", "intact_C3_frames", "intact_C3_force_le0p05")} for r in newer_C3],
                "total_frames": sum(r["frames"] for r in legacy) + sum(r["source_frames"] for r in newer_C3),
                "intact_nearstable_usable_sources_verified": 0,
                "threshold_eV_A": .05, "readiness": "Needs confirmation;no usable source in inspected existing labelled corpus"},
            "excluded_training_lineage": {"family": "family_0099", "jobs": ["9921439", "9922624", "9924387"],
                "reason": "existing training family;unused source frames are not independent evaluation labels"},
            "prospective_roles": {"10A": "fixed historical regression only", "11_B": "external isomer stress force cohort",
                "11_C": "additional force diagnostic;formal endpoint acceptance remains separate", "intact_C3": "uncovered"},
            "evaluation_boundaries": ["freeze source references and model/checkpoint before evaluation",
                "no tuning weights or epochs on heldout/external acceptance results",
                "report per chemical graph,composition and movable atomic role;do not pool absent C3 as zero error",
                "direction metrics require nonzero vector handling;pre-register thresholds",
                "actual optimization acceptance still needs matched initial hashes,VASP settings,chemical endpoints and0.02 eV/A",
                "source force labels alone do not demonstrate optimization acceleration"],
            "new_dataset_or_loader_created": False, "existing_partitions_changed": False,
            "training_or_model_inference_run": False, "new_DFT_submitted": False, "scientific_acceptance_granted": False,
            "guard_probes": guard_probes(rows),
            "RSI": {"status": receipt["status"], "run_mode": receipt["run_mode"], "model_turns_started": receipt["model_turns_started"],
                "selected_policies": len(load(rsi / "rsi_selection.json")["selected_policies"]),
                "applications": len(load(rsi / "rsi_application.json")["applications"]), "retried": False},
            "source_files": source_file_manifest(dependencies)}
    save_once(OUTPUT / "source_plan.json", plan)
    return plan


if __name__ == "__main__":
    result = run()
    print({"status": result["status"], "roles": result["candidate_role_counts"],
           "C3_frames_reviewed": result["C3_nontraining_trajectory_scope"]["total_frames"]})
