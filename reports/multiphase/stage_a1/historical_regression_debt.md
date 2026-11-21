# 五项历史回归债务

2026-11-21 在开发目录及独立发布树分别选择相同五个 pytest node。两处均 0 通过、5 失败。[逐测试断言](debt_test_evidence.json)保留两边实际测试名称和错误。215 项领域回归与以下五项单独计数。

| 债务和现状 | 精确测试（路径均位于 tests/） | 根因与两树差异 | 最小处理及回归 |
|---|---|---|---|
| Registry CLI 反向导入，仍存在 | test_b5_architecture_boundaries.py::test_domain_cannot_import_cli_or_skill_implementations | 两树均在 baseline_mkm/analysis.py 引用 registry_write 处首先失败。registration.py 也从该入口读取批校验。 | P1，从现有领域所有者导入；须核对原 CLI 和调用异常路径。 |
| 原生装配/适配器循环，仍存在 | test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic | 两树均有 native_model 和 surface_kmc.native 的回边，并有三组 DRC/灵敏度环。8 个实际导入探针均成功。 | P2 先拆原生回边，P3 分组拆报告回边。检查全图和旧模型/回执字节。 |
| 就绪程度生成视图漂移，仍存在 | test_b6_governance.py::test_readiness_generation_is_deterministic_and_matches_checked_in_view | 相同输入重复生成后，与提交的 capability_readiness.json 和 .md 字节不符。模块状态和派生就绪字段会随权威源变化。 | P4 区分固定历史视图和当前视图，双次生成比对以及来源检查。 |
| 热化学模块状态冲突，仍存在 | test_b6_governance.py::test_tests_and_status_do_not_invent_maturity_or_science | 两树当前 thermochemistry 为 Active，测试固定期待 Blocked；开发树另有 kinetic_data 为 Active 而测试期待 Planned，发布树无此附加差异。 | P4 用审核后的模块图作状态来源，用独立样例验证科学资格不随状态升级。 |
| OUTCAR 所有者命名冲突，仍存在 | test_code_structure.py::test_scientific_parsing_and_contract_validation_have_single_owners | 两树的预期列表有两个旧吸附近端和 NEB 工具；实测多了 thermochemistry/frequencies.py。用途与读取的物理量不同。 | P5 界定频率接口名称，保留 VFA 行语法的共享所有者。测试历史输入、无模态和虚频处理。 |

历史来源包括此前的 Phase 3.2.0.1 回归记录，本表结论以本轮两树直接复现为准。当前证据仅支持这些目标测试的结论。未运行全仓测试，不能由本表推断全仓恰有五项失败。
