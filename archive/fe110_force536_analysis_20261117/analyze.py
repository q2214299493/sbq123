"""Compare existing frozen536 vectors with qualified same-coordinate DFT labels."""
from __future__ import annotations

from collections import defaultdict
import csv
from pathlib import Path

import numpy as np

from archive.fe110_force_diagnosis536_20261114.analyze import diagnose, validate_packet, vector_metrics
from scripts.artifact_io import load_json_object, source_file_manifest, source_file_manifest_valid, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUT = BASE / "force_diagnosis536_analysis_20261117_v1"
STRICT = "STRICT_RAW_E_F_LOCALMAG"
ROLE_NAMES = {"adsorbate_C": "吸附C", "adsorbate_O": "吸附O", "adsorbate_H": "吸附H", "near_Fe": "近邻Fe", "other_Fe": "其他Fe", "all_movable_Fe": "全部可动Fe", "all_movable": "全部可动原子"}


def roles(row):
    free = sorted(set(range(len(row["symbols"]))) - set(row["fixed_atom_indices_0based"]))
    result = dict(row["force_role_groups"])
    if sorted(i for indices in result.values() for i in indices) != free:
        raise ValueError("roles do not partition movable atoms")
    result["all_movable_Fe"] = sorted(result["near_Fe"] + result["other_Fe"])
    result["all_movable"] = free
    return result


def subset_keys(row, joined):
    phases = ["ALL", row["force_stage"]]
    if row["DFT_movable_fmax_eV_A"] <= .05:
        phases.append("near_le0p05")
    populations = ["all_frames"]
    if joined["near_duplicate"]["representative_id"] == row["sample_id"]:
        populations.append("radius_representatives")
    if joined["adsorbate_component_count"] == 1 and joined["carbon_backbone_connected"]:
        populations.append("intact_connected")
    if joined["component_formulas"] == ["C2H2", "CO"]:
        populations.append("CO_plus_C2H2")
    return [(row["partition"], scope, composition, phase, population)
            for scope in ("ALL", row["qualification_scope"]) for composition in ("ALL", row["composition"])
            for phase in phases for population in populations]


def bucket():
    return {"target": [], "predicted": [], "frames": set(), "roots": set(), "per_frame_MAE": [], "root_MAE": defaultdict(list)}


def summarize_bucket(key, value):
    result = vector_metrics(np.concatenate(value["target"]), np.concatenate(value["predicted"]))
    return {"partition": key[0], "qualification_scope": key[1], "composition": key[2], "force_stage": key[3], "population": key[4], "role": key[5],
            "frames": len(value["frames"]), "source_roots": len(value["roots"]),
            "frame_balanced_vector_MAE_eV_A": float(np.mean(value["per_frame_MAE"])),
            "source_balanced_frame_vector_MAE_eV_A": float(np.mean([np.mean(v) for v in value["root_MAE"].values()])), **result}


def frame_record(row, target, predicted, joined):
    groups = roles(row)
    free = groups["all_movable"]
    errors = np.linalg.norm(predicted - target, axis=1)
    dft = np.linalg.norm(target, axis=1)
    ml = np.linalg.norm(predicted, axis=1)
    role_map = {i: role for role, indices in row["force_role_groups"].items() for i in indices}
    maximum = max(free, key=lambda i: errors[i])
    max_dft = max(free, key=lambda i: dft[i])
    max_ml = max(free, key=lambda i: ml[i])
    return {"sample_id": row["sample_id"], "partition": row["partition"], "qualification_scope": row["qualification_scope"], "composition": row["composition"],
            "force_stage": row["force_stage"], "source_root": joined["source_root"], "source_job_id": row["source_job_id"],
            "structure_sha256": row["structure_sha256"], "physical_label_key": row["physical_label_key"],
            "component_formulas": joined["component_formulas"], "carbon_backbone_connected": joined["carbon_backbone_connected"],
            "joint_signature": joined["joint_signature"], "near_duplicate_representative": joined["near_duplicate"]["representative_id"],
            "groups": {role: vector_metrics(target[indices], predicted[indices]) for role, indices in groups.items() if indices},
            "DFT_fmax_eV_A": float(dft[max_dft]), "ML_fmax_eV_A": float(ml[max_ml]),
            "maximum_error_atom_1based": maximum + 1, "maximum_error_role": role_map[maximum], "maximum_error_eV_A": float(errors[maximum]),
            "maximum_DFT_force_atom_1based": max_dft + 1, "maximum_DFT_force_role": role_map[max_dft],
            "maximum_ML_force_atom_1based": max_ml + 1, "maximum_ML_force_role": role_map[max_ml],
            "ML_le0p05_DFT_gt0p10": bool(ml[max_ml] <= .05 and dft[max_dft] > .10),
            "ML_le0p10_DFT_gt0p10_secondary": bool(ml[max_ml] <= .10 and dft[max_dft] > .10),
            "original_weighted_vector_MAE_eV_A": float(np.average(errors[free], weights=np.asarray(row["original_per_atom_weights"])[free])),
            "same_coordinate_DFT_label_exists": True, "new_DFT_for_this_coordinate_needed": False}


def atom_rows(row, target, predicted, joined):
    for role, indices in row["force_role_groups"].items():
        for i in indices:
            norm_dft, norm_ml = float(np.linalg.norm(target[i])), float(np.linalg.norm(predicted[i]))
            cosine = float(np.dot(target[i], predicted[i]) / norm_dft / norm_ml) if min(norm_dft, norm_ml) > 1e-8 else None
            yield [row["sample_id"], row["partition"], row["qualification_scope"], row["composition"], joined["source_root"], row["force_stage"],
                   i + 1, row["symbols"][i], role, *target[i].tolist(), *predicted[i].tolist(), float(np.linalg.norm(predicted[i] - target[i])), norm_dft, norm_ml, cosine, row["structure_sha256"]]


def run():
    labels_path = BASE / "force_diagnosis536_20261114_v1/qualified_reference_labels.json"
    predicted_path = BASE / "force_diagnosis536_gpu_20261117_v4/returned/predictions614.json"
    proof_path = BASE / "force_diagnosis536_gpu_20261117_v4/return_verification.json"
    joint_path = BASE / "joint614_cpu_audit_20261116_v1/joint_inventory_reviewed.json"
    labels_doc, proof = load_json_object(labels_path), load_json_object(proof_path)
    if not proof["all_checks_passed"] or not source_file_manifest_valid(proof) or not source_file_manifest_valid(labels_doc):
        raise ValueError("source validation or prediction-return binding changed")
    context = load_json_object(OUT / "request_context.json")
    references, packet = labels_doc["records"], load_json_object(predicted_path)
    data = validate_packet(references, packet, context["model_sha256_before"])
    joint = {r["sample_id"]: r for r in load_json_object(joint_path)["records"]}
    if len(data) != 614 or set(joint) != {r["sample_id"] for r in references}:
        raise ValueError("joint environment inventory is not the same614 inputs")
    grouped, frames, atom_count = defaultdict(bucket), [], 0
    with (OUT / "逐原子力比较.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["结构ID", "分区", "标签资格", "组成", "来源根", "DFT力区间", "原子序号1起", "元素", "原子角色", "DFT_Fx", "DFT_Fy", "DFT_Fz", "ML_Fx", "ML_Fy", "ML_Fz", "向量误差_eV每A", "DFT力范数_eV每A", "ML力范数_eV每A", "非零力方向余弦", "坐标SHA256"])
        for row, target, predicted in data:
            joined = joint[row["sample_id"]]
            if joined["structure_sha256"] != row["structure_sha256"] or joined["partition"] != row["partition"]:
                raise ValueError("environment join coordinates or partition mismatch")
            frames.append(frame_record(row, target, predicted, joined))
            for values in atom_rows(row, target, predicted, joined):
                writer.writerow(values)
                atom_count += 1
            for role, indices in roles(row).items():
                if not indices:
                    continue
                a, b = target[indices], predicted[indices]
                mae = float(np.linalg.norm(b - a, axis=1).mean())
                for key in subset_keys(row, joined):
                    value = grouped[key + (role,)]
                    value["target"].append(a)
                    value["predicted"].append(b)
                    value["frames"].add(row["sample_id"])
                    value["roots"].add(joined["source_root"])
                    value["per_frame_MAE"].append(mae)
                    value["root_MAE"][joined["source_root"]].append(mae)
    metrics = [summarize_bucket(key, value) for key, value in sorted(grouped.items())]
    cache_path = BASE / "force_diagnosis536_20261114_v1/cached_development_role_metrics.json"
    cached = load_json_object(cache_path)
    fresh_weighted = float(np.mean([r["original_weighted_vector_MAE_eV_A"] for r in frames if r["partition"] == "development"]))
    old_weighted = cached["native_role_weighted_per_frame_vector_MAE_eV_A"]
    reconciliation = {"cached_development_role_weighted_vector_MAE_eV_A": old_weighted, "current_ASE_development_role_weighted_vector_MAE_eV_A": fresh_weighted,
                      "current_minus_cache_percent": 100 * (fresh_weighted / old_weighted - 1),
                      "status": "NOT_EXACTLY_REPRODUCED;CACHE_AND_ASE_PREDICTIONS_REPORTED_SEPARATELY", "cause": "Needs confirmation;not a model improvement because checkpoint unchanged"}
    result = {"frames": frames, "summary_metrics": metrics, "movable_atom_comparisons": atom_count, "cache_reconciliation": reconciliation,
              "primary_flagged_frames": [r for r in frames if r["ML_le0p05_DFT_gt0p10"]],
              "secondary_flagged_frames": [r for r in frames if r["ML_le0p10_DFT_gt0p10_secondary"]],
              "model_sha256": context["model_sha256_before"], "units": "forces/vector errors:eV/Angstrom;SSE:(eV/Angstrom)^2;cosine:dimensionless",
              "definitions": {"vector_RMSE": "sqrt(mean_i ||F_ML_i-F_DFT_i||^2)", "vector_MAE": "mean_i ||F_ML_i-F_DFT_i||", "component_MAE": "mean over all xyz absolute component errors",
                              "source_balanced_MAE": "equal-source mean of within-source equal-frame per-atom vector MAE;descriptive sensitivity only", "direction_minimum_norm_eV_A": 1e-8},
              "no_training_DFT_optimization_or_new_inference": True, "heldout_or_quarantine_used": False,
              "source_files": source_file_manifest([Path(__file__), labels_path, predicted_path, proof_path, joint_path, cache_path, OUT / "request_context.json"])}
    write_json_exclusive(OUT / "same_coordinate_force_diagnosis.json", result)
    write_json_exclusive(OUT / "original_analyzer_crosscheck.json", diagnose(references, packet, context["model_sha256_before"]))
    write_tables(result)
    print({"frames": len(frames), "movable_atom_comparisons": atom_count, "summary_groups": len(metrics), "primary_flags": [r["sample_id"] for r in result["primary_flagged_frames"]], "cache": reconciliation}, flush=True)


def write_tables(result):
    with (OUT / "误差分组汇总.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        fields = ["partition", "qualification_scope", "composition", "force_stage", "population", "role", "frames", "source_roots", "atom_observations", "vector_RMSE_eV_A", "vector_MAE_eV_A", "component_MAE_eV_A", "maximum_vector_error_eV_A", "mean_cosine_nonzero", "reversed_direction_fraction_nonzero", "sum_squared_vector_error", "frame_balanced_vector_MAE_eV_A", "source_balanced_frame_vector_MAE_eV_A"]
        writer.writerow(fields)
        writer.writerows([[r[k] for k in fields] for r in result["summary_metrics"]])
    with (OUT / "逐帧力误差及交接风险.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        fields = ["sample_id", "partition", "qualification_scope", "composition", "source_root", "DFT_fmax_eV_A", "ML_fmax_eV_A", "maximum_DFT_force_role", "maximum_error_eV_A", "maximum_error_role", "ML_le0p05_DFT_gt0p10", "near_duplicate_representative"]
        writer.writerow(fields)
        writer.writerows([[r[k] for k in fields] for r in result["frames"]])


if __name__ == "__main__":
    run()
