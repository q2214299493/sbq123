"""Join existing force errors, geometry gaps and path sources without model calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
MODEL = BASE / "training536_execution_20261113_v4/returned/candidate.pt"
MODEL_SHA = "2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0"
SLAB = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
ROLES = ("adsorbate_C", "adsorbate_O", "adsorbate_H", "near_Fe", "other_Fe")
CRITICAL = ("adsorbate_C", "adsorbate_O", "near_Fe")
REUSE, REPEAT, MISSING = "已有标签可复用", "现有数据重复偏多", "确实缺少标注"
BLOCKED = "已有记录但尚不可复用"
INPUTS = {
    "joint": BASE / "joint614_cpu_audit_20261116_v1/joint_inventory_reviewed.json",
    "errors": BASE / "force_diagnosis536_analysis_20261117_v1/same_coordinate_force_diagnosis.json",
    "geometry": BASE / "c2_c4_joint_candidates_20261114_v1/coordinate_site_isolation_audit_v4.json",
    "paths": BASE / "c2_c4_joint_candidates_20261114_v1/reaction_path_reuse_audit.json",
    "network": BASE / "c2_c4_gap_inventory_20261114_v1/reaction_network_sources.json",
    "bindings": BASE / "c2_c4_gap_inventory_20261114_v1/reico_pool_label_bindings_v3.json",
    "costs": BASE / "c2_c4_joint_candidates_20261114_v1/static_cost_references.json",
    "c3_seeds": BASE / "c3_independent_validation_proposal_20261113_v1/proposal_evidence.json",
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def table(path, rows, columns):
    with Path(path).open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([label for _, label in columns])
        for row in rows:
            values = [row.get(key) for key, _ in columns]
            writer.writerow([json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v for v in values])


def guard_hashes():
    names = ("training_manifest.json", "train.db", "development.db", "train_metadata.npz", "development_metadata.npz", "package_inventory.json")
    paths = [BASE / folder / name for folder in ("combined_force_package_20261027_v3", "combined_force_package_20261113_v1") for name in names]
    paths += [MODEL, ROOT / "tasks/current_task.md", ROOT / "docs/01_METHOD_PROTOCOL.md", ROOT / "configs/execution_backends.yaml"]
    return {str(path): sha(path) for path in paths}


def critical_error(frame):
    return max((frame["groups"].get(role, {}).get("vector_RMSE_eV_A", 0.) or 0. for role in CRITICAL), default=0.)


def carbon_count(composition):
    match = re.search(r"C(\d*)", composition)
    return int(match.group(1) or 1) if match else 0


def priority(frame):
    if frame["ML_le0p05_DFT_gt0p10"] or (frame["DFT_fmax_eV_A"] <= .02 < frame["ML_fmax_eV_A"]):
        return "P0_同坐标阈值失配先复用"
    if (frame["DFT_fmax_eV_A"] <= .10 and critical_error(frame) >= .05) or critical_error(frame) >= .10:
        return "P1_已有标签误差复核"
    return "P2_常规覆盖保留"


def join_frames(joint, errors):
    index = {r["sample_id"]: r for r in errors}
    if len(index) != len(errors) or {r["sample_id"] for r in joint} != set(index):
        raise ValueError("force/environment IDs are not a one-to-one join")
    result = []
    for original in joint:
        error = index[original["sample_id"]]
        for key in ("partition", "composition", "qualification_scope", "structure_sha256", "physical_label_key", "joint_signature"):
            if original[key] != error[key]:
                raise ValueError(f"force/environment binding mismatch: {original['sample_id']}:{key}")
        if not error["same_coordinate_DFT_label_exists"] or error["new_DFT_for_this_coordinate_needed"]:
            raise ValueError("same-coordinate label qualification changed")
        if original["partition"] not in ("train", "development"):
            raise ValueError("heldout/quarantine must not enter error selection")
        if abs(original["DFT_fmax_eV_A"] - error["DFT_fmax_eV_A"]) > 1e-10:
            raise ValueError("DFT force magnitude binding changed")
        row = {**original, "actual_error": error, "error_priority": priority(error),
               "critical_role_RMSE_eV_A": critical_error(error), "new_DFT_needed": False,
               "path_evidence": "已有优化/静态标签；单帧连接图不证明反应路径",
               "inverse_threshold_flag": error["DFT_fmax_eV_A"] <= .02 < error["ML_fmax_eV_A"]}
        result.append(row)
    return result


def environment_groups(frames):
    groups = defaultdict(list)
    for row in frames:
        groups[(row["partition"], row["composition"], row["qualification_scope"], row["force_bin"], row["joint_signature"])].append(row)
    result = []
    for key, rows in sorted(groups.items()):
        metrics = {}
        for role in ROLES:
            parts = [(r, r["actual_error"]["groups"][role]) for r in rows if r["actual_error"]["groups"].get(role, {}).get("atom_observations", 0)]
            count = sum(m["atom_observations"] for _, m in parts)
            roots = defaultdict(list)
            for r, m in parts:
                roots[r["source_root"]].append(m["vector_MAE_eV_A"])
            metrics[role] = {"atoms": count,
                             "vector_RMSE_eV_A": math.sqrt(sum(m["sum_squared_vector_error"] for _, m in parts) / count) if count else None,
                             "vector_MAE_eV_A": sum(m["vector_MAE_eV_A"] * m["atom_observations"] for _, m in parts) / count if count else None,
                             "source_balanced_frame_MAE_eV_A": sum(sum(v) / len(v) for v in roots.values()) / len(roots) if roots else None}
        result.append({"partition": key[0], "composition": key[1], "qualification_scope": key[2], "force_bin": key[3],
                       "joint_signature": key[4], "frames": len(rows), "source_roots": len({r["source_root"] for r in rows}),
                       "representatives": len({r["actual_error"]["near_duplicate_representative"] for r in rows}),
                       "sample_ids": [r["sample_id"] for r in rows], "role_metrics": metrics,
                       "primary_flags": sum(r["actual_error"]["ML_le0p05_DFT_gt0p10"] for r in rows),
                       "inverse_flags": sum(r["inverse_threshold_flag"] for r in rows),
                       "largest_actual_critical_error_eV_A": max(r["critical_role_RMSE_eV_A"] for r in rows),
                       "new_DFT_needed_for_existing_coordinates": False})
    return result


def reference_context(candidate, frame_index):
    """A neighbor's observed error is never the unlabelled candidate's error."""
    nearest = candidate["isolation"]["train536"]
    name = nearest.get("reference_id")
    if name not in frame_index or frame_index[name]["partition"] != "train":
        raise ValueError("candidate context must bind an actual training prediction")
    ref = frame_index[name]
    return {"reference_id": name, "reference_structure_sha256": ref["structure_sha256"],
            "reference_full_RMSD_A": nearest["full_RMSD_A"],
            "reference_actual_critical_RMSE_eV_A": ref["critical_role_RMSE_eV_A"],
            "reference_qualification": ref["qualification_scope"],
            "reference_same_graph": candidate["geometry"]["environment"]["graph_signature"] == ref["graph_signature"],
            "candidate_actual_ML_DFT_error_eV_A": None,
            "meaning": "仅为邻近已标注训练结构的实测误差上下文；不外推候选误差或不确定度"}


def candidate_rows(records, frames, joint):
    index = {r["sample_id"]: r for r in frames}
    covered = defaultdict(lambda: defaultdict(set))
    for row in joint:
        if row["partition"] == "train":
            for scale, signature in row["joint_by_scale"].items():
                covered[row["composition"]][scale].add(signature)
    result = []
    for row in records:
        context = reference_context(row, index)
        all_scales = all(sig not in covered[row["composition"]][scale] for scale, sig in row["joint_by_scale"].items())
        near = context["reference_full_RMSD_A"] < .10
        blocked = bool(row["new_SP_review_blockers"])
        result.append({**row, "category": BLOCKED if blocked else MISSING, "error_context": context,
                       "candidate_actual_ML_DFT_error_eV_A": None, "candidate_DFT_fmax_eV_A": None,
                       "candidate_robust_missing_all_scales": all_scales,
                       "near_existing_training_geometry_below0p10A": near,
                       "low_incremental_geometry_value": near and not all_scales,
                       "target_role": "REICO离平衡连接/Fe配位补充；不是已验证路径或独立近稳定验收",
                       "priority": "BLOCKED_先审已有记录" if blocked else "P2_条件补标候选",
                       "selected_rank": None, "new_DFT_budget_allocated": 0,
                       "new_training_admission": False})
    return result


def ordering_key(row, selected):
    return (not row["candidate_robust_missing_all_scales"],
            row["composition"] in {r["composition"] for r in selected},
            -row["error_context"]["reference_actual_critical_RMSE_eV_A"],
            -row["robust_missing_frames_all_scales"], -row["pool_frames_of_joint_type"], row["candidate_id"])


def select_candidates(rows, paths):
    from archive.fe110_c2_c4_joint_candidates_20261114.geometry import iron_maps, nearest, packed_pose
    from scripts.adsorption.build_fe110_adsorption import read_poscar
    from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries

    slab = read_poscar(SLAB)
    operations = surface_pose_symmetries(slab)
    maps = iron_maps(slab, operations)
    path_refs = []
    for row in paths["newly_bound_existing_first_steps"] + paths["existing_last_step_labels"]:
        path = Path(row["structure_path"])
        path_refs.append({**packed_pose(read_poscar(path), operations, maps), "id": row.get("candidate_id", row.get("sample_id")), "source": str(path)})
    selected, packed, deferred = [], [], []
    remaining = []
    for row in rows:
        reason = None
        if row["category"] == BLOCKED:
            reason = "已有同坐标记录先完成原QC；不原样重算"
        elif row["family_risk_note"]:
            reason = "同家族历史SCF/磁性失败；仅递延，不认定本坐标必然失败"
        elif row["low_incremental_geometry_value"]:
            reason = "距已有训练几何<0.10Å且缺口不稳健；先复用邻近标签诊断"
        if reason:
            row["deferred_reason"] = reason
            deferred.append({"candidate_id": row["candidate_id"], "reason": reason})
        else:
            remaining.append(row)
    while remaining:
        remaining.sort(key=lambda r: ordering_key(r, selected))
        row = remaining.pop(0)
        if len(selected) >= 20:
            row["deferred_reason"] = "超出本次最多20个条件备选；不是无价值"
            deferred.append({"candidate_id": row["candidate_id"], "reason": row["deferred_reason"]})
            continue
        if row["family_id"] in {r["family_id"] for r in selected}:
            row["deferred_reason"] = "首批同轨迹家族仅保留一个代表"
            deferred.append({"candidate_id": row["candidate_id"], "reason": row["deferred_reason"]})
            continue
        pose = read_poscar(Path(row["source_path"]))
        close = nearest(pose, packed)
        path_close = nearest(pose, path_refs)
        if close["full_RMSD_A"] is not None and close["full_RMSD_A"] < .10:
            reason = "与先选候选的含可动Fe表面对称距离<0.10Å"
        elif path_close["full_RMSD_A"] is not None and path_close["full_RMSD_A"] <= 1e-7:
            reason = "可能等价于已有路径标签；先审原子映射，不新增同坐标单点"
        else:
            reason = None
        if reason:
            row["deferred_reason"] = reason
            deferred.append({"candidate_id": row["candidate_id"], "reason": reason})
            continue
        row.update(selected_rank=len(selected) + 1, nearest_selected=close, nearest_existing_path=path_close)
        row["priority"] = "P2a_前10条件备选" if len(selected) < 10 else "P2b_后备11至20"
        selected.append(row)
        packed.append({**packed_pose(pose, operations, maps), "id": row["candidate_id"], "source": row["source_path"]})
    return selected, deferred, len(operations)


def path_rows(doc, frames):
    result = []
    physical = {r["physical_label_key"]: r for r in frames}
    for group in ("newly_bound_existing_first_steps", "existing_last_step_labels", "existing_C_H_labels", "additional_paper_physical_labels"):
        for number, row in enumerate(doc[group]):
            key = row.get("physical_label_key")
            if not key and row.get("OUTCAR_sha256") and row.get("DFT_ionic_step") is not None:
                key = f"{row['OUTCAR_sha256']}:{row['DFT_ionic_step']}"
            protected = bool(row.get("protected_TS_validation")) or row.get("partition") in ("heldout", "quarantine", "validation")
            paper = group == "additional_paper_physical_labels"
            match = physical.get(key)
            result.append({"record_id": row.get("candidate_id", row.get("sample_id", f"paper_label_{number+1:02d}")),
                           "source_group": group, "source_id_not_new_structure": True,
                           "structure_path": row.get("structure_path", row.get("structure")),
                           "source_OUTCAR_path": row.get("OUTCAR_path", row.get("source_OUTCAR_path", row.get("outcar"))),
                           "physical_label_key": key, "partition": row.get("partition"),
                           "protected": protected, "category": "保护验证来源_不进入训练" if protected else BLOCKED,
                           "chemical_event": row.get("chemical_event", "CH+CO已有训练标签；跨后端兼容性待审"),
                           "monitored_C_C_distance_A": row.get("monitored_C_C_distance_A"),
                           "actual_error_from_same_physical_label": match["actual_error"] if match else None,
                           "blockers": "跨后端、磁性及新包准入仍需审核" if paper else "保留原磁性资格；不自动提升为完整局域磁矩证据",
                           "priority": "PROTECTED" if protected else "P0_已有路径标签先复核",
                           "new_DFT_for_same_coordinate": False, "new_training_admission": False})
    return result


def symbolic_rows(network):
    result = []
    for row in network["records"]:
        scopes = [int(v) for v in row["target_carbon_groups"] if int(v) in (2, 3, 4)]
        if not scopes or not 2 <= row["total_C_each_side"] <= 4:
            continue
        result.append({**row, "target_scopes_this_audit": scopes,
                       "category": "来源待绑定_不能据此断言无标签", "priority": "P1_先绑定真实路径坐标",
                       "actual_ML_DFT_error_eV_A": None,
                       "related_existing_path": "CH+CO实有路径标签另表列出；关系不等于本反应已验收" if "CH* + CO*" in row["reaction"] else None,
                       "new_DFT_budget_allocated": 0})
    return result


def master_rows(result):
    rows = []
    for frame in result["frames"]:
        if 2 <= carbon_count(frame["composition"]) <= 4 and frame["error_priority"].startswith("P0"):
            error = frame["actual_error"]
            rows.append({"priority": frame["error_priority"], "record_id": frame["sample_id"], "composition": frame["composition"],
                         "category": frame["category"], "object_type": "已标注固定坐标", "partition": frame["partition"],
                         "structure_path": frame["structure_path"], "structure_sha256": frame["structure_sha256"],
                         "actual_error_at_this_coordinate_eV_A": error["maximum_error_eV_A"],
                         "label_status": frame["qualification_scope"], "next_action": "开发仅评估" if frame["partition"] == "development" else "复用原训练标签诊断；不另算相同坐标",
                         "new_DFT_budget_allocated": 0})
    for composition, count in sorted(Counter(r["composition"] for r in result["backup_labels"]).items()):
        rows.append({"priority": "P0_包外标签先复用审核", "record_id": f"existing_backup_{composition}", "composition": composition,
                     "category": REUSE, "object_type": "已有兼容备选标签组", "records": count,
                     "actual_error_at_this_coordinate_eV_A": None, "label_status": "来源兼容证据已绑定；非新包自动准入",
                     "next_action": "保持原训练侧血缘；不占新单点、不作为独立验收", "new_DFT_budget_allocated": 0})
    rows.append({"priority": "P0_已有路径标签先复核", "record_id": "CHCO_first_and_last_12_references", "composition": "C2HO",
                 "category": BLOCKED, "object_type": "已有真实路径原子力", "records": 12,
                 "actual_error_at_this_coordinate_eV_A": None, "label_status": "原局域磁性缺口保留",
                 "next_action": "复核已有原子力/坐标/磁性；不重复12个坐标DFT", "new_DFT_budget_allocated": 0})
    rows.append({"priority": "P0_跨后端已有标签审核", "record_id": "paper_CHCO_10_physical_label_references", "composition": "C2HO",
                 "category": BLOCKED, "object_type": "另一训练家族已有物理标签", "records": 10,
                 "actual_error_at_this_coordinate_eV_A": None, "label_status": "跨后端兼容性及磁性不得自动继承",
                 "next_action": "先审核来源兼容性；整个训练家族不作独立盲验收", "new_DFT_budget_allocated": 0})
    for target in result["mainline_source_gaps"]:
        rows.append({"priority": target["priority"], "record_id": target["target"], "composition": "C3H2O" if "C3" in target["target"] else "C4",
                     "category": "来源待绑定或验收缺口", "object_type": "主线目标缺口",
                     "actual_error_at_this_coordinate_eV_A": None, "label_status": target["status"],
                     "next_action": "先完成真实坐标、异构体、位点及用途绑定；不强凑单点数", "new_DFT_budget_allocated": 0})
    for candidate in result["selected_conditional_candidates"]:
        rows.append({"priority": candidate["priority"], "record_id": candidate["candidate_id"], "composition": candidate["composition"],
                     "category": MISSING, "object_type": "真实坐标条件补标备选", "partition": "训练侧候选_未准入",
                     "structure_path": candidate["source_path"], "structure_sha256": candidate["source_sha256"],
                     "actual_error_at_this_coordinate_eV_A": None, "reference_error_context": candidate["error_context"],
                     "label_status": candidate["prior_label_status"], "next_action": "逐项科学复核后再决定是否申请一个单点；不是已批准批次",
                     "new_DFT_budget_allocated": 0})
    return sorted(rows, key=lambda r: (r["priority"], r["record_id"]))


def source_check(documents):
    bound = {str(p): sha(p) for p in INPUTS.values()}
    # Revalidate immutable primary evidence bindings without regenerating any analysis.
    for name in ("errors", "joint", "geometry", "paths", "network", "c3_seeds", "costs"):
        for row in documents[name].get("source_files", []):
            path, expected = row["path"], row["sha256"]
            actual = bound.get(path)
            if actual is None:
                actual = sha(path)
                bound[path] = actual
            if actual != expected:
                raise ValueError(f"upstream source binding changed: {path}")
    return bound


def write_outputs(out, result):
    table(out / "联合总优先表.csv", result["master_priorities"], [("priority", "优先级"), ("record_id", "记录或候选ID"), ("composition", "组成或范围"), ("category", "类别"), ("object_type", "对象类型"), ("partition", "用途分区"), ("records", "组内记录数"), ("structure_path", "真实坐标路径"), ("structure_sha256", "坐标SHA256"), ("actual_error_at_this_coordinate_eV_A", "本坐标实测最大误差_未知留空_eV每A"), ("reference_error_context", "邻近参考误差_不赋给候选"), ("label_status", "标签或来源状态"), ("next_action", "建议处置"), ("new_DFT_budget_allocated", "本轮分配DFT数")])
    frame_table = []
    for r in result["frames"]:
        e = r["actual_error"]
        frame_table.append({**r, "ML_fmax": e["ML_fmax_eV_A"], "max_error": e["maximum_error_eV_A"],
                            "max_error_role": e["maximum_error_role"], "primary_flag": e["ML_le0p05_DFT_gt0p10"],
                            "role_errors": {role: e["groups"].get(role) for role in ROLES}})
    table(out / "614帧误差环境联合表.csv", frame_table, [("sample_id", "结构ID"), ("partition", "分区"), ("composition", "组成"), ("qualification_scope", "标签资格"), ("source_root", "来源根"), ("structure_sha256", "坐标SHA256"), ("physical_label_key", "物理标签键"), ("category", "清单类别"), ("error_priority", "误差复核优先级"), ("force_bin", "DFT力区间"), ("DFT_fmax_eV_A", "DFT最大力_eV每A"), ("ML_fmax", "ML最大力_eV每A"), ("max_error", "最大向量误差_eV每A"), ("max_error_role", "最大误差角色"), ("primary_flag", "小ML力大DFT力"), ("inverse_threshold_flag", "DFT过0p02但ML未过"), ("component_formulas", "连接组分"), ("carbon_backbone_connected", "碳骨架连通"), ("joint_signature", "连接配位签名"), ("near_duplicate", "来源去冗余"), ("role_errors", "逐角色实测误差"), ("new_DFT_needed", "同坐标需新DFT")])
    table(out / "化学环境实测误差优先表.csv", result["environment_groups"], [("partition", "分区"), ("composition", "组成"), ("qualification_scope", "标签资格"), ("force_bin", "DFT力区间"), ("joint_signature", "连接配位签名"), ("frames", "帧数"), ("source_roots", "来源根数"), ("representatives", "几何代表数"), ("primary_flags", "小ML力大DFT力帧数"), ("inverse_flags", "DFT过0p02但ML未过帧数"), ("role_metrics", "角色误差及来源均衡统计"), ("sample_ids", "成员ID"), ("new_DFT_needed_for_existing_coordinates", "现有坐标需新DFT")])
    candidates = []
    for r in result["candidate_audit"]:
        candidates.append({**r, **{f"neighbor_{k}": v for k, v in r["error_context"].items()},
                           "components": r["geometry"]["graph"]["adsorbate_components"],
                           "largest_C_component": r["geometry"]["graph"]["largest_C_C_connected_component"],
                           "binding_sites": r["geometry"]["binding_sites"]})
    columns = [("selected_rank", "条件备选顺序"), ("priority", "优先级"), ("candidate_id", "候选ID"), ("composition", "组成"), ("family_id", "来源家族"), ("category", "类别"), ("source_path", "真实坐标路径"), ("source_sha256", "坐标SHA256"), ("prior_label_status", "已有同坐标标签状态"), ("candidate_actual_ML_DFT_error_eV_A", "候选自身实测误差_未知留空"), ("candidate_DFT_fmax_eV_A", "候选DFT最大力_未知留空"), ("candidate_robust_missing_all_scales", "候选三档阈值均缺覆盖"), ("neighbor_reference_id", "邻近已标注训练参考ID"), ("neighbor_reference_full_RMSD_A", "与参考的对称距离_A"), ("neighbor_reference_actual_critical_RMSE_eV_A", "仅参考结构的CO近Fe最大角色RMSE_eV每A"), ("neighbor_reference_qualification", "参考标签资格"), ("neighbor_reference_same_graph", "与参考连接图相同"), ("near_existing_training_geometry_below0p10A", "距已有训练几何小于0p10A"), ("family_risk_note", "家族历史风险"), ("components", "吸附质组分数"), ("largest_C_component", "最大碳连通分量"), ("binding_sites", "逐原子成键位点"), ("deferred_reason", "递延原因"), ("new_DFT_budget_allocated", "本轮分配DFT数")]
    table(out / "67候选审核及误差上下文.csv", candidates, columns)
    table(out / "补标条件候选与预算.csv", sorted([r for r in candidates if r["selected_rank"]], key=lambda r: r["selected_rank"]), columns + [("conditional_median_core_hours", "历史中位参考核时"), ("conditional_cap_core_hours", "条件预算上限核时")])
    table(out / "反应路径已有标签复用表.csv", result["path_labels"], [("record_id", "原记录ID"), ("source_group", "来源组"), ("physical_label_key", "物理标签键"), ("structure_path", "坐标路径"), ("source_OUTCAR_path", "原OUTCAR路径"), ("category", "类别"), ("protected", "保护验证来源"), ("chemical_event", "来源声明的化学过程"), ("monitored_C_C_distance_A", "所监测CC距离_A"), ("blockers", "准入边界"), ("new_DFT_for_same_coordinate", "相同坐标需新DFT"), ("priority", "优先级")])
    table(out / "C2至C4反应路径来源缺口.csv", result["symbolic_path_gaps"], [("directed_id", "原反应记录ID"), ("reaction", "来源反应式"), ("total_C_each_side", "本步各侧总碳数"), ("largest_single_formula_C_each_side", "各侧最大单一分子式碳数_非连接证明"), ("target_scopes_this_audit", "来源路径目标碳数_非本步骨架"), ("source_nominal_family", "来源名义反应族"), ("source_file", "来源文件"), ("path_ids", "来源路径ID"), ("geometry_path", "已绑定真实路径坐标"), ("category", "状态"), ("priority", "优先级"), ("actual_ML_DFT_error_eV_A", "同坐标实际误差_未知留空"), ("new_DFT_budget_allocated", "本轮分配DFT数")])
    table(out / "C3验收种子与阻塞.csv", result["protected_C3_seed_sources"], [("candidate_id", "原种子ID"), ("exact_smiles", "原异构体SMILES"), ("proposed_pose_file", "已有Fe45真实坐标_无则空"), ("proposed_pose_kind", "坐标来源性质"), ("proposed_role", "原拟用途_保持不变"), ("same_coordinate_compatible_DFT_label", "同坐标兼容标签现状"), ("graph", "原连接图证据"), ("is_verified_nearstable_frame", "是否已证明近稳定"), ("new_DFT_budget_allocated", "本轮分配DFT数")])
    table(out / "178缺口类型处置表.csv", result["environment_gaps"], [("gap_id", "缺口ID"), ("composition", "组成"), ("category", "类别"), ("joint_signature", "连接配位签名"), ("pool_frames", "池内帧数"), ("pool_families", "家族数"), ("existing_labeled_members", "已有记录"), ("unlabeled_sample_ids", "无标签成员ID"), ("joined_candidate_ids", "本轮已审几何代表"), ("selected_candidate_ids", "条件备选ID"), ("frozen536_force_error", "缺口候选自身误差_未知留空"), ("new_DFT_budget_allocated", "本轮分配DFT数")])
    table(out / "142包外标签复用表.csv", result["backup_labels"], [("candidate_id", "原候选ID"), ("composition", "组成"), ("family_id", "家族"), ("physical_label_key", "物理标签键"), ("structure_path", "坐标路径"), ("structure_sha256", "坐标SHA256"), ("source_job_id", "原DFT作业"), ("DFT_ionic_step", "原DFT步"), ("coordinate_force_match", "原坐标力绑定"), ("raw_positive_Fe_local_moments", "原局域Fe磁性证据"), ("permitted_use", "原许可范围"), ("actual_error_available", "是否已有本536同坐标误差"), ("new_DFT_for_same_compatible_label", "相同兼容标签需新DFT")])


def run(out):
    if out.exists() or not out.resolve().is_relative_to(BASE):
        raise ValueError("a fresh audit output under the calculation authority is required")
    frozen_before = guard_hashes()
    if sha(MODEL) != MODEL_SHA:
        raise ValueError("frozen536 checkpoint changed")
    docs = {name: load(path) for name, path in INPUTS.items()}
    bound = source_check(docs)
    bound[str(Path(__file__).resolve())] = sha(__file__)
    frames = join_frames(docs["joint"]["records"], docs["errors"]["frames"])
    if len(frames) != 614 or Counter(r["partition"] for r in frames) != {"train": 536, "development": 78}:
        raise ValueError("614 frozen partition scope changed")
    candidates = candidate_rows(docs["geometry"]["records"], frames, docs["joint"]["records"])
    for r in candidates:
        for path, digest in ((r["source_path"], r["source_sha256"]), (r["frame_metadata_path"], r["frame_metadata_sha256"])):
            if sha(path) != digest:
                raise ValueError("candidate coordinate/frame source changed")
            bound[path] = digest
    selected, deferred, symmetries = select_candidates(candidates, docs["paths"])
    statistics = docs["costs"]["statistics"]
    for row in selected:
        stat = statistics[row["composition"]]
        row["conditional_median_core_hours"] = stat["median_seconds"] * stat["ranks"] / 3600
        row["conditional_cap_core_hours"] = math.ceil(2 * stat["p90_seconds"] / 900) / 4 * stat["ranks"]
    gap_candidates = defaultdict(list)
    for row in candidates:
        gap_candidates[(row["composition"], row["joint_signature"])].append(row)
    gaps = []
    for gap in docs["joint"]["gap_groups_outside_training_coverage"]:
        linked = gap_candidates[(gap["composition"], gap["joint_signature"])]
        gaps.append({**gap, "joined_candidate_ids": [r["candidate_id"] for r in linked],
                     "selected_candidate_ids": [r["candidate_id"] for r in linked if r["selected_rank"]]})
    backup = []
    known = {(r["physical_label_key"], r["structure_sha256"]): r for r in frames}
    for row in docs["joint"]["compatible_backup_reuse_references"]:
        backup.append({**row, "actual_error_available": (row["physical_label_key"], row["structure_sha256"]) in known,
                       "new_training_admission": False})
    core_gaps = [
        {"target": "完整C3独立近稳定验收", "priority": "P1_来源缺口",
         "real_seed_ids": [r["candidate_id"] for r in docs["c3_seeds"]["candidates"] if r["proposed_pose_file"]],
         "source_only_unwritten_seed_ids": [r["candidate_id"] for r in docs["c3_seeds"]["candidates"] if not r["proposed_pose_file"]],
         "target_binding_modes_supported": docs["c3_seeds"]["independent_target_binding_mode_count_supported"],
         "compatible_nearstable_labels_verified": 0, "candidate_is_nearstable": False,
         "status": "已有种子受保护；起始种子不等于近稳定构型，单点不能保证补齐稳定端点", "new_DFT_budget_allocated": 0},
        {"target": "C4路径与优化", "priority": "P1_先绑定真实坐标", "real_candidate_ids": [], "actual_error": None,
         "status": "Needs confirmation：沿用既有有界检索未找到C4坐标的结论；未扩大搜索，不断言全服务器不存在", "new_DFT_budget_allocated": 0}]
    summary = {"frames": len(frames), "partitions": dict(Counter(r["partition"] for r in frames)),
               "frame_categories": dict(Counter(r["category"] for r in frames)),
               "same_coordinate_primary_flags": sum(r["actual_error"]["ML_le0p05_DFT_gt0p10"] for r in frames),
               "inverse_threshold_flags": sum(r["inverse_threshold_flag"] for r in frames),
               "candidate_coordinates": len(candidates), "candidate_classes": dict(Counter(r["category"] for r in candidates)),
               "conditional_candidates": len(selected), "candidate_compositions": dict(Counter(r["composition"] for r in selected)),
               "environment_gap_categories": dict(Counter(r["category"] for r in gaps)), "backup_labels": len(backup),
               "new_DFT_allocated": 0, "new_GPU_predictions": 0, "new_training_runs": 0}
    result = {"status": "READ_ONLY_JOINT_PRIORITY_PROPOSAL_NOT_COMPUTE_AUTHORIZATION", "summary": summary,
              "model_sha256": MODEL_SHA, "frames": frames, "environment_groups": environment_groups(frames),
              "candidate_audit": candidates, "selected_conditional_candidates": selected, "candidate_deferrals": deferred,
              "environment_gaps": gaps, "backup_labels": backup, "path_labels": path_rows(docs["paths"], frames),
              "symbolic_path_gaps": symbolic_rows(docs["network"]), "mainline_source_gaps": core_gaps,
              "protected_C3_seed_sources": [{**r, "is_verified_nearstable_frame": False, "new_DFT_budget_allocated": 0} for r in docs["c3_seeds"]["candidates"]],
              "surface_symmetries": symmetries,
              "selection_rule": "先原准入/保护来源门，再三档稳健缺口、未选组成、邻近训练参考的实测关键角色RMSE、缺口范围、ID；同家族和<0.10Å候选去冗余；参考误差不赋给候选",
              "limits": ["候选自身实际力误差、DFT残余力保持null", "相同组成和接触图不证明实际反应路径", "三类统计对象不同，不能相加当作614帧拆分", "已有路径原子力不等于NEB弹簧或投影力", "不改变标签磁性资格或能量准入", "未解决完整C3独立近稳定或C4真实坐标缺口"],
              "frozen_hashes_before": frozen_before,
              "source_files": [{"path": path, "sha256": value} for path, value in sorted(bound.items())]}
    result["master_priorities"] = master_rows(result)
    if guard_hashes() != frozen_before:
        raise ValueError("frozen inputs or project authority changed during read-only audit")
    result["frozen_hashes_after"] = frozen_before
    out.mkdir()
    save(out / "joint_priority.json", result)
    save(out / "summary.json", summary)
    write_outputs(out, result)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
