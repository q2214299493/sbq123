# Stage A.2.5 / P5 — VASP OUTCAR 解析职责

发布基线为 `327b30fea9e071770806da03b852051104bb1403`。Windows 开发树位于独立的开发历史 `233d5a6c589560094a0e942b6d48708b1fd5a847`，带有既存修改。两树拟编辑的五个已有 Python 文件在修改前逐字节相同。各树分别应用局部改动。

## 解析职责与调用关系

| 观测或判定 | 实现归属 | 输出约定与调用方 |
| --- | --- | --- |
| OUTCAR、OSZICAR 的通用结果 | `scripts.neb_agent.utils_vasp.parse_outcar / parse_oszicar` | 分别记录电子步、EDIFF、离子步、收敛标记、正常结束标记、磁矩、能量与力。OUTCAR 的 sigma→0 能量、可选 TOTEN 和末步逐原子力，以及 OSZICAR 的 F 各有独立含义。`vasp_result_gate` 据此评估最终电子和弛豫状态。 |
| 吸附与气相报告 | `adsorption.analyze_fe110_ch_h_relaxation`、`adsorption.finalize_step12a_gas_references` 及 `adsorption.review_completed_batch` | 既有专用适配器委托通用解析器提供收敛事实。前两者保留历史 TOTEN 匹配、力块终止及报错行为，分别汇报可动原子的最大力和索引、气相参考的力与异常标记。 |
| 振动行、频谱、结构与原始字节绑定 | `scripts.vasp_vibrations.frequency_header / parse_frequency_outcar` | 行记录保留频率数值和虚频标志。频谱接口按原约定给虚频加负号，单位 cm⁻¹。模态从 1 编号，原子映射从 0 编号。Cartesian 活动自由度来自各轴 T/F；缺失或重复编号报错，连续但自由度数目不符时返回显式标志和未评审状态。 |
| 本征矢、反应坐标及 TS 等级 | `ts_validation.analyze_vfa` 及原有审核门 | `_frequency_modes` 共享行读取，解释显式原子编号或 VASP 默认行序、位移及主导原子。`analyze_vfa` 结合结构、审核和来源绑定判定 Grade A。 |
| NEB 图像与路径 | `neb_agent.analyze_neb_outputs`、`path_quality_control` 等 | 通用读取器分别提取原子 max/RMS 与 VTST 垂直真实力。NEB 模块按图像解释力趋势、最大能量图像和收敛性。路径审核、几何和连通性使用原有协议。 |
| 热化学与 intake | `thermochemistry.frequencies.draft_intake`、`thermochemistry.engine / harmonic` | 观测可转为待审 intake。ZPE、热焓、熵、Gibbs 修正以及已审 TS 模态的排除继续由热化学模块负责。 |

修改前，热化学频谱读取器依赖 `ts_validation.analyze_vfa.frequency_header`。修改后，TS 和热化学分别引用 `vasp_vibrations` 的同一实现。该模块只依赖既有的数值验证、POSCAR 读取和文件哈希。通用 VASP 解析器和 NEB 路径分析之间的边保持原样。

旧入口 `thermochemistry.frequencies.parse_outcar(outcar, poscar)`、`ts_validation.analyze_vfa.frequency_header(line)` 和热化学 CLI 均保留。单参数通用 OUTCAR 接口继续支持原有关键字选项。架构测试分别检查实现唯一性、兼容入口的函数对象和依赖方向。维护范围内的导入图覆盖函数内部导入。开发树由 332 个模块、1163 条边变为 333 个模块、1166 条边；发布树由 291 个模块、1059 条边变为 292 个模块、1062 条边。四次扫描均为零环。

## 科学兼容性

- 两树的代码分别只读打开同一批已封存的本地原始文件。每树 45 个来源的 SHA-256 及四类解析结果的完整载荷摘要在 P5 前后相同。频谱 CLI 的 1662 字节 stdout 在两树完全一致。原始字节哈希与序列化结果哈希分列在 [验证回执](validation.json)。
- Fe(110) CH* + CO* → CHCO* 有 12 个模态，活动原子为零基的 45–48。第 12 模为 −318.644011 cm⁻¹，VFA 的模态和本征矢记录与历史报告一致，维持 Grade A。热化学仍按原记录排除第 12 模。TS 局部 ZPE 为 0.51405165 eV，正、逆电子能垒分别为 0.97360174、0.31429371 eV。端点热化学仍缺，MKM 维持 blocked。
- 开发树的完整 VFA 结果与封存报告逐字段一致。发布树使用自己的生产配置和验证流水线配置，VFA 的来源清单保留对应的路径和文件哈希；其余字段与封存报告相同。与 Phase 2.2 的旧热化学报告相比，当前结果多出既存的 `states.TS.subspace_verified` 字段。
- 对 CHCO 的历史 NEB 路径只读重放全部八幅图像。能量、力历史、SCF 和每幅图像的完整行均与封存报告一致，最高能量图像仍为 05。归档报告另含路径审核和几何验证信息；单独调用诊断读取器只生成它负责的层级。回执列出与归档不同的十个顶层字段，这些差异在 P5 前已存在。
- 发布树基线回放最初在回执整理时遇到独立工作树配置路径的归属错误。在相同逻辑路径使用经 `git show` 核对的原始发布基线解析文件重新只读回放，分别记录两个配置来源。两树均未运行科学求解器，未修改原始证据或生产 SQLite。

## Windows 实测

| 测试或检查 | 开发树 | 独立发布树 |
| --- | --- | --- |
| 修改前，同组 189 项 | 187 通过，2 失败 | 188 通过，1 失败 |
| 修改后，相同组加 6 个新用例 | 194 通过，1 项既有失败 | 195 通过 |
| 补充测试，解析归属、力流、B2/B2.1 科学合同 | 170 通过 | 169 通过 |
| 修改后的专项合计 | **364 通过，1 项既有失败** | **364 通过** |
| 六个变更 Python 文件的 py_compile、Ruff 和兼容导入 | 通过 | 通过 |

原有重复归属断言在两树均转为通过。新增用例覆盖缺少整个谱、首模缺失、中间跳号、重号、连续但不完整的 Cartesian 子空间及公共入口归属。既有测试继续验证 D 指数、显式与默认原子索引、部分 Hessian、虚频反应坐标、截断的 OUTCAR、普通力和 NEB 力。P1–P3 架构边界与 P4 的 B6 治理回归均通过。完整文件组及测试计数见 [验证回执](validation.json)。

开发树保留一项修改前即复现的失败，`tests/test_code_structure.py::test_ts_engine_layers_do_not_recombine`。本地未跟踪文件 `scripts/ts_strategy_engine/paper_sequential.py` 有 750 行，现有测试上限为 400 行。该文件未进入发布树，断言保持原样。补充测试数量相差一项，因为只有开发树含 `tests/test_outcar_numbered_ediff.py`。本轮验证范围为专项测试。

## 精确变更清单

- `scripts/thermochemistry/frequencies.py`
- `scripts/thermochemistry/__main__.py`
- `scripts/ts_validation/analyze_vfa.py`
- `scripts/vasp_vibrations.py`
- `tests/test_thermochemistry.py`
- `tests/test_code_structure.py`
- `reports/multiphase/stage_a2_5/completion.md`
- `reports/multiphase/stage_a2_5/validation.json`
- `reports/multiphase/stage_a2_5/handoff.md`
- `modules/state_handoff/events/history-stage-a2-5-outcar-ownership-20261121.json`

State Handoff 的两树处理结果及待审选择见[交接回执](handoff.md)。
