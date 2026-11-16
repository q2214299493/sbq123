"""Review evidence blockers and render a CPU-only inventory; reuse measured geometries."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .audit import BASE, BINS, BLOCKED, OUT, ROOT, gap_category, write_tables


def review_inventory():
    initial = OUT / "joint_inventory.json"
    result = load_json_object(initial)
    snapshot = OUT / "audit_initial_source_snapshot.py.txt"
    source = Path(__file__).with_name("audit.py")
    original_sha = next(r["sha256"] for r in result["source_files"] if Path(r["path"]) == source)
    if sha256_file(snapshot) != original_sha:
        raise ValueError("initial collector source snapshot does not match measured evidence")
    for row in result["gap_groups_outside_training_coverage"]:
        ready = row["reuse_substatus"] == "COMPATIBLE_LABEL_REVIEW_CANDIDATE"
        row["category"] = gap_category(bool(row["existing_labeled_members"]), ready)
    result["gap_category_counts_separate_universe"] = dict(Counter(r["category"] for r in result["gap_groups_outside_training_coverage"]))
    grouped = defaultdict(list)
    for r in result["records"]:
        grouped[(r["partition"], r["qualification_scope"], r["composition"], r["force_bin"], r["joint_signature"])].append(r)
    result["joint_cells"] = [{"environment_id": f"ENV_{i:03d}", "partition": key[0], "qualification_scope": key[1], "composition": key[2],
                              "force_bin": key[3], "joint_signature": key[4], "frames": len(rows),
                              "source_roots": sorted({r["source_root"] for r in rows}),
                              "representatives": sorted({r["near_duplicate"]["representative_id"] for r in rows}),
                              "sample_ids": [r["sample_id"] for r in rows]}
                             for i, (key, rows) in enumerate(sorted(grouped.items()), 1)]
    result["role_DFT_force_distributions"] = role_distributions()
    result["revision"] = "reviewed;two existing but ineligible records separated from reusable labels;geometry and force results reused byte-for-byte"
    bound = {Path(r["path"]) for r in result["source_files"]} | {initial, snapshot, Path(__file__)}
    result["source_files"] = source_file_manifest(sorted(bound))
    write_json_exclusive(OUT / "joint_inventory_reviewed.json", result)
    write_tables(result, "_reviewed")
    with (OUT / "联合环境覆盖汇总.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["环境ID", "分区", "标签资格", "组成", "力区间", "连接配位签名", "帧数", "来源根数", "几何代表数", "来源根", "代表ID", "全部结构ID"])
        for r in result["joint_cells"]:
            writer.writerow([r["environment_id"], r["partition"], r["qualification_scope"], r["composition"], r["force_bin"], r["joint_signature"], r["frames"], len(r["source_roots"]), len(r["representatives"]), ";".join(r["source_roots"]), ";".join(r["representatives"]), ";".join(r["sample_ids"])])
    with (OUT / "已有142帧备选复用来源.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["结构ID", "组成", "来源家族", "DFT作业", "DFT步", "物理标签键", "原坐标路径", "坐标SHA256", "使用范围"])
        for r in result["compatible_backup_reuse_references"]:
            writer.writerow([r["candidate_id"], r["composition"], r["family_id"], r["source_job_id"], r["DFT_ionic_step"], r["physical_label_key"], r["structure_path"], r["structure_sha256"], "训练侧待审核复用；不独立验收、不自动准入、不重复计算"])
    return result


def role_distributions():
    labels = load_json_object(BASE / "force_diagnosis536_20261114_v1/qualified_reference_labels.json")["records"]
    grouped = defaultdict(list)
    for row in labels:
        force = np.asarray(row["DFT_forces_eV_per_A"])
        groups = dict(row["force_role_groups"])
        groups["all_movable_Fe"] = groups["near_Fe"] + groups["other_Fe"]
        for role, indices in groups.items():
            grouped[(row["partition"], row["qualification_scope"], role)].extend(np.linalg.norm(force[indices], axis=1).tolist())
    return [{"partition": key[0], "qualification_scope": key[1], "role": key[2], "atom_observations": len(values),
             "DFT_force_norm_p50_eV_A": float(np.quantile(values, .5)), "DFT_force_norm_p90_eV_A": float(np.quantile(values, .9)),
             "DFT_force_norm_max_eV_A": float(max(values)), "DFT_force_norm_mean_eV_A": float(np.mean(values))}
            for key, values in sorted(grouped.items()) if values]


def plot(result):
    font = FontProperties(fname=r"C:\Windows\Fonts\msyh.ttc")
    plt.rcParams["axes.unicode_minus"] = False
    compositions = ["C2HO", "C2H2O", "C2H3", "C3H2O", "其他组成"]
    labels = ["≤0.02", "(0.02,0.05]", "(0.05,0.10]", "(0.10,0.50]", ">0.50"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, split, title in zip(axes, ("train", "development"), ("训练：536帧", "开发：78帧"), strict=True):
        matrix = np.zeros((5, 5), dtype=int)
        sources = matrix.copy()
        for i, composition in enumerate(compositions):
            for j, force_bin in enumerate(BINS):
                rows = [r for r in result["records"] if r["partition"] == split and r["force_bin"] == force_bin
                        and (r["composition"] == composition if i < 4 else r["composition"] not in compositions[:4])]
                matrix[i, j], sources[i, j] = len(rows), len({r["source_root"] for r in rows})
        ax.imshow(matrix, cmap="Blues", vmin=0, vmax=125)
        for i in range(5):
            for j in range(5):
                ax.text(j, i, f"{matrix[i,j]} / {sources[i,j]}", ha="center", va="center", fontsize=10,
                        color="white" if matrix[i, j] > 65 else "black")
        ax.set_xticks(range(5), labels, rotation=25, ha="right")
        ax.set_yticks(range(5), compositions, fontproperties=font)
        ax.set_title(title, fontproperties=font, fontsize=13)
        ax.set_xlabel("最大DFT可动力区间（eV/Å）", fontproperties=font)
    fig.suptitle("614帧已有DFT标签：每格为帧数 / 来源根数", fontproperties=font, fontsize=15)
    fig.text(.5, .015, "排除固定18个Fe；来源根不等于统计独立样本；含严格证据与原force-only范围；无新ML预测", ha="center", fontproperties=font, fontsize=10)
    fig.tight_layout(rect=(0, .07, 1, .94))
    target = OUT / "DFT力区间与来源覆盖.png"
    if target.exists():
        raise FileExistsError(target)
    fig.savefig(target, dpi=160)
    plt.close(fig)
    write_json_exclusive(OUT / "plot_binding.json", {"DFT_labels_only": True, "ML_predictions": False,
                         "source_files": source_file_manifest([Path(__file__), OUT / "joint_inventory_reviewed.json", target])})


def report(result):
    folder = ROOT / "docs/reviews/fe110_joint614_cpu_20261116"
    folder.mkdir(parents=True, exist_ok=True)
    rows = result["records"]
    lines = ["# 614帧DFT力区间、连接环境与来源去冗余联合清单", "", "日期：2026-11-16。CPU只读分析已完成；实际ML力误差、新单点选样和科学准入均未执行。", "",
             "本轮保持512/536包、78开发/53测试/16隔离分区、checkpoint、注册库和原任务指针不变。614=536训练+78开发，不是614训练。", "",
             "## 1. 力区间与覆盖", "", "力指标为每帧全部可动原子DFT力向量范数的最大值，排除固定底18个Fe、包含上27个Fe及吸附C/O/H。区间是诊断分组，不证明优化阶段、稳定极小值或TS。", "",
             "| DFT最大力（eV/Å） | 训练 | 开发 |", "|---|---:|---:|"]
    for name, label in zip(BINS, ("≤0.02", "(0.02,0.05]", "(0.05,0.10]", "(0.10,0.50]", ">0.50"), strict=True):
        lines.append(f"| {label} | {sum(r['partition']=='train' and r['force_bin']==name for r in rows)} | {sum(r['partition']=='development' and r['force_bin']==name for r in rows)} |")
    lines += ["", "| 分区/主要组成 | 帧数 | 来源根数 | 0.10 Å几何代表数 | ≤0.05帧数 | 低力来源数 |", "|---|---:|---:|---:|---:|---:|"]
    for split in ("train", "development"):
        for comp in ("C2HO", "C2H2O", "C2H3", "C3H2O"):
            group = [r for r in rows if r["partition"] == split and r["composition"] == comp]
            low = [r for r in group if r["DFT_fmax_eV_A"] <= .05]
            lines.append(f"| {split}/{comp} | {len(group)} | {len({r['source_root'] for r in group})} | {len({r['near_duplicate']['representative_id'] for r in group})} | {len(low)} | {len({r['source_root'] for r in low})} |")
    lines += ["", f"![DFT力区间与来源覆盖]({(OUT/'DFT力区间与来源覆盖.png').as_posix()})", "", "## 2. 标签资格、连接和原子角色", "",
              "严格E/F/局域磁矩证据：训练285、开发18；原审核force-only范围：训练251、开发60。原磁性等级保留，未重新准入。低力训练65帧中24严格+41原force-only；开发低力14帧全部是原force-only范围。严格开发子集没有≤0.05帧。", "",
              "逐帧记录C/O/H、近邻Fe、其他Fe、全部可动Fe的DFT力范数，缺失元素标空而非零；最大力原子与角色另列。整训练最大力落在Fe的42帧、开发10帧只是DFT受力分布，不证明Fe预测误差主导。原子角色分布的中位/P90/最大值按训练/开发及资格分开保存在JSON。", "",
              "连接判据沿用`configs/adsmind_lite/analysis_rules.yaml`：共价半径系数1.25、最小键距0.35 Å；沿用1.20/1.25/1.30敏感性扫描。记录吸附组分、C—C骨架连通、逐原子Fe配位、规范图和联合签名。这些是几何接触，不是电子键级或已确认反应路径。", "",
              "78帧的吸附连接图随截断变化，另有311帧仅Fe配位/联合签名敏感，225帧两者都不变。敏感性保留，未据此排除标签。", "",
              "低力C3H2O的24帧均为单一吸附连接组分且C3骨架连通，来源均为0099，归为3个几何代表；不是CO+C2H2。低力C2H3的4帧均完整，只有9848812一个来源、2个代表，保留总磁矩级证据限制。C2HO低力9帧中5帧为C+CO+H；C2H2O低力17帧中7帧为CH2+CO。因此组成和低力帧数不能替代完整分子环境覆盖。", "",
              "## 3. 来源根与去冗余", "",
              "明确family_id优先，其次已有calculation_group；0099的静态、旧优化与9924387续算属于同一来源根。其他老轨迹按已有来源组保留，不根据文件名或新作业号制造独立性。来源根是溯源单位，不等于统计独立样本。13帧旧回放没有scheduler作业ID，沿用其明确目录来源，未编造ID。", "",
              "训练103、开发17个来源根，无跨分区共同来源根。614帧无重复坐标文件SHA或物理标签键；36个保留表面的对称操作、同元素排列、面内周期最短像并计入可动Fe后，训练/开发间没有≤0.20 Å整结构近邻。此结论仅针对614，不声称本轮重新审计53/16的几何或力。", "",
              "近重复距离沿用0.10 Å：在同分区、同资格、同组成、同力区间、同连接—配位签名内，以对称操作下max(吸附质RMSD,可动Fe RMSD)作距离，确定性代表半径分组，不使用链式连通聚类。398训练+51开发=449个代表，165帧为代表半径内近重复；代表之间可能仍相关，不称449个独立结构或极小值。", "",
              "半径敏感性：0.05 Å为422/58个训练/开发代表；0.10 Å为398/51；0.20 Å为364/44。分组只用于诊断，不删除165帧、不重划数据，也不表示其力标签无用。", "",
              "## 4. 三类清单与准入阻塞", "", "三类统计有不同对象，不能直接相加当作614帧的拆分。", "",
              "| 类别 | 对象与数量 | 当前用途 |", "|---|---|---|",
              "| 已有标签可复用 | 614帧中449个诊断代表；另有142帧包外训练侧兼容备选（C2H3/C3H2O各71） | 沿用原资格诊断；包外备选仍需准入审核，不是独立验收 |",
              "| 现有数据重复偏多 | 614帧中165帧落入上述代表半径 | 标记来源集中和几何相近，不删除、不降级 |",
              "| 确实缺少标注 | 已绑定REICO训练池内176个未覆盖连接—配位类型，没有同坐标DFT标签 | 仅缺口，不等于176个新单点；无标签DFT力区间为未知 |", "",
              "536训练相对于1597帧固定REICO训练池仍缺178个几何联合类型（C2HO20/C2H2O25/C2H339/C3H2O94）。其中另2类有已有记录但尚不可复用，单列阻塞，不能归为合格复用或宣称完全无标签：", "",
              "| 结构ID | 已有作业 | 阻塞 |", "|---|---|---|",
              "| family_0028_step000 | 9919443 | 局域Fe磁性待审；保留原等级 |",
              "| family_0086_step000 | 9919414 | 原QC排除保留，坐标—力对应/电子收敛/能量对应未通过 |", "",
              "2条记录先解决原证据，不自动批准、不原样重算。缺口标签判定按坐标SHA、物理标签键和原分区，未用相同ID或附近结构替代同坐标。已有142帧备选可补受力过程，但在原默认判据下没有覆盖这178个缺失联合类型；不能声称它们解决所有环境缺口。", "",
              "这里“确实缺少”仅限已绑定目录和现有REICO池；未扩大服务器搜索，不作全项目或全化学空间无标签断言。没有把未读文件、未发现的C4坐标或未定义反应路径算成可执行单点候选。", "",
              "## 5. 优先级与后续接口", "",
              "已确认优先缺口：完整C3近稳定标签仍集中于0099；开发C3的9帧全部>0.50，且没有完整单组分C3H2O，不能用于独立近稳定验收。C2H3低力仅一个旧来源，局域磁矩证据不完整。C2含氧体系的完整分子和解离环境须分别评估。", "",
              "C4在614中为0帧；2026-11-14已绑定的有界检索未定位可绑定真实C4坐标。本轮未扩大检索，仍需确认结构来源和兼容标签；不能虚构ID、分配DFT预算或根据化学式推断路径。C5/C6不在本614分析范围。", "",
              "所有缺口的冻结536实际力误差保持null，新单点预算分配为0，上一轮20个备选继续待定。GPU恢复后先复用兼容预测缓存或完成同坐标推理，再将误差叠加到本清单，区分已有数据未学好与真实覆盖不足。", "",
              "## 6. 文件与验证", ""]
    for name, label in [("614帧联合清单_reviewed.csv", "614帧逐帧联合清单"), ("联合环境覆盖汇总.csv", "力区间×连接环境×来源汇总"), ("缺口分类清单_reviewed.csv", "178类缺口及2类准入阻塞"), ("已有142帧备选复用来源.csv", "142帧包外兼容标签来源"), ("joint_inventory_reviewed.json", "完整哈希绑定、逐原子角色统计、来源和去冗余证据")]:
        lines.append(f"- [{label}]({(OUT/name).as_posix()})")
    lines += ["", "只读源绑定、614帧坐标/原子序/约束/标签元数据和DFT最大力重算核对，以及数值/来源/非链式聚类/准入阻塞测试均需通过最终verification.json后交付；不以脚本退出0替代科学准入。分析期间没有GPU查询或推理、训练、DFT提交、优化、数据包变更或模型晋升。", "",
              "本轮RSI仅调用一次：3个模型回合、7次宿主资料动作、采用经验0。它未能在自身限定范围读取父目录标签本体，给出“先核查同坐标标签与来源、不把访问缺口当缺标”的建议；主分析已直接读取并校验现有本地文件，未因此重算或重试入口。", "",
              "[RSI看板](C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html)。报告按report-quality-gate复核中文、单位、数字、链接与事实/限制。", "",
              "**下一步：GPU可用后，将冻结536同坐标力误差绑定到本联合清单，再确定补标结构。**", ""]
    with (folder / "README.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))


if __name__ == "__main__":
    result = review_inventory()
    plot(result)
    report(result)
    print({"frames": len(result["records"]), "joint_cells": len(result["joint_cells"]),
           "gap_categories": result["gap_category_counts_separate_universe"],
           "blocked_gaps": sum(r["category"] == BLOCKED for r in result["gap_groups_outside_training_coverage"])}, flush=True)
