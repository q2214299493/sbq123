# B.2.3.2.1 Zacros 多相映射审计

**仓库基线 `abd47e9800335da0f57732d7493dce2b760fd18d`。** 审计确认 Zacros 4.0 能按带类型的有限晶格图表示不等容量、同一分子的多齿占位、局部反应以及方向计数。项目 Ni/Cu 基准已有跨两个项目库存的单分子双齿原生回执。合成氧化物的七节点空间配置仍不完整，B.2.2.2 的指定转移、B.2.2.3 的指定四节点反应及三相产物也需各自绑定原生事件、动力学及接触几何。具体状态和证据边界见[能力矩阵](capabilities.md)、[字段映射和受限拓扑](mapping.md)、[氧化物配置缺口](oxide.md)与[原始证据索引](evidence.json)。

## Ni/Cu 离线回归及可选对照重放

- 初始全空的合成 Ni/Cu 基准为 3×3 重复，每个基元一 Ni 一 Cu，合计 18 个节点。晶格上的 18 个异类匹配对应 9 个参考位点，每参考位点 2 个匹配。分母用于系数转换。B.1 的观测速率以整张模拟晶格每秒的事件数报告。
- `dent` 的 `H2-bridge` 属于 `junction`，归档别名为 `HCu*`。原生 `r1_forward` 的产物两行都用实体 1；`r2_reverse` 在同两类节点匹配腿 1、2。初态为节点 (1,2) 上一个实体，原生报告 16 个初始匹配。反序 seed 的历史诊断只剩 15 个，缺少解吸；该差别能识别单纯检查退出码发现不了的映射错误。
- 原生进程终止于事件 20；两个统计文件的共同采样窗是事件 0–19，时长 0.020951458831958522 s。窗内正向 13、逆向 6，桥式分子数从 1 增至 8，气相净交换 −7。该结果是合成基准单轨迹的有限窗口观测。重启、吸引/排斥簇、吸收态时钟及已知原生警告均沿用各自回执。[项目原生回执](../phase2_5_1/zacros_validation.json) · [B.1 轨迹重放](../stage_b1_4/replay/zacros-dent.json) · [反序 seed 诊断](../phase2_5_1/dentate_order_diagnostic.json)

只有已封存的 Ni/Cu `dent` 对照在本审计中具备以下**可复核的重放规格**。现有归档已足以判断该能力，本次没有执行需要。若以后有复现需求，应按该次精确输入与可执行文件重新取得独立授权。

| 项目 | 已有证据支持的对照重放规格 |
| --- | --- |
| 输入 | 从 `phase2_5_1/benchmarks/dent.zip` 取 manifest 中的五个输入，核对 ZIP、manifest 和五个原始成员 SHA-256。独立空目录，无 restart.inf。实际哈希见证据索引 `project_native_archives.dent`。 |
| 引擎与边界 | 项目留存的 Zacros 4.0 二进制 SHA-256 为 `84a8f88d6df633eeea9eeac8aa9227237cdf2564a4dc72e0cab8a18c4ce119d2`。使用原始无参数单进程入口，400 K、1 bar H₂、seed 13201。模型上限 20 步、模拟时间 0.1 s、原生墙钟 15 s、外层 30 s。若以后批准，最多一次启动。 |
| 预期与失败处理 | 原生成功读入五个输入，初态 16 个匹配，20 个事件后正常终止；核对晶格及计数文件的同构建固定种子轨迹与归档值。日志应记录版本、终止原因和警告 4008。按原始字节归档输出和耗时；达到超时、计数不符或异常退出即停止并保留部分结果。不得用日志内的运行日期或墙钟文本作为轨迹等价条件。 |

氧化物 CO₂ 暂无以上输入和数值依据，无执行计划。若研究者只验证软件，明确声明并评审的合成七节点配置即可作为空间证据；验证真实催化剂则需相应的结构和动力学来源。CATKINAS 的覆盖度分母不参与该决定。

## 两棵工作树的验证

| Windows 工作树 | 改动前 | 加入本轮测试后 | 本轮 Python 检查 |
| --- | --- | --- | --- |
| 开发树，`refactor/v2-architecture-repair`，HEAD `233d5a6c` | 655 通过，8 排除，31.49 s | 658 通过，8 排除，35.35 s | py_compile、Ruff 通过 |
| 独立发布树，任务分支从 `abd47e98` 起 | 655 通过，8 排除，31.49 s | 658 通过，8 排除，34.68 s | py_compile、Ruff 通过 |

专项回归包括 B.1 速率/单位/源项和原生输出，B.2 库存、身份、转移及跨相反应，原有 CATKINAS 映射、Zacros 输入、重启和成组归档。新增两种合成图的匹配数反例、一项 Ni/Cu 原生实体和通用界面双向映射回读。8 项 `test_native_zacros_replay` 参数化用例会启动原生进程，均在收集时显式排除。本轮执行的是限定回归，原生启动 0 次。

复现上述后测可在任一工作树根目录使用

```powershell
C:/Anaconda/python.exe -m pytest -o addopts= -q tests/test_zacros_multiphase_mapping_audit.py tests/test_native_model.py tests/test_native_advanced.py tests/test_native_rate_adapters.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_kinetic_parameters.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_multiphase_identity.py tests/test_interphase_transfer.py tests/test_cross_phase_elementary.py tests/test_reaction_network.py tests/test_catkinas_network_mapping.py tests/test_catkinas_oxide_multidentate_audit.py -k "not test_native_zacros_replay" --tb=short
```

另按基线 Git 对象与两树工作文件逐字节核对 40 项来源，包括 8 个项目归档及原始模型、适配器实现和数据契约记录。逐项核对归档清单与回执列出的输入输出哈希。发行包中 102/103 两个示例绑定了 19 个输入输出成员。对 102 的末帧比对了物种数、空间快照、腿号及格点类型；对 103 使用了不同位点类型间原生跳跃的正反过程统计。[来源与哈希](evidence.json)

## 本轮文件清单

- `modules/surface_kmc/README.md`
- `tests/test_zacros_multiphase_mapping_audit.py`
- `reports/multiphase/stage_b2_3_2_1/capabilities.md`
- `reports/multiphase/stage_b2_3_2_1/mapping.md`
- `reports/multiphase/stage_b2_3_2_1/oxide.md`
- `reports/multiphase/stage_b2_3_2_1/evidence.json`
- `reports/multiphase/stage_b2_3_2_1/completion.md`
- `reports/multiphase/stage_b2_3_2_1/handoff.md`
- `modules/state_handoff/events/history-stage-b2-3-2-1-zacros-mapping-audit-20261122.json`

本轮修改限于上述审计、测试、模块文档入口及待审历史事件。[State Handoff 实际回执](handoff.md)
