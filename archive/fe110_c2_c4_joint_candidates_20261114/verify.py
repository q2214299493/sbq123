"""Validate source bindings and read-only guards, without accepting candidates."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .collect_sources import BASE, OUT, ROOT


def run():
    names = ["coordinate_site_isolation_audit_v4.json", "CARE_geometry_audit_v4.json", "existing_paper_label_sources_v4.json",
             "static_cost_references.json", "reaction_path_reuse_audit.json", "single_point_candidates_and_budget_v2.json", "checks_v3.json"]
    source_checks = {name: source_file_manifest_valid(load_json_object(OUT / name)) for name in names}
    batch = load_json_object(OUT / "single_point_candidates_and_budget_v2.json")
    selected = batch["selected"]
    request = load_json_object(OUT / "request_context.json")
    source_geometry_checks = {r["candidate_id"]: sha256_file(Path(r["source_path"])) == r["source_sha256"] for r in selected}
    minimum_protected = min(r["isolation"]["protected"]["minimum_ads_pose_RMSD_A_any_reference"] for r in selected)
    minimum_pair = min(r["full_RMSD_A"] for r in batch["selected_same_composition_pairwise_metrics"])
    server = load_json_object(OUT / "server_extended_geometry_index.json")
    paper = load_json_object(OUT / "existing_paper_label_sources_v4.json")
    path = load_json_object(OUT / "reaction_path_reuse_audit.json")
    manifest = load_json_object(BASE / "combined_force_package_20261113_v1/training_manifest.json")
    checks = {"all_current_source_manifests_valid": all(source_checks.values()),
              "twenty_actual_source_geometries_hash_bound": len(selected) == 20 and all(source_geometry_checks.values()),
              "twenty_distinct_families": len({r["family_id"] for r in selected}) == 20,
              "no_known_prior_failure_family_in_first_batch": not any(r["family_risk_note"] for r in selected),
              "protected_pose_isolation_above0p20A": minimum_protected > .20,
              "selected_pair_isolation_above0p10A": minimum_pair >= .10,
              "all_selected_same_cell_fixed_mask_pair_guards_pass": all(not r["new_SP_review_blockers"] for r in selected),
              "all_selected_default_joint_signatures_new_and_distinct": len({r["joint_signature"] for r in selected}) == 20,
              "server_scope_limits_not_exceeded": server["status"] == "BOUNDED_SCOPE_COMPLETE" and not server["limits"],
              "no_C4_C5_C6_in_parsed_existing_server_records": server["C4_C5_C6_records"] == 0,
              "six_existing_first_step_force_coordinate_checks_passed": len(path["newly_bound_existing_first_steps"]) == 6 and all(r["coordinate_force_precision_check"] and r["EDIFF_marker_before_force"] for r in path["newly_bound_existing_first_steps"]),
              "six_protected_C_H_validation_labels_preserved": path["protected_C_H_validation_labels"] == 6,
              "test_and_lint_checks_passed": load_json_object(OUT / "checks_v3.json")["all_passed"],
              "frozen512_536_twelve_core_file_hashes_unchanged": frozen_hashes() == request["frozen_hashes_before"],
              "frozen_partitions536_78_53_16": [len(manifest["splits"][s]) for s in ("train", "development", "heldout")] + [len(manifest["quarantined_observed_heldout"])] == [536, 78, 53, 16],
              "candidate536_weight_unchanged": sha256_file(BASE / "training536_execution_20261113_v4/returned/candidate.pt") == request["baseline_candidate_weight_sha256"],
              "current_task_unchanged": sha256_file(ROOT / "tasks/current_task.md") == request["current_task_sha256"],
              "registry_unchanged": sha256_file(ROOT / "data/project_registry.sqlite3") == request["registry_sha256_before"],
              "backend_policy_unchanged": sha256_file(ROOT / "configs/execution_backends.yaml") == request["backend_policy_sha256"],
              "scientific_protocol_unchanged": sha256_file(ROOT / "docs/01_METHOD_PROTOCOL.md") == request["method_protocol_sha256"],
              "no_execution_or_scientific_acceptance_in_plan": not batch["new_DFT_training_inference_or_structure_generation"]}
    audit = load_json_object(OUT / "coordinate_site_isolation_audit_v4.json")
    result = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "source_binding_checks": source_checks,
              "selected_structure_checks": source_geometry_checks, "selected_formula_counts": dict(Counter(r["composition"] for r in selected)),
              "minimum_protected_ads_pose_RMSD_A": minimum_protected, "minimum_selected_same_formula_full_RMSD_A": minimum_pair,
              "reference_counts": audit["reference_counts_unique_source_bindings"],
              "selected_intact_C3H2O_count": sum(r["composition"] == "C3H2O" and r["geometry"]["graph"]["adsorbate_components"] == 1 for r in selected),
              "selected_connected_all_adsorbates_count": sum(r["geometry"]["graph"]["adsorbate_components"] == 1 for r in selected),
              "paper_unique_physical_force_records": paper["unique_physical_sources"],
              "labels_and_geometries_not_readmitted": True, "only_coordinate_v4_and_budget_v2_are_final": True,
              "source_files": source_file_manifest([OUT / n for n in names] + [OUT / "request_context.json", OUT / "server_extended_geometry_index.json", Path(__file__)])}
    write_json_exclusive(OUT / "final_verification.json", result)
    print({"status": result["status"], "checks": checks, "min_protected": minimum_protected, "min_pair": minimum_pair}, flush=True)
    if not all(checks.values()):
        raise ValueError("final audit verification failed;do not call candidates accepted")


if __name__ == "__main__":
    run()
