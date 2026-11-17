"""Validate real joined outputs, source bindings and frozen-input preservation."""
from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from pathlib import Path

from .analyze import guard_hashes, load, save, sha


def verify(run, output_name="verification_v2.json", binding_name="report_binding.json"):
    root = run / "results_v2"
    data = load(root / "joint_priority.json")
    frames = data["frames"]
    selected = data["selected_conditional_candidates"]
    checks = {}
    checks["614_unique_IDs_and_frozen_partitions"] = len({r["sample_id"] for r in frames}) == 614 and Counter(r["partition"] for r in frames) == {"train": 536, "development": 78}
    checks["614_complete_coordinate_physical_label_and_qualification_join"] = all(all(r[k] == r["actual_error"][k] for k in ("structure_sha256", "physical_label_key", "partition", "qualification_scope", "joint_signature")) for r in frames)
    checks["original_449_representatives_165_near_duplicates_not_removed"] = Counter(r["category"] for r in frames) == {"已有标签可复用": 449, "现有数据重复偏多": 165}
    checks["359_environment_cells_partition_614_exactly"] = len(data["environment_groups"]) == 359 and Counter(sid for g in data["environment_groups"] for sid in g["sample_ids"]) == Counter(r["sample_id"] for r in frames)
    sse_ok = True
    for role in ("adsorbate_C", "adsorbate_O", "adsorbate_H", "near_Fe", "other_Fe"):
        original = sum(r["actual_error"]["groups"].get(role, {}).get("sum_squared_vector_error", 0.) for r in frames)
        recomposed = sum(m["atoms"] * m["vector_RMSE_eV_A"] ** 2 for g in data["environment_groups"] if (m := g["role_metrics"][role])["atoms"])
        sse_ok &= math.isclose(original, recomposed, rel_tol=1e-12, abs_tol=1e-12)
    checks["per_role_error_SSE_conserved"] = sse_ok
    checks["six_primary_flags_have_existing_DFT_and_development_stays_development"] = sum(r["actual_error"]["ML_le0p05_DFT_gt0p10"] for r in frames) == 6 and next(r for r in frames if r["sample_id"] == "08_B_step111")["partition"] == "development" and not any(r["new_DFT_needed"] for r in frames)
    checks["all67_candidate_errors_and_DFT_fmax_remain_unknown"] = len(data["candidate_audit"]) == 67 and all(r["candidate_actual_ML_DFT_error_eV_A"] is None and r["candidate_DFT_fmax_eV_A"] is None for r in data["candidate_audit"])
    checks["neighbor_context_only_uses_training_labels"] = all(r["error_context"]["candidate_actual_ML_DFT_error_eV_A"] is None and next(f for f in frames if f["sample_id"] == r["error_context"]["reference_id"])["partition"] == "train" for r in data["candidate_audit"])
    checks["20_unique_families_source_isolated_robust_geometry_candidates"] = len(selected) == 20 and len({r["family_id"] for r in selected}) == 20 and all(r["candidate_robust_missing_all_scales"] and not r["family_risk_note"] and not r["new_SP_review_blockers"] and r["isolation"]["protected"]["minimum_ads_pose_RMSD_A_any_reference"] > .20 and (r["nearest_selected"]["full_RMSD_A"] is None or r["nearest_selected"]["full_RMSD_A"] >= .10) for r in selected)
    checks["candidate_coordinate_bytes_and_metadata_unchanged"] = all(sha(r["source_path"]) == r["source_sha256"] and sha(r["frame_metadata_path"]) == r["frame_metadata_sha256"] for r in data["candidate_audit"])
    checks["20_multicomponent_candidates_not_called_intact_C3_or_C4"] = all(r["geometry"]["graph"]["adsorbate_components"] > 1 and r["composition"] != "C4" for r in selected)
    checks["178_environment_gaps_176_missing_2_existing_blocked"] = Counter(r["category"] for r in data["environment_gaps"]) == {"确实缺少标注": 176, "已有记录但尚不可复用": 2}
    checks["142_backup_labels_not_moved_into_frozen_package"] = len(data["backup_labels"]) == 142 and all(r["new_training_admission"] is False and r["new_DFT_for_same_compatible_label"] == "NOT_NEEDED" for r in data["backup_labels"])
    checks["six_protected_path_references_preserved"] = sum(r["protected"] for r in data["path_labels"]) == 6 and all(not r["new_training_admission"] and not r["new_DFT_for_same_coordinate"] for r in data["path_labels"])
    checks["symbolic_reaction_rows_not_mislabelled_as_coordinates_or_missing_labels"] = all(2 <= r["total_C_each_side"] <= 4 and not r["geometry_path"] and r["actual_ML_DFT_error_eV_A"] is None and r["category"] != "确实缺少标注" for r in data["symbolic_path_gaps"])
    checks["C3_seed_roles_preserved_no_nearstable_claim"] = len(data["protected_C3_seed_sources"]) == 5 and sum(bool(r["proposed_pose_file"]) for r in data["protected_C3_seed_sources"]) == 3 and all(not r["is_verified_nearstable_frame"] for r in data["protected_C3_seed_sources"])
    checks["C4_real_coordinate_and_error_not_invented"] = data["mainline_source_gaps"][1]["real_candidate_ids"] == [] and data["mainline_source_gaps"][1]["actual_error"] is None
    checks["all_primary_source_byte_hashes_revalidated"] = all(sha(r["path"]) == r["sha256"] for r in data["source_files"])
    checks["frozen12_model_task_method_backend_unchanged"] = guard_hashes() == data["frozen_hashes_before"] == data["frozen_hashes_after"]
    csv_inventory = []
    rectangular = True
    for p in [*sorted(root.glob("*.csv")), run / "补标候选连接环境.csv"]:
        with p.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        rectangular &= bool(rows) and all(len(r) == len(rows[0]) for r in rows[1:])
        csv_inventory.append({"path": str(p), "rows": len(rows) - 1, "columns": len(rows[0]), "sha256": sha(p)})
    checks["all_CSV_tables_rectangular_UTF8"] = rectangular
    expected = {"614帧误差环境联合表.csv": 614, "化学环境实测误差优先表.csv": 359, "67候选审核及误差上下文.csv": 67, "补标条件候选与预算.csv": 20, "178缺口类型处置表.csv": 178, "142包外标签复用表.csv": 142, "C3验收种子与阻塞.csv": 5, "补标候选连接环境.csv": 20}
    checks["requested_table_row_counts_match"] = all(next(v["rows"] for v in csv_inventory if Path(v["path"]).name == name) == count for name, count in expected.items())
    report_binding = load(run / binding_name)
    report = Path(report_binding["report"])
    text = report.read_text(encoding="utf-8")
    checks["report_binding_matches_final_data_and_sources"] = sha(root / "joint_priority.json") == report_binding["data_sha256"] and sha(report) == report_binding["report_sha256"] and all(sha(r["path"]) == r["sha256"] for r in report_binding["source_files"])
    link_paths = re.findall(r"\]\(([^)]+)\)", text)
    checks["report_quality_gate_UTF8_units_scope_links_complete"] = "\ufffd" not in text and all(Path(p).exists() for p in link_paths if Path(p).name != output_name) and all(word in text for word in ("eV/Å", "不确定度", "未知", "512/536", "78/53/16", "P0", "P1", "P2"))
    checks["no_new_scientific_compute_or_budget"] = data["summary"]["new_DFT_allocated"] == data["summary"]["new_GPU_predictions"] == data["summary"]["new_training_runs"] == 0 and all(r["new_DFT_budget_allocated"] == 0 for r in data["master_priorities"])
    result = {"all_checks_passed": all(checks.values()), "checks": checks, "csv_inventory": csv_inventory,
              "report_quality_gate": "核对需求、中文、数字、链接、数据口径、未知值和科学边界；未将程序通过当作科学验收",
              "scientific_acceptance": False, "execution_authorized": False}
    save(run / output_name, result)
    print({"all_checks_passed": result["all_checks_passed"], "checks": len(checks), "failed": [k for k, v in checks.items() if not v]})
    if not result["all_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output-name", default="verification_v2.json")
    parser.add_argument("--binding-name", default="report_binding.json")
    args = parser.parse_args()
    if Path(args.output_name).name != args.output_name or Path(args.binding_name).name != args.binding_name:
        raise ValueError("receipt names must be simple filenames under this audit run")
    verify(args.run.resolve(), args.output_name, args.binding_name)
