# Fe(110) REICO 首轮六个 DFT 单点探针

日期：2026-10-22。**六个 DFT 固定几何单点已通过规范执行器实际提交；12:53（Asia/Shanghai）快照为 1 RUN、5 PEND。尚无已接受的 DFT 标签或模型准确性结论。**

用户接受先做少量 DFT 参照、再判断是否让 ML 主导优化采样的流程，原话与本阶段具体范围见不可变的 `user_authorization.md`。本次把少量探针具体化为六个，属于原约 300 个构型标注预算，后续新构型标注最多剩余 294 个；本阶段不提交剩余构型，不运行离子优化、训练或自动重试。

## 选点依据

从已冻结的 99 个随机起点中，**只选训练分区**。C₂HO、C₂H₂O、C₂H₃ 各选一条家族；C₃H₂O 选三条，合计 C₂/C₃ 各三条。依据每个构型中“原子对距离 / 该元素对防碰撞下限”的最小值排序：三种 C₂ 组成取中位附近，C₃ 取 10%、50%、90% 分位附近。没有利用 DFT、ML 能量或模型误差选点。

| 家族 | 组成 | 几何排序分位 | 最小距离与对应下限之比 |
| --- | --- | ---: | ---: |
| family_0029 | C₂HO | 50% | 1.1454 |
| family_0002 | C₂H₂O | 50% | 1.1207 |
| family_0007 | C₂H₃ | 50% | 1.1304 |
| family_0078 | C₃H₂O | 10% | 1.0106 |
| family_0052 | C₃H₂O | 50% | 1.0740 |
| family_0004 | C₃H₂O | 90% | 1.1907 |

该排序只用于有限预算的几何分层，不代表能量高低或全空间代表性。`family_0078` 包含约 0.859 Å 的压缩 C–H 接触，保留为离平衡受力探针；它不是稳定分子或吸附终态。所有构型保持原始坐标，不先做 ML 松弛。各组成也不被解释为已确认的分子连接图。

来源汇总的原始字节哈希与第一步独立审核一致；六个 POSCAR 均与对应原始起点字节相同。开发集与最终测试家族未被用来选点。这六个点是将来训练分区内的诊断参照，不能作为独立最终测试或泛化证明。

## DFT 输入与执行边界

使用现有 `build_fe110_active_learning_force_label` 及 `configs/true_fe110_production.yaml`，没有复制旧 INCAR 作为模板或修改锁定的科学参数。

- PBE/PAW-PBE，ENCUT 400 eV，Gamma 5×5×1；Fe45 五层基底，原子顺序与底部 18 个固定 Fe 保留。
- ISPIN=2；Fe 初始磁矩 2.2 μB/原子，C/O/H 按 POSCAR 顺序生成初始零磁矩。
- ISMEAR=1、SIGMA=0.20 eV、ALGO=Fast；静态标注 EDIFF=10⁻⁶、NELM=200、LORBIT=11。
- NSW=0、IBRION=−1：固定几何总能量、全部原子力、总磁矩与局部磁矩。
- 每点 32 MPI 核，使用规范 `sunboquan-codex`/LSF 执行器及既有队列资源规则。
- 已核对规范 VASP 程序、环境以及 Fe/C/O/H、Fe/C/H 两套远端 POTCAR 全文哈希。POTCAR 正文不下载或写入 Git。
- 每个任务有精确输入、目标目录、POTCAR 和用户授权绑定的独立 `SUBMIT_DIAGNOSTIC_VASP` 门；原子坐标不经过 GPU 到 VASP 的直接传递。

六份诊断静态 preflight 通过；INCAR Custodian 的六份持久化验证全部 PASS，无参数变化、错误或警告。提交预约与实际提交回执分开保存；预约本身不证明成功提交，PEND/RUN 也不证明电子收敛。旧计算不停止、不更改或重新提交。

## 实际作业与注册

以下为 2026-10-22 12:53:24–25（Asia/Shanghai）的逐作业 LSF 原始输出及哈希快照。队列字段不代表电子收敛、磁性基态或标签合格。

| 家族 | LSF 作业号 | 调度状态 |
| --- | --- | --- |
| family_0029 | 9918415 | RUN |
| family_0002 | 9918416 | PEND |
| family_0007 | 9918418 | PEND |
| family_0078 | 9918420 | PEND |
| family_0052 | 9918423 | PEND |
| family_0004 | 9918425 | PEND |

远端根目录：`sunboquan-codex:~/sbq/Fe110/diagnostics/reico_probe6_20261022_v1/`。六个成功提交回执齐备，规范执行器核对了远端全部输入与复制后的 POTCAR；没有提交失败或自动重试。

已通过现有追加注册接口登记 6 个计算、6 个作业、8 个实际调度观察及 130 个输入/来源文件记录，共 150 行 INSERT、零 UPDATE。**这是作业和来源元数据，不是 150 个结构、能量或科学结果。** 没有写入 results、科学接受 reviews 或 Excel。注册 plan SHA256 为 `cc9550df612c0f14a9afe0f890468118a6054a6122ff9e514dc353bd2f0b3207`；保存了精确 plan、按本次执行授权审查的 approval 和成功事务 receipt。

## 输出位置与检查

主工作区包：`calculations/fe110_reico_pilot300_20261022/probe6_v1/`。

- `selection.json`：预测和 DFT 前冻结的六家族选择与来源。
- `batch_request.json`：规范输入、结构哈希与六包预算，历史状态为准备完成。
- `execution_plan.json`：六个有效执行门、具体远端目标及 POTCAR 绑定。
- 各家族目录：POSCAR/INCAR/KPOINTS/POTCAR.spec/script.lsf、参数验证、分析与结构审核、授权、执行门、提交预约和实际回执。
- `submission_summary.json`：六个实际提交回执齐备后生成；不存在时不得假设六个都已提交。
- `scheduler_summary.json` 与各目录 `scheduler_after_submission.json`：本次六作业的实际调度输出、查询时间及哈希。
- `submission_registry_{batch,plan,approval,receipt}.json`：现有注册接口的一次追加事务证据。
- `exact_prediction_plan.json`：后续同几何模型对照方案，当前不是可执行 GPU 请求。

源码入口为 `scripts/adsorption/reico_probe_batch.py`。它只准备输入，不包含上传、提交或模型调用。语法/导入、定向 Ruff 以及新选点测试和共享 VASP 构建器测试共 16 项通过；实际六包又经过独立参数验证与规范执行门核验。没有运行全仓库测试。

## 标签和模型判断

DFT 完成后检查正常结束、EDIFF 在 NELM 前收敛、原子序和固定坐标对应、完整原始力，以及总/局部磁矩。SCF 收敛不等于找到了磁性全局基态；磁态异常或标签不合格时保留原因，不自动追加多磁初态或重算。

计划在相同六个 POSCAR 上比较原始 AQCat25 与已冻结 control 的力，共最多 12 次固定几何预测。执行前仍须重新核对原生 checkpoint、CUDA、运行时和该六点范围；当前没有 ML 松弛或 GPU 预测结果。

比较重点是各吸附原子的力向量大小、方向、C/H/O 分组误差和压缩原子对的相对受力，Fe 误差单独报告，不用 45 个 Fe 的平均值掩盖吸附原子错误。不同预训练能量零点的裸总能量不直接当作能量误差比较。

六个点只能排查明显问题，不能证明全部 99 个随机环境都可信。如果当前模型明显错误，再具体准备小批 DFT 短程优化与初始能量–力模型；不能把六点诊断自动扩展为 99 条 ML 优化或新训练。

## 仓库状态同步

本轮 `repo-state sync --safe-only` 实际退出码为 1，仍被既有 `sbq_catalyst_agent_workflow.egg-info/PKG-INFO` 分类哈希不一致阻止。没有改写分类事件或包元数据绕过检查；本次六个提交回执、调度原始证据和注册事务均已另行核验。源码发布与该管理视图同步分别报告。
