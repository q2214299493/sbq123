"""Read back exact metadata mutations and write a compact review deliverable."""
from __future__ import annotations

from pathlib import Path

from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.artifact_io import load_json_object, source_file_manifest
from scripts.registry_connection import open_registry
from .collect import OUTPUT, ROOT, scope

REPORT = ROOT / "docs/reviews/fe110_grouped_qc_20261026"


def readback():
    batch = load_json_object(OUTPUT / "registry_batch.json")
    receipt = load_json_object(OUTPUT / "registry_receipt.json")
    assert receipt["inserted"] == 138 and receipt["updated"] == 14
    checks = 0
    with open_registry(ROOT / "data/project_registry.sqlite3") as connection:
        for row in batch["rows"]["files"]:
            stored = connection.execute("SELECT * FROM files WHERE file_id=?", (row["file_id"],)).fetchone()
            assert stored is not None and all(stored[key] == value for key, value in row.items())
            checks += 1
        for row in batch["rows"]["job_status_history"]:
            stored = connection.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND checked_at=?",
                (row["job_record_id"], row["checked_at"])).fetchall()
            assert len(stored) == 1 and all(stored[0][key] == value for key, value in row.items())
            checks += 1
        for row in batch["workflow_status_changes"]:
            stored = connection.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (row["calculation_id"],)).fetchone()
            assert stored["workflow_status"] == "done"
            checks += 1
        results = sum(connection.execute("SELECT count(*) FROM results WHERE calculation_id=?", (r["calculation_id"],)).fetchone()[0]
                      for r in batch["workflow_status_changes"])
        assert results == 0
    result = {"status": "PASS", "exact_rows_or_projections_checked": checks, "accepted_or_other_results_for14jobs": results,
              "source_files": source_file_manifest([Path(__file__), OUTPUT / "registry_batch.json", OUTPUT / "registry_receipt.json"])}
    save_once(OUTPUT / "registry_readback_v3.json", result)
    return result


def deliver():
    checked = readback()
    summary = load_json_object(OUTPUT / "summary.json")
    replay = load_json_object(OUTPUT / "independent_verification.json")
    candidates = load_json_object(OUTPUT / "eligible_training_candidates.json")["samples"]
    proposed = load_json_object(OUTPUT / "recommended_small_supplement.json")["samples"]
    REPORT.mkdir(parents=True, exist_ok=True)
    fields = ("sample_id", "composition", "source_job_id", "ionic_step", "origin", "structure_path", "structure_sha256",
              "movable_fmax_eV_A", "magnetic_review_level", "graph_signature", "data_qc_status")
    proposal_ids = {r["sample_id"] for r in proposed}
    save_once(REPORT / "candidate_index.json", {"candidate_root": str(OUTPUT), "candidates": [
        {**{key: row[key] for key in fields}, "recommended_first_round": row["sample_id"] in proposal_ids} for row in candidates],
        "recommended_count": len(proposed), "training_authorized": False, "is_training_package": False})
    lines = ["# Fe(110) 定向14份结果回收与训练帧审核 — 2026-10-26", "",
        "**14份结果全部回收；12个单点与160个优化帧共172帧，171帧通过物理标签审核。排除2个已有单点标签的优化起始帧后，有169帧可用候选；首轮建议27帧：11个单点＋两条优化轨迹各8帧。**", "",
        "候选不是新训练包；原366帧训练包、485帧审核视图、开发/测试隔离与已有磁性等级均保留。没有续算、重试、提交新DFT、GPU计算或模型训练。", "",
        "## 回收与逐帧检查", "",
        "- 原生14份提交回执逐项匹配；读取14个真实作业号，均为DONE。全部回收文件SHA256与远端一致，原提交INCAR/POSCAR/KPOINTS/script及POTCAR哈希一致；POTCAR正文留在远端。",
        "- 单点沿用validate_static：正常结束、严格SCF/NELM边界、原始力/ASE解析一致、坐标与冻结POSCAR一致、完整局域磁矩及固定层检查。",
        "- 优化逐帧按OUTCAR离子编号关联SCF、局域磁矩、原始坐标/力表与TOTEN；对照OSZICAR、独立ASE输出和XDATCAR。保存原始力表字节范围及SHA256；全80帧均审核，未借用最终帧的收敛或磁矩。",
        "- 171个通过帧均属于原train来源；按真实Fe(110)表面对称、XY周期和同元素排列，与513个保留几何进行了24,120次适用比较，0冲突。只读取保留几何，不使用其能量或力进行选点。",
        "- 新标签保留LOCAL_MOMENTS_REVIEWED_POSITIVE_FE等级。Fe局域磁矩均为正仅支持当前分支审核，不证明磁基态；旧10_B仍为LEGACY_TOTAL_MAGNETIZATION_ONLY，没有升级。", "",
        "## 排除与候选数量", "",
        "`family_0021_step004`（9922612，C2HO）达到NELM=200：末次ΔE=-9.8411e-5eV、Δε=-2.1269e-5eV，相对于EDIFF=1e-6eV未达阈值。尽管OUTCAR包含EDIFF终止文字，既有严格门槛要求iteration<NELM，因此排除。原生通用SCF摘要的标志不能覆盖这一边界；未重算。", "",
        "两个优化第1帧与原提交起点一致，且已有审核单点标签，故从新增候选中排除；保留其审核证据。其余同一轨迹只有几何RMSD≤0.02Å且最大可动原子力差≤0.02eV/Å同时成立才可视为冗余；本批无满足条件的额外冗余帧。169帧=11个单点＋158个优化后续帧，不表示169帧都必须加入首轮训练。", "",
        "首轮27帧按每条轨迹的连接图和既有受力区间先选代表，再补充离子步分布，最多8帧/轨迹；不是SOAP重新选点，也没有根据测试误差选点。未被推荐的142帧仍保留为合格备用。", "",
        "## 优化轨迹结果", "", "|来源|帧数|SCF末次迭代范围|Fe局域磁矩范围/μB|最小可动原子最大力/eV Å⁻¹|对应步|最终力/eV Å⁻¹|", "|---|---:|---|---|---:|---:|---:|"]
    for t in replay["trajectories"]:
        lines.append(f"|{t['sample_id']}|80|{t['SCF_iteration_range']}|{t['Fe_local_moment_range_muB']}|{t['minimum_movable_force_eV_A']:.6f}|{t['minimum_force_ionic_step']}|{t['final_movable_force_eV_A']:.6f}|")
    lines.extend(["", "两条轨迹均正常结束于80步上限，离子未收敛；逐帧距离图均保持原连接且为一个连通分量（几何诊断，不是电子成键证明）。本批没有可动原子最大力≤0.05eV/Å的帧，不能声称已补齐近稳定锚点或证明吸附最低点。中间帧的力标签资格与父优化是否收敛分别审核。", "",
        "## 首轮建议27帧", "", "|构型|组成|作业号|离子步|可动原子最大力/eV Å⁻¹|用途|", "|---|---|---|---:|---:|---|"])
    for row in proposed:
        purpose = "既定定向局域环境单点" if row["origin"] == "new_static" else "下降轨迹受力区间代表"
        lines.append(f"|{row['sample_id']}|{row['composition']}|{row['source_job_id']}|{row['ionic_step']}|{row['movable_fmax_eV_A']:.6f}|{purpose}|")
    lines.extend(["", "完整169帧索引见candidate_index.json；本地候选标签见：", "",
        "- `calculations/fe110_reico_pilot300_20261022/grouped_qc_20261026_v2/eligible_training_candidates.json`",
        "- `calculations/fe110_reico_pilot300_20261022/grouped_qc_20261026_v2/recommended_small_supplement.json`", "",
        "## 验证与登记", "",
        "202项直接相关测试通过；语法、Ruff通过。独立复核171个合格原始力标签、169个候选结构/力/能量元数据源绑定和27帧建议清单通过；366/485源哈希保持不变。", "",
        f"登记仅新增124条文件元数据和14条DONE观测（138 INSERT），更新14个工作流完成投影；{checked['exact_rows_or_projections_checked']}项精确回读一致。这14个作业的results记录仍为0，没有登记接受的吸附能或端点。计划SHA：`7437412a8c63943ccb0598f93850cabdca25ca1a9f0ddf67e0f0c82b8c5bd282`。", "",
        "初次回收v1因SSH标准输入脚本传递超时，未下载数据；失败与原代码保留。v2用已验证的系统Python及无标准输入的命令传递，随后小样本回收通过，再完成全部14份。没有覆盖失败证据或重提交作业。", "",
        "尚未组装新的训练包、重算189类缺口/SOAP覆盖、验证新模型精度或测量优化加速。下一步是以27帧建议作为新训练包组装输入，继续保留数据隔离和磁性等级；训练须另行授权。", ""])
    path = REPORT / "README.md"
    data = "\n".join(lines).encode("utf-8")
    if path.exists():
        assert path.read_bytes() == data
    else:
        path.write_bytes(data)
    save_once(REPORT / "checkpoint_v3.json", {"summary": {k: summary[k] for k in (
        "jobs_recovered", "frames_reviewed", "qc_counts", "eligible_candidates", "recommended_candidates")},
        "registry_readback": checked, "source_files": source_file_manifest([
            Path(__file__), OUTPUT / "summary.json", OUTPUT / "independent_verification.json",
            OUTPUT / "registry_receipt.json", OUTPUT / "tests_primary.xml", path, REPORT / "candidate_index.json"]),
        "runtime_outputs_local_only": True, "new_DFT_GPU_or_training": False})
    print({"report": str(path), "metadata_readback": checked["exact_rows_or_projections_checked"],
           "eligible": len(candidates), "recommended": len(proposed), "native_receipts": len(scope())})


if __name__ == "__main__":
    deliver()
