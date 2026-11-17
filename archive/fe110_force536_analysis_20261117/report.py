"""Render source-bound force diagnostics without accepting models or allocating DFT."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .analyze import BASE, OUT, ROLE_NAMES, ROOT, STRICT


def select(result, partition, role="all_movable", scope="ALL", composition="ALL", phase="ALL", population="all_frames"):
    return next((r for r in result["summary_metrics"] if (r["partition"], r["role"], r["qualification_scope"], r["composition"], r["force_stage"], r["population"]) ==
                 (partition, role, scope, composition, phase, population)), None)


def precision_context():
    ase = BASE / "energy_reaction_sidecar_20261113_v1/deployed_ase_utils.py.txt"
    training = BASE / "training536_execution_20261113_v4/executor/entry.py"
    gpu_request = BASE / "force_diagnosis536_gpu_20261117_v4/packet/request.json"
    request = load_json_object(gpu_request)
    expected = next(r["sha256"] for r in request["native_source_files"] if r["path"].endswith("ase_utils.py"))
    text = ase.read_text(encoding="utf-8")
    if sha256_file(ase) != expected or "disable_amp: bool = True" not in text or "self.trainer.scaler = None" not in text:
        raise ValueError("native ASE precision source binding not established")
    if '"--amp"' not in training.read_text(encoding="utf-8"):
        raise ValueError("training AMP entry evidence changed")
    note = {"training_execution_entry_includes_amp": True, "ASE_calculator_defaults_disable_amp_true": True,
            "ASE_snapshot_matches_executed_native_source": True,
            "full_3p11percent_cache_difference_causally_explained": False,
            "conclusion": "precision paths differ;matched-precision replay not performed;do not call the changed MAE model improvement",
            "source_files": source_file_manifest([ase, training, gpu_request, OUT / "checkpoint_metadata_probe.json"])}
    write_json_exclusive(OUT / "precision_context.json", note)


def plot(result):
    font = FontProperties(fname=r"C:\Windows\Fonts\msyh.ttc")
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.3))
    roles = ["adsorbate_C", "adsorbate_O", "adsorbate_H", "near_Fe", "other_Fe"]
    x = np.arange(len(roles))
    for offset, partition, label, color in [(-.19, "train", "训练536帧", "#3b78a6"), (.19, "development", "开发78帧", "#d18735")]:
        values = [select(result, partition, role)["vector_RMSE_eV_A"] for role in roles]
        axes[0].bar(x + offset, values, .36, label=label, color=color)
    axes[0].set_xticks(x, [ROLE_NAMES[r] for r in roles], fontproperties=font)
    axes[0].set_ylabel("力向量RMSE（eV/Å）", fontproperties=font)
    axes[0].set_title("原子角色误差：保留原标签资格范围", fontproperties=font)
    axes[0].legend(prop=font)
    axes[0].grid(axis="y", alpha=.2)
    for partition, label, color in [("train", "训练", "#3b78a6"), ("development", "开发", "#d18735")]:
        frames = [r for r in result["frames"] if r["partition"] == partition]
        axes[1].scatter([r["DFT_fmax_eV_A"] for r in frames], [r["ML_fmax_eV_A"] for r in frames], s=16, alpha=.5, label=label, color=color)
    flags = result["primary_flagged_frames"]
    axes[1].scatter([r["DFT_fmax_eV_A"] for r in flags], [r["ML_fmax_eV_A"] for r in flags], s=85, marker="x", color="#b62f36", label="小ML力/大DFT力：6帧")
    axes[1].plot([.003, 40], [.003, 40], "--", color="gray", linewidth=1)
    axes[1].axvline(.1, color="#b62f36", alpha=.5, linestyle=":")
    axes[1].axhline(.05, color="#b62f36", alpha=.5, linestyle=":")
    axes[1].set_xscale("log")
    axes[1].set_yscale("log")
    axes[1].set_xlim(.003, 40)
    axes[1].set_ylim(.003, 40)
    axes[1].set_xlabel("同坐标DFT最大可动力（eV/Å）", fontproperties=font)
    axes[1].set_ylabel("ML最大可动力（eV/Å）", fontproperties=font)
    axes[1].set_title("最大力幅值对照；6帧均为原force-only范围", fontproperties=font)
    axes[1].legend(prop=font, fontsize=9)
    fig.suptitle("冻结536：614帧同坐标力比较", fontproperties=font, fontsize=15)
    fig.text(.5, .015, "排除固定18个Fe；最大力散点不替代逐原子向量误差；本图不证明结构优化或VASP加速效果", ha="center", fontproperties=font, fontsize=10)
    fig.tight_layout(rect=(0, .06, 1, .94))
    target = OUT / "固定结构力误差.png"
    if target.exists():
        raise FileExistsError(target)
    fig.savefig(target, dpi=160)
    plt.close(fig)
    write_json_exclusive(OUT / "plot_binding.json", {"source_files": source_file_manifest([Path(__file__), OUT / "same_coordinate_force_diagnosis.json", target])})


def report(result):
    directory = ROOT / "docs/reviews/fe110_force536_analysis_20261117"
    directory.mkdir(parents=True, exist_ok=True)
    dev = select(result, "development")
    fe = select(result, "development", "all_movable_Fe")
    fe_share = 100 * fe["sum_squared_vector_error"] / dev["sum_squared_vector_error"]
    fe_count = 100 * fe["atom_observations"] / dev["atom_observations"]
    cache = result["cache_reconciliation"]
    lines = ["# 冻结536模型：614帧同坐标ML–DFT力误差", "", "日期：2026-11-17。已完成19,631个可动原子观测的逐原子比较；没有训练、模型重选、优化、GPU重算或DFT提交。", "",
             "## 1. 数据与口径", "", "输入为BUCT3作业436回收的冻结536原生ASE预测，与原536训练+78开发DFT标签逐项绑定。checkpoint SHA为`2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0`。614个ID、坐标SHA、原子序、力形状和有限性均经过来源守卫；固定底18个Fe不计入统计。53测试和16隔离帧未用于本轮。", "",
             "严格E/F/局域磁矩证据为训练285帧、开发18帧；其余训练251、开发60沿用原审核force-only范围。资格不变。下文同时列全范围和严格子集，不能把组成/受力分布不同导致的误差差别归因于磁性等级。训练误差不是独立验收；开发也不替代53保留测试。", "",
             "`ΔF_i=||F_ML,i−F_DFT,i||`；向量RMSE为`sqrt(mean ΔF_i²)`，向量MAE为`mean ΔF_i`。分量MAE、按帧均值、按来源均值均另列，不混为同一指标。方向余弦仅统计两力范数均>1e-8的原子；接近零力时方向敏感，不能单凭平均余弦判定优化稳定性。", "",
             "## 2. 整体和原子角色", "", "| 范围 | 帧数 | 向量RMSE（eV/Å） | 向量MAE（eV/Å） | 最大向量误差（eV/Å） |", "|---|---:|---:|---:|---:|"]
    for partition, label, scope in [("train", "训练：原资格全范围", "ALL"), ("development", "开发：原资格全范围", "ALL"), ("train", "训练：严格证据", STRICT), ("development", "开发：严格证据", STRICT)]:
        value = select(result, partition, scope=scope)
        lines.append(f"| {label} | {value['frames']} | {value['vector_RMSE_eV_A']:.6f} | {value['vector_MAE_eV_A']:.6f} | {value['maximum_vector_error_eV_A']:.6f} |")
    lines += ["", "原78开发帧的原子角色统计（含18严格+60原force-only范围）：", "", "| 角色 | 原子观测数 | 向量RMSE | 向量MAE | 最大误差 | 平均非零方向余弦 |", "|---|---:|---:|---:|---:|---:|"]
    for role in ("adsorbate_C", "adsorbate_O", "adsorbate_H", "near_Fe", "other_Fe", "all_movable_Fe"):
        value = select(result, "development", role)
        lines.append(f"| {ROLE_NAMES[role]} | {value['atom_observations']} | {value['vector_RMSE_eV_A']:.6f} | {value['vector_MAE_eV_A']:.6f} | {value['maximum_vector_error_eV_A']:.6f} | {value['mean_cosine_nonzero']:.4f} |")
    lines += ["", f"本表误差单位均为eV/Å。可动Fe占开发原子观测{fe_count:.2f}%，贡献平方向量误差总和{fe_share:.2f}%；C/O每原子RMSE更大，近邻Fe也明显高于其他Fe。因此不能将失配归为Fe唯一主因。全开发集平均方向余弦为{dev['mean_cosine_nonzero']:.6f}。", "",
              f"![固定结构力误差]({(OUT/'固定结构力误差.png').as_posix()})", "", "## 3. C₂/C₃与低力覆盖", "",
              "| 训练低力范围（DFT最大力≤0.05） | 帧数 | 来源根数 | 向量RMSE | 向量MAE |", "|---|---:|---:|---:|---:|"]
    for composition in ("C2H3", "C3H2O"):
        value = select(result, "train", composition=composition, phase="near_le0p05")
        lines.append(f"| {composition} | {value['frames']} | {value['source_roots']} | {value['vector_RMSE_eV_A']:.6f} | {value['vector_MAE_eV_A']:.6f} |")
    lowc3 = select(result, "train", composition="C3H2O", phase="near_le0p05")
    c3c = select(result, "train", "adsorbate_C", composition="C3H2O", phase="near_le0p05")
    c3o = select(result, "train", "adsorbate_O", composition="C3H2O", phase="near_le0p05")
    c3fe = select(result, "train", "all_movable_Fe", composition="C3H2O", phase="near_le0p05")
    rep = select(result, "train", composition="C3H2O", phase="near_le0p05", population="radius_representatives")
    final = next(r for r in result["frames"] if r["sample_id"] == "family_0099_step020_job9924387_opt133")
    lines += ["", f"24帧完整C3低力标签均来自0099；按既有0.10 Å、力区间、资格和连接配位分层，只有3个代表。全原子RMSE为{lowc3['vector_RMSE_eV_A']:.6f}，但吸附C/O/可动Fe分别为{c3c['vector_RMSE_eV_A']:.6f}/{c3o['vector_RMSE_eV_A']:.6f}/{c3fe['vector_RMSE_eV_A']:.6f}。只取3代表时全原子RMSE为{rep['vector_RMSE_eV_A']:.6f}；这些仍是同来源训练标签，不能称独立验收。", "",
              f"具体到`{final['sample_id']}`，同坐标DFT最大力{final['DFT_fmax_eV_A']:.6f}，ML最大力{final['ML_fmax_eV_A']:.6f}，ML最大力位于吸附C；两者对0.02数值阈值判断不同。这支持低力残余力偏差的诊断，不证明实际优化轨迹偏移或某个稳定极小值。", "",
              "C2H3低力4帧也只有一个旧来源（10_B），局域磁矩证据缺口保留；开发C2H3仅1帧且为高力。开发C3H2O的9帧全部高力且不满足完整单组分+C—C骨架连通；没有独立完整C3近稳定验收数据。按组成汇总时包含解离环境；JSON另有`intact_connected`和`CO_plus_C2H2`分组，不将CO+C2H2当完整C3。", "",
              "## 4. 小ML力、大DFT力构型", "", "主诊断阈值沿用ML最大可动力≤0.05且DFT>0.10 eV/Å：5训练+1开发，共6帧，均属于原force-only资格范围。它们是固定DFT坐标上的预测，不是本轮ML优化终态。", "",
              "| 结构ID | 分区 | ML最大力 | DFT最大力 | 最大DFT力角色 | 最大向量误差角色 |", "|---|---|---:|---:|---|---|"]
    for row in result["primary_flagged_frames"]:
        lines.append(f"| {row['sample_id']} | {row['partition']} | {row['ML_fmax_eV_A']:.6f} | {row['DFT_fmax_eV_A']:.6f} | {ROLE_NAMES[row['maximum_DFT_force_role']]} | {ROLE_NAMES[row['maximum_error_role']]} |")
    lines += ["", "6帧的最大向量误差有5帧位于C、1帧位于近邻Fe。严格证据303帧中没有满足该主阈值的个案；不能把6帧的磁性证据升级为完整，也不能把原审核force-only资格自动撤销。它们已经有DFT标签：不为这些相同坐标再提交单点。开发帧08_B_step111仍留开发分区，不转入训练。", "",
              "辅助敏感性阈值ML≤0.10且DFT>0.10得到27帧，逐帧文件保留标记；这不是新增验收标准。反方向也存在：DFT≤0.05而ML>0.05有训练7、开发2帧。平均力误差较小并不保证最大力阈值同时通过。", "",
              "## 5. 缓存与本次推理的口径", "",
              f"同一冻结checkpoint的旧开发角色加权MAE缓存为{cache['cached_development_role_weighted_vector_MAE_eV_A']:.9f}，本次ASE逐帧按原开发权重重算为{cache['current_ASE_development_role_weighted_vector_MAE_eV_A']:.9f}，相对差{cache['current_minus_cache_percent']:.3f}%。这不是模型改善：权重未变，两套预测数值尚未严格复现。也不能将角色加权MAE与原子加权MAE {dev['vector_MAE_eV_A']:.9f}直接比较。", "",
              "已确认训练执行入口含`--amp`；与实际GPU执行哈希相同的ASE定制源码默认`disable_amp=True`，并将trainer.scaler置空。两条数值路径存在明确精度设置差别。其是否完整解释3.11%差异仍为Needs confirmation，尚未做同精度重放；本轮不启动新推理。坐标SHA和相同checkpoint绑定保证本次固定结构比较的来源，并不保证复现训练缓存。", "",
              "## 6. 已确认、假设和后续边界", "",
              "已确认：C/O每原子误差高于Fe；近邻Fe高于其他Fe；低力C3平均误差掩盖部分吸附C/O偏差；6个主阈值失配个案已有标签；完整C3近稳定开发/独立验收缺口仍在。", "",
              "待验证假设：均匀训练中Fe平均占84.46%权重，可能影响吸附质/阶段误差分配；优化阶段和角色差异化加权可能改善交接，但单个模型比较不能证明因果或收益。不能从本轮结果认定536优于/劣于512，不能推断VASP离子步、SCF或核时下降。", "",
              "既有176类无同坐标标签的环境缺口和上一轮20个备选仍没有本模型的真实ΔF；不从相邻环境借用误差，不分配新增DFT预算，不调整512/536包或78/53/16。训练/开发、来源均衡和几何代表敏感性结果分别保存在分组CSV，不把449个代表称统计独立样本。", "",
              "下一步建议：先制定与原生FP32推理口径一致的角色/优化阶段加权对照方案，优先复用现有训练标签；本轮不训练、不补标。", "", "## 7. 交付与验证", ""]
    for name, label in [("逐原子力比较.csv", "19,631个可动原子逐原子比较"), ("逐帧力误差及交接风险.csv", "614帧误差与阈值标记"), ("误差分组汇总.csv", "训练/开发、资格、组成、力阶段与来源敏感性汇总"), ("same_coordinate_force_diagnosis.json", "完整诊断与来源哈希"), ("precision_context.json", "精度口径证据")]:
        lines.append(f"- [{label}]({(OUT/name).as_posix()})")
    lines += ["", "复用原分析器的9项测试，并新增固定Fe排除、来源均衡、完整/解离分组和角色互斥的4项数学守卫测试。实际完整性、统计守恒和冻结包检查见`verification.json`；这些检查不构成模型科学验收。报告按report-quality-gate核对语言、单位、数字、链接与事实/假设边界，图像需实际打开检查。", "",
              "RSI按约定仅调用一次；内部状态BLOCKED，1个模型回合、资料工具执行0，原因是服务连接失败。未重试，也没有产生可用诊断建议；最终数值来自直接读取的本地标签和预测文件。", "",
              "[RSI看板](C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html)。", ""]
    with (directory / "README.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))


if __name__ == "__main__":
    result = load_json_object(OUT / "same_coordinate_force_diagnosis.json")
    precision_context()
    plot(result)
    report(result)
    print({"report_created": True, "frames": len(result["frames"]), "atom_comparisons": result["movable_atom_comparisons"]})
