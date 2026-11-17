"""Render a source-linked audit report; never change inputs or candidate membership."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyze import ROOT, carbon_count, load, save, sha, table


def link(path, label=None):
    path = Path(path)
    return f"[{label or path.name}]({path.as_posix()})"


def render(run, report_dir):
    results = run / "results_v2"
    data_path = results / "joint_priority.json"
    data = load(data_path)
    selected = sorted(data["selected_conditional_candidates"], key=lambda r: r["selected_rank"])
    connection_rows = []
    for row in selected:
        geometry = row["geometry"]
        connection_rows.append({"rank": row["selected_rank"], "candidate_id": row["candidate_id"], "composition": row["composition"],
                                "source_path": row["source_path"], "sha256": row["source_sha256"],
                                "graph_signature": geometry["environment"]["graph_signature"], "joint_signature": row["joint_signature"],
                                "bond_counts": geometry["environment"]["bond_counts"], "edges": geometry["graph"]["edges_local_0based"],
                                "symbols": geometry["graph"]["symbols_local"], "C_C_pairs": geometry["C_C_pairs"],
                                "binding_sites": geometry["binding_sites"], "actual_error": None,
                                "path_evidence": "真实REICO短ML轨迹；不是DFT反应路径"})
    connection_path = run / "补标候选连接环境.csv"
    table(connection_path, connection_rows, [("rank", "条件备选顺序"), ("candidate_id", "候选ID"), ("composition", "组成"), ("source_path", "坐标来源"), ("sha256", "坐标SHA256"), ("symbols", "局部原子序"), ("edges", "几何接触边_局部零起始索引"), ("graph_signature", "连接图签名"), ("joint_signature", "连接配位联合签名"), ("bond_counts", "几何接触计数"), ("C_C_pairs", "CC距离_A"), ("binding_sites", "逐原子Fe邻居与名义位点"), ("actual_error", "候选自身实测误差_未知留空"), ("path_evidence", "路径证据等级")])
    rsi_receipt = load(run / "rsi_process_receipt.json")
    rsi = json.loads(rsi_receipt["stdout"])
    rsi_dir = Path(rsi["rsi_application"]["path"]).parent
    rsi_application = load(rsi_dir / "rsi_application.json")
    main_flags = [r for r in data["frames"] if r["actual_error"]["ML_le0p05_DFT_gt0p10"]]
    inverse_mainline = [r for r in data["frames"] if r["inverse_threshold_flag"] and 2 <= carbon_count(r["composition"]) <= 4]
    protected = [r for r in data["path_labels"] if r["protected"]]
    source_files = [data_path, run / "rsi_process_receipt.json", Path(__file__), rsi_dir / "research_result.json"]
    lines = [
        "# C₂–C₄误差—化学环境—反应路径联合只读优先表", "", "日期：2026-11-17。最终数据使用 `results_v2`；早期 `results` 保留，不作为最终交付。", "",
        "已复用冻结536的614帧GPU预测及已有DFT标签，完成完整ID/坐标/物理标签键连接、359个环境单元的误差汇总、67个真实候选的来源审核与条件排序。没有重新预测、训练或提交DFT。", "",
        "优先顺序为：P0已有标签与同坐标失配复核 → P1真实路径/C₄坐标及独立C₃验收来源绑定 → P2离平衡条件补标。20个备选均为多组分REICO几何，候选自身真实误差未知；不能将它们当作完整C₃近稳定或C₄覆盖方案。", "",
        "## 1. 联合清单与三类对象", "",
        "| 对象 | 已有标签可复用 | 数据重复偏多 | 目录内确实缺标 | 另列阻塞 |", "|---|---:|---:|---:|---:|",
        "| 614帧既有标签 | 449个几何代表 | 165帧近重复 | 0 | 原磁性资格不升级 |",
        "| 包外既有训练侧标签 | 142条备选：C₂H₃/C₃H₂O各71 | 保留同家族及相邻帧信息 | 0 | 新包准入仍需审核 |",
        "| 178个训练未覆盖联合类型 | 0个可直接覆盖缺口的已审类型 | 不与帧数相加 | 176类 | 2类已有记录不可复用 |",
        "| 67个已绑定真实候选 | 0个新增自动准入 | 另列几何接近与同家族递延 | 65个坐标 | 2个已有标签先审核 |", "",
        "这些统计属于不同对象，不能相加作为614帧拆分。449个几何代表也不是449个统计独立来源；165帧近重复不删除、不降级。142条包外标签不自动加入536，也不转成独立验收。", "",
        f"主入口：{link(results / '联合总优先表.csv')}；全量614帧：{link(results / '614帧误差环境联合表.csv')}；环境单元：{link(results / '化学环境实测误差优先表.csv')}。", "",
        "## 2. 已有真实误差优先复用，不重复计算", "",
        "ΔFᵢ=‖F_ML,i−F_DFT,i‖₂。沿用已核验的原生ASE FP32预测、物理单位eV/Å和可动原子掩码；固定底18个Fe排除。训练536与开发78分开，严格证据和原审核force-only范围分开。C₁/H₂保留在614全量表中作为知识保留参考，不计作C₂–C₄新增覆盖。", "",
        "| 已有结构ID | 分区 | ML最大力 | DFT最大力 | 最大误差角色 |", "|---|---|---:|---:|---|"]
    for row in main_flags:
        e = row["actual_error"]
        lines.append(f"| {row['sample_id']} | {row['partition']} | {e['ML_fmax_eV_A']:.6f} | {e['DFT_fmax_eV_A']:.6f} | {e['maximum_error_role']} |")
    lines += ["", "主阈值是ML最大可动力≤0.05且DFT>0.10 eV/Å。6个个案已有同坐标标签，5训练+1开发，均保留原force-only及局域磁矩缺口。开发08_B_step111仅评估，不转训练。", "",
              f"反向数值阈值DFT≤0.02但ML>0.02共有22帧，其中C₂/C₃主线{len(inverse_mainline)}帧；这些是固定坐标阈值分歧，不证明实际优化失败或DFT科学验收。完整C₃的opt133已有DFT标签，继续优先复用。", "",
              "C/O每原子误差与近邻Fe误差分别保留，不将可动Fe数量多解释为唯一误差来源。359个环境单元均给出原子加权RMSE/MAE和来源均衡的逐帧MAE；组成、力区间和磁性资格不混为一个平均数。", "",
              "## 3. 20个条件补标候选及排序依据", "",
              "先通过既有坐标/隔离审核与标签查重；递延0021/0028/0086风险家族；优先候选自身在1.20/1.25/1.30三档接触判据下均缺覆盖的环境，再按组成多样性和邻近已标注训练结构的关键角色实测RMSE排序，同家族首批一个、候选间含可动Fe对称距离<0.10 Å去冗余。", "",
              "关键角色参考值=max(C、O、近邻Fe的向量RMSE)。这是可复核的启发式排序，不是候选自身误差、委员会不确定度或最优选样证明；相邻参考值未外推给候选。按几何接近度给出上下文，不假定任何误差相关长度。", "",
              "| 顺序 | 候选ID | 组成 | 已标注参考ID | 仅参考的关键角色RMSE | 候选自身ΔF |", "|---:|---|---|---|---:|---|"]
    for row in selected:
        e = row["error_context"]
        lines.append(f"| {row['selected_rank']} | {row['candidate_id']} | {row['composition']} | {e['reference_id']} | {e['reference_actual_critical_RMSE_eV_A']:.4f} | 未知 |")
    lines += ["", "1–10为P2a条件备选，11–20为P2b后备；不是已批准计算批次。合计C₂H₂O 6、C₂H₃ 3、C₂HO 2、C₃H₂O 9，20个不同家族。所有候选均多组分，C₃碳骨架连通也不等于完整C₃H₂O；不将总分子式当作分子身份。", "",
              f"来源、坐标SHA、标签现状、参考距离和预算：{link(results / '补标条件候选与预算.csv')}。全部67项及递延理由：{link(results / '67候选审核及误差上下文.csv')}。", "",
              f"完整接触边、局部原子序、C—C距离、Fe接触邻居和名义位点：{link(connection_path)}。这些接触不证明电子键级或稳定吸附位点；未进行新的结构生成或优化。", "",
              "## 4. 反应路径与已有标签旁路", "",
              "CH+CO已有起始6帧和末段6帧路径原子力，应先核查原磁性与用途资格，不为相同坐标重复单点。另一个CHCO训练家族有10个物理标签引用，跨后端和磁性资格不能自动继承；整个训练家族不作为新的独立盲验收。C+H另有11条引用，其中6条保护验证标签继续禁止进入训练。", "",
              f"本轮列出{len(data['path_labels'])}条路径/训练标签引用，不称为同数量的独立或已准入构型；其中保护验证引用{len(protected)}条。原始DFT原子力不替换为NEB弹簧或投影力。详见{link(results / '反应路径已有标签复用表.csv')}。", "",
              f"符号网络中筛出{len(data['symbolic_path_gaps'])}条本步总碳数2–4且关联C₂–C₄目标路径的来源记录，包括C₂加氢/耦合、C₃生长/裂解/脱氧以及C₄生长/加氢/脱氧。它们没有完成真实路径坐标绑定，状态为“来源待绑定”，不称“确实无DFT标签”。来源路径目标C₄也不等于每一步具有C₄骨架。详见{link(results / 'C2至C4反应路径来源缺口.csv')}。", "",
              "C₄四条关键来源保留：C1C6_R034176::R、REV_C1C6_R002321::F、C1C6_R038452::F、C1C6_R028346::R。当前没有可执行C₄结构ID或本模型真实误差；沿用此前有界检索结论，未扩展服务器搜索，不能断言全服务器不存在C₄。", "",
              "## 5. 完整C₃独立近稳定与准入阻塞", "",
              "完整C₃训练低力24帧仍集中于0099家族，只有3个几何代表；它们不能再担任独立验收。已有C₃提案中的cfg0/cfg1仅做过内存Fe45迁移审核，没有已写出的Fe45输入，不虚构可执行坐标。", "",
              "已有真实Fe45种子为05_C3H2O_FLJNAOYG_cfg2、07_C3H2O_POVFFVOJ_cfg2、08_C3H2O_XXNRTDXE_cfg0；后两者分别保留独立异构体后备、历史负对照用途。原提案支持的目标结合模式数为2（包含虚拟迁移证据），第三种仍Needs confirmation；三个真实种子不等于三个目标模式或三个近稳定构型。它们的近稳定力标签尚未验证，不分配新的计算预算。", "",
              f"详见{link(results / 'C3验收种子与阻塞.csv')}。任何验收侧新标签与训练补标预算均应另行明确，不能把一个起始结构单点当作已补齐近稳定端点。", "",
              "已有记录阻塞单列：family_0028_step000/job9919443的局域Fe磁性待审；family_0086_step000/job9919414保留原QC排除。不得把已有失败记录改叫缺标并自动原样重算。", "",
              f"178类处置：{link(results / '178缺口类型处置表.csv')}；142条包外复用来源：{link(results / '142包外标签复用表.csv')}。所有“缺标”限定于已绑定来源范围。", "",
              "## 6. 条件预算与执行边界", "",
              "| 条件备选数量 | 历史中位参考核时 | 条件分配核时上限 | 本轮实际分配/提交 |", "|---:|---:|---:|---:|"]
    for size in (10, 20):
        prefix = selected[:size]
        lines.append(f"| {size} | {sum(r['conditional_median_core_hours'] for r in prefix):.1f} | {sum(r['conditional_cap_core_hours'] for r in prefix):.0f} | 0 |")
    lines += ["", "成本沿用24个历史32核单点的小样本参考：各组成2×历史P90向上取整至0.25小时；不是整批置信界、实扣账单或已批准预算，不含未知C₄准备、独立验收、排队、重试或未来训练。不能为了用满20个名额跳过主线来源缺口。", "",
              "512/536包及78/53/16分区保持冻结，checkpoint不变；原current_task仍为另一组六作业VASP对照，本轮不覆盖或干预。不新增GPU预测、训练、DFT、优化、NEB/DIMER，不自动接受模型、结构或标签。", "",
              "## 7. 验证、RSI与下一步", "",
              f"新分析代码的5个科学记账测试通过，覆盖同ID异坐标拒绝、开发隔离、邻居误差不外推、来源均衡、已有失败记录不改称缺标以及路径目标与本步骨架的区别；限定Ruff检查通过。数据验证见{link(run / 'verification_v2.json')}，包括完整614行连接、各表行数、源哈希、角色SSE守恒、保护来源、候选去冗余和冻结文件守卫。", "",
              f"本轮RSI仅调用一次，状态{rsi['status']}，模型{rsi['model_turns_started']}轮、资料工具{rsi['host_tool_executions']}次，选中经验{len(rsi_application['selected_policies'])}条。建议采用P0复用→P1真实来源绑定→P2条件候选的顺序，已体现在表中。RSI实际只阅读了有界摘要/片段，其明确保留未完成全量独立复核的限制；程序对完整614行的检查与RSI建议分开，不将模型建议当成科学验收。", "",
              f"{link(rsi_dir / 'review.md', '本次RSI记录')}；{link(Path('C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html'), 'RSI看板')}。", "",
              "唯一下一步：先只读复核P0的C₂真实路径标签磁性与兼容性，明确哪些既有路径标签能复用，再锁定首批确需新单点的坐标；不立即执行这20个备选。", ""]
    report_dir.mkdir(exist_ok=False)
    report = report_dir / "README.md"
    with report.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
    save(run / "report_binding.json", {"data_sha256": sha(data_path), "report": str(report), "report_sha256": sha(report),
                                       "connection_table_sha256": sha(connection_path),
                                       "source_files": [{"path": str(p.resolve()), "sha256": sha(p)} for p in source_files]})
    print(json.dumps({"report": str(report), "conditional_candidates": len(selected), "mainline_inverse_flags": len(inverse_mainline)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "docs/reviews/fe110_joint_priority_20261117")
    args = parser.parse_args()
    render(args.run.resolve(), args.report_dir.resolve())
