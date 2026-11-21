# Stage B.2.1 · Windows 离线回归

开发树在 `refactor/v2-architecture-repair@233d5a6c589560094a0e942b6d48708b1fd5a847` 上保留已有修改。独立发布树及远端任务分支的起点为 `37d9e5529862e9fc3052ecda5d2d362aa76036fe`。更改前逐文件核对了所属实现、覆盖率 schema、模块文档、两个案例的原始输入与历史覆盖率快照，两树对应字节一致。

| 实际运行范围 | 开发树 | 发布树 |
| --- | ---: | ---: |
| 修改前，既有多齿覆盖与位点审阅 | 51 通过 | 51 通过 |
| 最终运行中，B.1.5 的完整离线专项组 | 596 通过 | 596 通过 |
| 最终运行中，既有多齿覆盖、位点审阅、反应网络 | 93 通过 | 93 通过 |
| 最终运行中，本轮库存计数专项 | 22 通过 | 22 通过 |
| **最终专项合计** | **711 通过，0 失败，39.39 s** | **711 通过，0 失败，38.85 s** |
| 4 个变更 Python 文件的 py_compile、Ruff 及覆盖率入口导入 | 通过 | 通过 |

两次最终运行分别从各自的工作目录启动。各排除一项 live CATKINAS 与八项 native Zacros 测试。本次未运行全仓测试。保留了 B.1 的 V1/V2、单位、源项、原生归档重放、执行门和状态治理回归。检查期间 Ruff 曾指出分子记录函数复杂度超限，已在同一覆盖率模块内拆分足迹核对与单库存贡献计算，最终检查通过。

## 重放与完整性

- 两树分别通过现有 `scripts.baseline_mkm.analysis coverage` 入口生成各自的 Ni/Cu 与氧化物 JSON，输出互相逐字节一致，并通过覆盖率 schema。Ni/Cu 结果 SHA-256 为 `d50ff225f6f9c52361fca13920137720e4e5569bece453d7cd26fd6f4e8cbfe1`，氧化物为 `ab1c981802a6e01423c69656b1e6e2fef8e97b3bcb6d4ac3e673fe5181ed80ce`。自动化测试从两个原始网络来源重新得到报告对象，并核对与交付值相同。
- 源项兼容性对照使用原 B.1 数学实现。此前的 10 份 V2 归档及资格报告仍通过 B.1 字节复现测试。Phase 3.1.1 不带计数参照的覆盖率命令继续重现原验证 JSON 的字节。
- 两树各 **71/71** 个选定历史文件的原始字节与发布基线中的 Git blob 完全一致。范围包括 Phase 2.5.1、2.5.2、3.0、3.1.1 的归档，Phase 3.1 位点对定义，B.1.4 与 B.1.5 报告，原始氧化物 fixture 及四个 V1/V2 契约 schema。生产 SQLite 和原始计算文件均未写入。

## 复现命令

在仓库根目录使用下列命令执行相同专项。两种引擎仅使用既有归档。

```powershell
C:/Anaconda/python.exe -m pytest tests/test_native_rate_adapters.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_kinetic_parameters.py tests/test_mkm_analysis.py tests/test_mkm_single_point.py tests/test_catkinas_closed_cycle.py tests/test_native_model.py tests/test_native_advanced.py tests/test_mkm_drc.py::test_offline_raw_native_replay tests/test_mkm_drc.py::test_published_contract_and_independent_drc tests/test_mkm_drc_cross_reaction.py::test_published_cross_type_result_and_step_stability tests/test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic tests/test_b7_release.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_state_manager.py tests/test_b4_state_governance.py tests/test_execution_gate_compatibility.py tests/test_neb_execution_gate.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_reaction_site_review.py tests/test_reaction_network.py -k 'not test_live_closed_cycle and not test_native_zacros_replay' --tb=short -r f
```

要独立重放计数结果，Ni/Cu 使用 Phase 3.1.1 的归档网络。氧化物使用现有网络生成命令从 fixture 生成版本 `a35beac998f393b7ad16e954e74f5982523436605fdcad54934de042ce8e9bfa`。将以下示例中的 `OUT` 替换为新的临时输出目录。

```powershell
python -m scripts.baseline_mkm.analysis coverage reports/multiphase/phase3_1_1/network.json reports/multiphase/stage_b2_1/interface_observations.json OUT/interface.json
python -m scripts.reaction_network tests/fixtures/multiphase/synthetic_oxide_site_network.json --output-dir OUT
python -m scripts.baseline_mkm.analysis coverage OUT/network-a35beac998f393b7ad16e954e74f5982523436605fdcad54934de042ce8e9bfa.json reports/multiphase/stage_b2_1/oxide_observations.json OUT/oxide.json
```
