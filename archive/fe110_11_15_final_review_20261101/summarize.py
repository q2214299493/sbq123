"""Add C-exchange-aware duplicate evidence and a human review; never accept data."""
from dataclasses import replace
from datetime import datetime, timezone
import itertools
from pathlib import Path

from archive.fe110_11_15_final_review_20261101 import audit
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


def compare_poses(first, second, slab, operations):
    """Reuse surface-aware owner; also permit exchange of the two identical C nuclei."""
    symbols = audit.expanded_symbols(second)
    carbons = [i for i in range(45, len(symbols)) if symbols[i] == "C"]
    if len(carbons) != 2:
        raise ValueError("this review is scoped to exactly two carbon atoms")
    scores = [{**audit.surface_equivalence(first, second, slab, operations), "carbon_exchange": False}]
    frac = second.frac.copy()
    frac[carbons] = frac[carbons[::-1]]
    mapped = replace(second, frac=frac)
    scores.append({**audit.surface_equivalence(first, mapped, slab, operations), "carbon_exchange": True})
    return min(scores, key=lambda r: (max(r["adsorbate_RMSD_A"], r["slab_RMSD_A"]), r["adsorbate_RMSD_A"]))


def grouped(records, pairs):
    """Greedy representatives, not transitive chaining across the RMSD tolerance."""
    pair_map = {frozenset([p["first"], p["second"]]): p for p in pairs}
    groups = []
    for row in sorted(records, key=lambda r: (r["toten_eV"], r["name"])):
        if row["blockers"] or not row["requested_graph_preserved"]:
            continue
        duplicate = next((g for g in groups if pair_map.get(frozenset([row["name"], g["representative"]]), {}).get("duplicate")), None)
        if duplicate:
            duplicate["members"].append(row["name"])
        else:
            groups.append({"representative": row["name"], "members": [row["name"]]})
    return groups


def main():
    source = audit.OUT / "analysis.json"
    target = audit.OUT / "final_review.json"
    report = audit.OUT / "final_review.md"
    if target.exists() or report.exists():
        raise FileExistsError("preserve the existing final review")
    analysis = load_json_object(source)
    rows = analysis["records"]
    if len(rows) != 15:
        raise ValueError("incomplete batch")
    slab = audit.read_poscar(audit.CLEAN)
    policy = audit.yaml.safe_load(audit.reviewer.POLICY.read_text())
    rules = policy["duplicate_detection"]
    ops = audit.surface_pose_symmetries(slab)
    poses = {r["name"]: audit.read_poscar(Path(r["directory"]) / "CONTCAR") for r in rows}
    pairs = []
    for first, second in itertools.combinations(rows, 2):
        if first["formula"] != second["formula"] or first["final_signature"] is None or first["final_signature"] != second["final_signature"]:
            continue
        a, b = poses[first["name"]], poses[second["name"]]
        if audit.expanded_symbols(a) != audit.expanded_symbols(b):
            continue
        metrics = compare_poses(a, b, slab, ops)
        de = abs(first["toten_eV"] - second["toten_eV"])
        duplicate = max(metrics["adsorbate_RMSD_A"], metrics["slab_RMSD_A"]) <= rules["geometry_rmsd_tolerance_angstrom"] and de <= rules["energy_tolerance_ev"]
        pairs.append({"first": first["name"], "second": second["name"], **metrics,
            "energy_difference_eV": de, "duplicate": duplicate,
            "energy_difference_is_diagnostic_only": bool(first["blockers"] or second["blockers"])})
    groups = grouped(rows, pairs)
    pending = []
    for row in rows:
        if row["blockers"]:
            matches = [p for p in pairs if p["duplicate"] and row["name"] in (p["first"], p["second"])]
            pending.append({"name": row["name"], "blockers": row["blockers"], "same_geometry_evidence": matches,
                "numerically_accepted": False})
    states = load_json_object(audit.OUT / "scheduler/receipt.json")["states"]
    summary = {"created_at": datetime.now(timezone.utc).isoformat(), "review_scope": "11-15 existing adsorption outputs",
        "analysis_sha256": sha256_file(source), "adapter_sha256": sha256_file(Path(__file__)),
        "records_total": len(rows), "numerical_geometry_pass_count": sum(not r["blockers"] and r["requested_graph_preserved"] for r in rows),
        "requested_graph_preserved_count": sum(r["requested_graph_preserved"] for r in rows),
        "all_fragments": {r["name"]: r["measurements"]["fragments"] for r in rows},
        "independent_converged_groups": groups, "independent_converged_count": len(groups),
        "comparisons_with_C_exchange": pairs, "nonconverged": pending,
        "scheduler_missing_current_DONE": [r["name"] for r in rows if states.get(r["job_id"]) != "DONE"],
        "policy": rules, "no_free_rotation_or_height_fit": True, "raw_sources_preserved": True,
        "scientific_acceptance": False, "registry_written": False, "excel_written": False,
        "adsorption_energy_computed": False,
        "RSI": {"status": "FAILED_BEFORE_RESEARCH", "cause": "file paths supplied to directory-only --scope",
                "automatic_retry": False, "cross_review_completed": False}}
    write_json_exclusive(target, summary)
    text = ["# Fe(110) 11–15 最终结构核验", "", "范围：15个既有作业；不提交、不重算，不写数据库或Excel。",
            "", f"电子/离子/力/参数/几何检查通过：{summary['numerical_geometry_pass_count']}/15。目标连接保持：{summary['requested_graph_preserved_count']}/15。",
            f"本批次内独立收敛构型：{len(groups)}个；不代表全局最低能或已完成振动稳定性验证。", "",
            "去重采用项目0.20 Å RMSD与0.05 eV能差规则；同一真实表面对称操作同时匹配吸附物和Fe环境，允许H交换及两个C核交换；不任意平移高度或旋转分子。", "",
            "| 编号 | 独立收敛代表 | 合并的收敛来源 | 未收敛 |", "|---|---|---|---|"]
    for species in ("11", "12", "13", "14", "15"):
        gs = [g for g in groups if g["representative"].startswith(species + "_")]
        duplicates = [n + "→" + g["representative"] for g in gs for n in g["members"] if n != g["representative"]]
        failures = [r["name"] for r in rows if r["name"].startswith(species + "_") and r["blockers"]]
        text.append("| " + " | ".join([species, ", ".join(g["representative"] for g in gs), ", ".join(duplicates) or "无", ", ".join(failures) or "无"]) + " |")
    text += ["", "## 每个来源", "", "TOTEN仅按兼容SIGMA=0.20 eV分支保存；未补齐气相/参考能元组，因此不是吸附能。13_A能量仅用于诊断，不能作为已接受能量。", "",
             "| 构型 | 作业 | 步数 | 最大可动原子力 eV/Å | 最终TOTEN eV | 核验阻碍 |", "|---|---|---:|---:|---:|---|"]
    for r in rows:
        text.append(f"| {r['name']} | {r['job_id']} | {r['ionic_steps']} | {r['fmax_eV_A']:.8f} | {r['toten_eV']:.8f} | {', '.join(r['blockers']) or '数值与结构检查通过'} |")
    text += ["", "## 边界与失败记录", "", "- 原始90个输入/输出文件及远程POTCAR哈希完整保存；POTCAR内容未下载。",
             "- 初次11_A传输缺少INCAR，其他已下载文件保留；仅补收缺少的INCAR后全部SHA256通过。没有重投作业。",
             "- 当前DONE证据缺失：" + ", ".join(summary["scheduler_missing_current_DONE"]) + "。bjobs/bacct/bhist未恢复；UNKNOWN不等于计算失败，正式登记需另行处理证据缺口。",
             "- 去重不删除原始记录；未把分离共吸附或化学转化结果混入原目标。各结构的片段、键长与Fe接触见analysis.json。",
             "- 本次尚未给予正式科学接受，数据库/Excel未修改。",
             "- RSI本次因将文件路径传给仅接受目录的scope参数而在研究启动前失败，未重试，未声称完成其交叉审查。",
             "- 未执行振动稳定性、气相参考、热修正、速度收益或全局最稳构型验证。", ""]
    with report.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(text))
    print("FINAL", summary["numerical_geometry_pass_count"], "numerical_geometry_pass;", len(groups), "independent_converged", flush=True)
    print("GROUPS", groups, flush=True)
    print("NONCONVERGED", pending, flush=True)


if __name__ == "__main__":
    main()
