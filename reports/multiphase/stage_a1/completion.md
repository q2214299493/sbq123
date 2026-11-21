# Stage A.1 多相催化架构审计完成报告

2026-11-21。现有证据足以复核从科学接收到合成闭环 MKM 的工作流，以及 Zacros 的有限晶格案例。通用 KMC 统计源项和理想反应器仍缺实现。可以先纠正分析层的 Registry 导入，再逐个解除循环依赖。Fe(110) 的实际 MKM 资格仍受其项目证据约束。

## 交付索引

| 交付 | 内容 |
|---|---|
| 1 | [架构地图与六维评估](architecture_map.md) |
| 2 | [模块职责与已验证范围](module_responsibilities.md) |
| 3 | [依赖图与复算口径](dependency_graph.md)，[完整邻接表、源码摘要及导入探针](dependency_graph.json) |
| 4 | [四组循环依赖](circular_dependencies.md) |
| 5 | [重复实现及解析边界](duplicate_implementations.md) |
| 6 | [科学数据契约图](scientific_contracts.md) |
| 7 | [跨尺度缺口及 Reactor 八项核查](cross_scale_gaps.md) |
| 8 | [五项历史回归](historical_regression_debt.md)，[两树断言](debt_test_evidence.json) |
| 9 | [三级文献基准提案](benchmark_proposal.md) |
| 10 | [最小实施顺序、风险和必需测试](minimal_refactoring_plan.md) |
| 11 | 本报告及[原生回执核查清单](native_evidence.json) |

## 现场版本与核查

开发目录位于 Desktop/work，分支 refactor/v2-architecture-repair，检查时 HEAD 为 233d5a6c589560094a0e942b6d48708b1fd5a847，包含本地开发修改。独立源发布树的 codex/multiphase-phase0-integration 检查基线为 818c7fa41df647fd7b0c0267999172c7c4691c3e。图中源码 SHA-256 对应实际读取的文件，开发树结果不可仅从其 HEAD 重建。

| 实施检查 | 开发目录 | 发布树 | 结论 |
|---|---:|---:|---|
| Scientific Intake、Thermochemistry、Reaction Network、Kinetic Parameters、Scientific Priority、MKM Analysis 六组 pytest | 215 通过 | 215 通过 | 局部行为回归；两栏是同一批用例 |
| 五项治理/架构债务逐一复现 | 5 失败 | 5 失败 | 状态期望的附加差异见债务表 |
| Fe 位点识别与未知晶面边界 | 4 通过 | 4 通过 | test_b5_architecture_boundaries 中的 test_unsupported_site_profile_never_uses_fe110_default 与 test_fe110_profile_preserves_supported_site_classes |
| 静态导入图及每个环的双顺序导入 | 328 模块、1150 边，8/8 可导入 | 287 模块、1046 边，8/8 可导入 | 两树均有 4 个循环分量 |
| CATKINAS 两份清单、Zacros 原生归档与内部输出的 SHA-256 | 全部匹配 | 全部匹配 | CATKINAS 5 个闭环来源和 3 个单点工件，Zacros 8 个归档、42 个输出成员 |

领域回归以 python -m pytest -o addopts='' -q 运行 tests 下的 test_scientific_intake.py、test_thermochemistry.py、test_reaction_network.py、test_kinetic_parameters.py、test_scientific_priority.py、test_mkm_analysis.py。架构测试节点见债务表。未运行全仓测试。原生数值来自已归档回执；本轮执行的是文件完整性、静态图、导入和测试检查。

Phase 3.0 单点记录的合成 Ni/Cu TOF 为 81.51277016 s⁻¹，分母详见该工况及 reference_site_pair 绑定；Zacros 八个案例的原生退出码记录均为 0。两者验证的可观察量不同。Fe(110) 只承担真实项目的证据检验，phase3_3_1/closure.json 的动力学合格步数为 0。现有原生结果没有提供任意催化剂的工业物相、位点密度、动力学参数或反应器验证。

本轮交付为审计文档与证据索引。生产 SQLite、原始计算文件、科学审批和执行门均未改动。未启动原生计算、反应器实现或 Stage A.2。**下一步为研究者审阅 P1，确认后仅调整两处 Registry 校验导入并运行针对性回归。**
