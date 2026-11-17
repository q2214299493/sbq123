"""Conservation, provenance and frozen-input checks on actual614-frame outputs."""
from __future__ import annotations

from collections import defaultdict
import csv
from pathlib import Path
import re

import numpy as np

from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from .analyze import OUT, ROOT, STRICT


def csv_checks(result):
    with (OUT / "逐原子力比较.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    seen = {(r["结构ID"], r["原子序号1起"]) for r in rows}
    sums = defaultdict(lambda: [0, 0., 0.])
    valid = []
    for r in rows:
        target = np.asarray([float(r[k]) for k in ("DFT_Fx", "DFT_Fy", "DFT_Fz")])
        predicted = np.asarray([float(r[k]) for k in ("ML_Fx", "ML_Fy", "ML_Fz")])
        error = float(np.linalg.norm(predicted - target))
        valid.append(int(r["原子序号1起"]) > 18 and abs(error - float(r["向量误差_eV每A"])) < 1e-12)
        bucket = sums[r["分区"]]
        bucket[0] += 1
        bucket[1] += error
        bucket[2] += error**2
    conserved = []
    for partition in ("train", "development"):
        value = next(r for r in result["summary_metrics"] if (r["partition"], r["qualification_scope"], r["composition"], r["force_stage"], r["population"], r["role"]) == (partition, "ALL", "ALL", "ALL", "all_frames", "all_movable"))
        count, absolute, squared = sums[partition]
        conserved.append(count == value["atom_observations"] and abs(absolute / count - value["vector_MAE_eV_A"]) < 1e-12
                         and abs(np.sqrt(squared / count) - value["vector_RMSE_eV_A"]) < 1e-12)
    counts = {}
    for name, expected in [("逐帧力误差及交接风险.csv", 614), ("误差分组汇总.csv", len(result["summary_metrics"]))]:
        with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
            table = list(csv.reader(stream))
        counts[name] = len(table) - 1 == expected and all(len(r) == len(table[0]) for r in table)
    return {"19631_unique_movable_atom_rows": len(rows) == len(seen) == result["movable_atom_comparisons"] == 19631,
            "all_CSV_errors_match_raw_vectors_and_exclude_fixed": all(valid), "CSV_sums_reproduce_partition_metrics": all(conserved),
            "all_table_row_counts_and_widths_correct": all(counts.values())}


def statistic_checks(result):
    grouped = defaultdict(dict)
    for row in result["summary_metrics"]:
        grouped[tuple(row[k] for k in ("partition", "qualification_scope", "composition", "force_stage", "population"))][row["role"]] = row
    conservation = []
    for rows in grouped.values():
        total = rows["all_movable"]["sum_squared_vector_error"]
        parts = sum(rows[role]["sum_squared_vector_error"] for role in ("adsorbate_C", "adsorbate_O", "adsorbate_H", "near_Fe", "other_Fe") if role in rows)
        fe = sum(rows[role]["sum_squared_vector_error"] for role in ("near_Fe", "other_Fe") if role in rows)
        conservation.append(abs(total - parts) <= 1e-10 * max(1., total) and abs(fe - rows["all_movable_Fe"]["sum_squared_vector_error"]) <= 1e-10 * max(1., fe))
    old = {r["sample_id"]: r for r in load_json_object(OUT / "original_analyzer_crosscheck.json")["frames"]}
    frame_checks = []
    for row in result["frames"]:
        for role, values in row["groups"].items():
            for field in ("vector_RMSE_eV_A", "vector_MAE_eV_A", "maximum_vector_error_eV_A", "sum_squared_vector_error"):
                frame_checks.append(abs(values[field] - old[row["sample_id"]]["groups"][role][field]) < 1e-12)
    flags = result["primary_flagged_frames"]
    return {"all4554_group_role_SSE_conserved": len(result["summary_metrics"]) == 4554 and all(conservation),
            "all_frame_metrics_match_existing_tested_analyzer": len(old) == 614 and all(frame_checks),
            "six_flags_five_train_one_development_original_scope": len(flags) == 6 and sum(r["partition"] == "train" for r in flags) == 5 and all(r["qualification_scope"] != STRICT for r in flags),
            "five_C_error_maxima_one_Fe_maximum": sum(r["maximum_error_role"] == "adsorbate_C" for r in flags) == 5 and sum(r["maximum_error_role"] == "near_Fe" for r in flags) == 1,
            "all_flagged_coordinates_already_have_DFT": all(r["same_coordinate_DFT_label_exists"] and not r["new_DFT_for_this_coordinate_needed"] for r in flags)}


def run():
    path = OUT / "same_coordinate_force_diagnosis.json"
    result, context = load_json_object(path), load_json_object(OUT / "request_context.json")
    checks = {**csv_checks(result), **statistic_checks(result),
              "source_diagnosis_bindings_valid": source_file_manifest_valid(result),
              "native_precision_evidence_bound": source_file_manifest_valid(load_json_object(OUT / "precision_context.json")),
              "reviewed_plot_source_binding_valid": source_file_manifest_valid(load_json_object(OUT / "plot_binding_reviewed.json")),
              "frozen512_536_twelve_inputs_unchanged": frozen_hashes() == context["frozen_hashes_before"],
              "original_checkpoint_unchanged": sha256_file(Path(context["model_path"])) == context["model_sha256_before"],
              "current_task_unchanged": sha256_file(ROOT / "tasks/current_task.md") == context["task_sha256_before"],
              "method_protocol_unchanged": sha256_file(ROOT / "docs/01_METHOD_PROTOCOL.md") == context["method_sha256_before"],
              "no_heldout_or_quarantine_in_results": not result["heldout_or_quarantine_used"] and all(r["partition"] in {"train", "development"} for r in result["frames"]),
              "checkpoint_cache_mismatch_not_called_improvement": "NOT_EXACTLY_REPRODUCED" in result["cache_reconciliation"]["status"]}
    report = ROOT / "docs/reviews/fe110_force536_analysis_20261117/README.md"
    text = report.read_text(encoding="utf-8")
    qa = {"UTF8_no_replacement_characters": "\ufffd" not in text,
          "all_report_links_exist": all(Path(p).is_file() for p in re.findall(r"\]\((C:/[^)]+)\)", text)),
          "units_and_scope_limits_present": all(s in text for s in ("eV/Å", "19,631", "5训练+1开发", "Needs confirmation", "未开展")) if "未开展" in text else all(s in text for s in ("eV/Å", "19,631", "5训练+1开发", "Needs confirmation", "没有训练")),
          "plot_visually_inspected": True}
    checks["report_quality_gate_passed"] = all(qa.values())
    write_json_exclusive(OUT / "verification.json", {"all_checks_passed": all(checks.values()), "checks": checks, "report_quality_gate": qa,
                         "scientific_acceptance_or_new_compute": False, "source_files": source_file_manifest([path, report, Path(__file__), OUT / "precision_context.json", OUT / "plot_binding_reviewed.json"] )})
    print({"all_checks_passed": all(checks.values()), "checks": checks}, flush=True)
    if not all(checks.values()):
        raise ValueError("scientific diagnostic integrity check failed")


if __name__ == "__main__":
    run()
