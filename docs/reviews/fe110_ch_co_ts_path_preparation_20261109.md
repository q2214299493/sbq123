# Fe(110) CH* + CO* → [CH]–[C]–[O]*：端点与路径待审核

日期：2026-11-09，Asia/Shanghai。状态：**本地准备完成，待用户审阅；未提交 GPU、VASP 或训练作业**。

## 当前结论

可复用已有合格端点，不需要先新增吸附优化。目标是形成 C–C 键；CH 上的 H 保留，CO 的 C–O 不断裂。不是其他 C₂HO 异构体，也不按字符串中的星号数推断实际空位计量。

| 端点 | 已有作业/身份 | 最终 TOTEN / eV | 最大可动原子力 / eV Å⁻¹ |
|---|---|---:|---:|
| IS | 9839757，已重新审核登记的 CH* + CO* 共吸附态 | -385.14767079 | 0.01811889 |
| FS | 9842136，完整 [CH]–[C]–[O]* | -384.48836276 | 0.01157330 |

IS 原本按完整 CH–C–O 投入，最终 C–C 断开；原物种的拒绝记录保留，但实际 CH*+CO* 已单独合格登记。这里复用的是该重新分类的共吸附态，不把原失败当作完整分子成功。9842107 是 FS 的近重复，不作为另一个独立极小态。

两端完整参数记录一致：Fe45、五层、底部18原子固定、PBE/PAW-PBE、ENCUT400、5×5×1、ISPIN2、ISMEAR1、SIGMA0.20。已逐文件核对两个 CONTCAR 和两个 OUTCAR 的登记 SHA256。能量约定 `fe110_converged_toten_sigma0p20_v1`。现有端点反应能 **+0.65930803 eV**；这不是活化能，不含 ZPE、熵或自由能修正。

完整兼容性指纹：`52b8afbf5a2902cbe115001d2554440b59421d61e1819f5921ddc373da5839de`。

## 原子映射与几何

本次读回结构后确认零基索引：CH 的 C45/H48，CO 的 C46/O47；形成 C45–C46。该索引仅属于本任务，不是可复用模板。

原始 FS 与 IS 的空间放置不同。用真实 Fe(110) 清洁表面、保留吸附面的对称操作，**同时变换整个 FS 的 Fe 与吸附物**，然后仅重排等价 Fe 原子。没有自由分子拟合，没有交换两个 C 的化学身份。

- 对称操作的分数坐标旋转 `[-1,-1,0; 0,1,0; 0,0,1]`，平移约 `[2/3,0,0]`。
- 固定层变换残差约 `2.7e-8 Å`，仅该数值舍入归回原固定坐标；未优化或重新定义端点。
- 映射后 C45、C46、O47、H48 位移分别约 0.634、1.969、2.030、0.401 Å。
- IS 最近 Fe：C45–Fe40/41≈1.876 Å；C46–Fe41≈1.856 Å；O47–Fe39≈2.848 Å。
- 映射 FS 最近 Fe：C45–Fe40/41/43≈2.061/2.067/2.070 Å；C46–Fe43≈2.010 Å；O47–Fe44≈2.039 Å。

端点事件解析仍为 `REVIEW_REQUIRED`：CO 的平移/倾斜伴随 Fe 配位更换，且最大反应原子位移 2.03 Å 触发通用提示。没有遗漏目标 C–C 成键，也没有额外吸附物内部断键；这些配位与位移提示不被自动抹除，更不据此宣称已找到单一步 TS。

## 路径候选

本地目录：`calculations/fe110_ch_co_to_chco_ts_20261109/review_ready_v2/`。

采用一个约 2.02 Å 的 C–C 几何引导点，保留其 C–H/C–O 长度，再分段 IDPP。引导点不是预测鞍点，不是运行中的力约束。五张内部图像、两端共七张（00–06）；按约2 Å 的端点运动及几何分辨率选择，不沿用氢转移的 O–H 门限。所有49原子参与映射，底18原子固定，没有仅对 C/O 做插值。

| image | C–C / Å | C–O / Å | C–H / Å | 最近吸附物–Fe / Å | 最大相邻原子位移 / Å |
|---|---:|---:|---:|---:|---:|
| 00 | 2.787166 | 1.203031 | 1.103885 | 1.856432 | — |
| 01 | 2.522941 | 1.195955 | 1.096173 | 1.739496 | 0.333305 |
| 02 | 2.266863 | 1.210949 | 1.095646 | 1.678258 | 0.333305 |
| 03 | 2.022030 | 1.247217 | 1.102314 | 1.678823 | 0.333305 |
| 04 | 1.793052 | 1.242478 | 1.094570 | 1.741131 | 0.345988 |
| 05 | 1.586810 | 1.257435 | 1.094043 | 1.858985 | 0.345988 |
| 06 | 1.413291 | 1.291403 | 1.100743 | 2.009873 | 0.345988 |

Canonical `plan --initialize-path --images 5`：`NEEDS_PATH_REVIEW`；数值几何诊断 PASS。固定坐标和标志保留，分支展开连续，C–C 单调缩短。已实际执行原版 `dist.pl`（六组相邻结构）及 `nebmovie.pl 0`，检查七帧输出，并目视审阅 `path_review.png`。`path_review.json` 保持 `needs_review`，未伪造用户接受。

**风险**：中段最近 Fe–C≈1.68 Å，虽未触发碰撞门，仍可能造成较大的初始真实力。几何连续不代表低能、正确 MEP 或模型适用；不能直接把 image03 宣称为峰值或提交 Dimer。

关键输出：

- `endpoints/IS.vasp`、`FS_symmetry_mapped.vasp`、`waypoint.vasp`。
- `reaction_contract.json`：完整原子映射、登记端点及参数分支。
- `registered_endpoint_check.json`、`endpoint_event_validation.json`、`endpoint_provenance.json`。
- `plan/path_candidate/00–06/POSCAR`、`path_geometry_diagnosis.json`、`movie`、`path_review.json`。
- `dist.json`、`path_numeric_review.json`、`path_review.png`。

## 最小软件修正与验证

TS 合同原来丢弃登记参数的附加字段，并把含元素符号的 coverage/magnetic 标签改成小写，造成同一端点的指纹失配。现保留完整附加元数据与这两个科学标签的大小写，不改数据库、物理参数或旧合同文件。JSON 合同优先用 JSON 解析，避免 YAML1.1 把 `1e-05` 读取成字符串导致哈希失配。旧 YAML 输入仍受支持。

- 修改：`scripts/ts_strategy_engine/contract.py`。
- 新增：`tests/test_ts_contract_full_compatibility.py`；同指纹、元数据变化、非有限值拒绝、磁性/覆盖度标签、JSON 指数浮点往返。
- 已执行 py_compile、导入检查、限定文件 Ruff。
- 已执行四个相关测试文件：full_compatibility、strategy_engine、strategy_learning、endpoint_contracts，共99项通过；主工作区与独立发布工作树均退出码0。
- 本地一遍准备与一次路径生成成功；未用科学作业验证代码。

早期本地准备失败的文件保留在反应根目录；该次登记兼容性检查为 STOP，不可作为活动路径。活动目录仅为 `review_ready_v2/`。原始 VASP 源文件全部保持不变。

本轮 RSI 默认入口仅调用一次，因文件级 scope 不被该入口接受而在初始化拒绝（`invalid research task scope`）；未生成建议、未采用经验、未自动重试。以上结论来自本地已登记来源与实际几何检查，不是 RSI 背书。看板：`C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html`。

收尾 `repo-state sync --safe-only` 已执行一次，退出码2，原因是已有 `sbq_catalyst_agent_workflow.egg-info/PKG-INFO` 分类后变化冲突。未修改无关元数据、未重试或手改托管 current_task；本轮任务边界保存在本审核文档与 backlog。该同步失败不属于科学结果验证。

## 唯一下一步

用户审核路径后，单独授权受限 GPU ordinary ML-NEB，拟采用 MatRIS 主模型、AQCat25 完整同构复核。绑定前需重新查两台 GPU 的实时资源、任务环境、精确 checkpoint 和输入哈希；当前未选择主机或宣称该 C–C 偶联域已校准。GPU 回收至 work 审阅后，依据路径/峰形与必要的同构 VASP 能力验证选择粗/局部 NEB、CI-NEB 或 Dimer，不预设唯一流程。误差证据超标才申请微调；本轮不授权训练、重投或昂贵计算。
