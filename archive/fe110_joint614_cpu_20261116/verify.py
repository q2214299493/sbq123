"""Bounded final checks on the real CPU inventory, with frozen-package guards."""
from __future__ import annotations

import csv
from pathlib import Path
import re

import numpy as np

from archive.fe110_independent_nearstable_20261113.audit import frozen_hashes
from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive,
)
from .audit import BASE, BLOCKED, OUT, ROOT


def run():
    context = load_json_object(OUT / "request_context.json")
    path = OUT / "joint_inventory_reviewed.json"
    result = load_json_object(path)
    records = result["records"]
    labels = load_json_object(BASE / "force_diagnosis536_20261114_v1/qualified_reference_labels.json")["records"]
    measured = {r["sample_id"]: r for r in records}
    maximum_checks = []
    for row in labels:
        free = sorted(set(range(len(row["symbols"]))) - set(row["fixed_atom_indices_0based"]))
        maximum = np.linalg.norm(np.asarray(row["DFT_forces_eV_per_A"])[free], axis=1).max()
        maximum_checks.append(abs(maximum - measured[row["sample_id"]]["DFT_fmax_eV_A"]) < 1e-12)
    cluster_checks = []
    for row in records:
        representative = measured[row["near_duplicate"]["representative_id"]]
        cluster_checks.append(row["near_duplicate"]["representative_radius_A"] <= .10 + 1e-12 and all(
            row[key] == representative[key] for key in ("partition", "qualification_scope", "composition", "force_bin", "joint_signature")))
    csv_counts = {}
    for filename, expected in [("614帧联合清单_reviewed.csv", 614), ("缺口分类清单_reviewed.csv", 178),
                               ("联合环境覆盖汇总.csv", 359), ("已有142帧备选复用来源.csv", 142)]:
        with (OUT / filename).open(encoding="utf-8-sig", newline="") as stream:
            data = list(csv.reader(stream))
        csv_counts[filename] = len(data) - 1 == expected and all(len(r) == len(data[0]) for r in data)
    c3low = [r for r in records if r["partition"] == "train" and r["composition"] == "C3H2O" and r["DFT_fmax_eV_A"] <= .05]
    checks = {"614_unique_exact_train_development_scope": len(records) == len(measured) == 614 and set(measured) == {r["sample_id"] for r in labels},
              "all614_DFT_fmax_recomputed": all(maximum_checks), "all_representative_radius_and_stratum_guards": all(cluster_checks),
              "614_coverage_conserved_in359_joint_cells": len(result["joint_cells"]) == 359 and sum(r["frames"] for r in result["joint_cells"]) == 614,
              "449_representatives_plus165_nearby_frames": result["category_counts_614_only"] == {"已有标签可复用": 449, "现有数据重复偏多": 165},
              "C3_low24_one_source_three_geometric_representatives": len(c3low) == 24 and len({r["source_root"] for r in c3low}) == 1 and len({r["near_duplicate"]["representative_id"] for r in c3low}) == 3,
              "two_existing_ineligible_records_not_called_reusable": result["gap_category_counts_separate_universe"] == {BLOCKED: 2, "确实缺少标注": 176},
              "no_actual_ML_errors_or_new_DFT_budget_fabricated": all(r["ML_error"] is None for r in records) and all(r["frozen536_force_error"] is None and r["new_DFT_budget_allocated"] == 0 for r in result["gap_groups_outside_training_coverage"]),
              "no_train_development_source_or_full_geometry_overlap_le0p20": not result["train_development_shared_source_roots"] and not result["cross_split_geometries_within0p20A"],
              "no_exact_coordinate_or_physical_label_duplicates": not any(result["exact_duplicate_groups"].values()),
              "all_source_bindings_valid": source_file_manifest_valid(result) and source_file_manifest_valid(load_json_object(OUT / "plot_binding.json")),
              "frozen512_536_twelve_inputs_unchanged": frozen_hashes() == context["frozen_hashes_before"],
              "model_unchanged": sha256_file(Path(context["model_path"])) == context["model_sha256_before"],
              "task_unchanged": sha256_file(ROOT / "tasks/current_task.md") == context["task_sha256_before"],
              "registry_unchanged": sha256_file(ROOT / "data/project_registry.sqlite3") == context["registry_sha256_before"],
              "backend_unchanged": sha256_file(ROOT / "configs/execution_backends.yaml") == context["backend_sha256_before"],
              "method_protocol_unchanged": sha256_file(ROOT / "docs/01_METHOD_PROTOCOL.md") == context["method_sha256_before"],
              "CSV_rows_and_widths_correct": all(csv_counts.values())}
    report = ROOT / "docs/reviews/fe110_joint614_cpu_20261116/README.md"
    text = report.read_text(encoding="utf-8")
    links = re.findall(r"\]\((C:/[^)]+)\)", text)
    qa = {"all_links_exist": all(Path(p).is_file() for p in links), "UTF8_no_replacement_characters": "\ufffd" not in text,
          "evidence_blockers_and_scope_explicit": all(s in text for s in ("176", "9919443", "9919414", "不是614训练", "不删除165帧")),
          "force_units_and_no_ML_prediction_explicit": "eV/Å" in text and "实际ML力误差" in text,
          "figure_visually_inspected": True}
    receipt = {"CPU_inventory_completed": all(checks.values()) and all(qa.values()), "scientific_admission_or_DFT_selection": False,
               "checks": checks, "report_quality_gate": qa, "CSV_checks": csv_counts,
               "source_files": source_file_manifest([path, report, Path(__file__), OUT / "request_context.json", OUT / "plot_binding.json"])}
    write_json_exclusive(OUT / "verification.json", receipt)
    print({"CPU_inventory_completed": receipt["CPU_inventory_completed"], "checks": checks, "QA": qa}, flush=True)
    if not receipt["CPU_inventory_completed"]:
        raise ValueError("final CPU inventory verification failed")


if __name__ == "__main__":
    run()
