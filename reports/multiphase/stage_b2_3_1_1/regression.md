# 双工作树离线回归

发布树和远端起点为 `codex/multiphase-phase0-integration@03b47b74a7f1c44d96d228387e6d24a9ddd3e4be`。开发目录保留在 `refactor/v2-architecture-repair@233d5a6c589560094a0e942b6d48708b1fd5a847`。逐树对照基线 Git 对象，45 个历史证据、契约和相关实现的文件字节均一致。两树独立生成的证据索引 SHA-256 均为 `b99ed592fda5aafe1d6ff86b2cacb7b10bc5f798b4ab674383b67637da2f043f`。[完整路径与 SHA-256](evidence.json)

| 最终检查 | Windows 开发目录 | Windows 独立发布树 |
| --- | ---: | ---: |
| B.2.3.1 离线范围 896 项，加本轮 8 项 | **904 通过**，9 项排除，65.74 秒 | **904 通过**，9 项排除，63.70 秒 |
| 新测试文件 py_compile 和 Ruff | 通过 | 通过 |
| 同一氧化物 fixture 经公开观测入口重建 B.2.1 完整占位报告 | 匹配 | 匹配 |
| Ni/Cu 已验收的两份原生运行与 B.1 V2 回执 | 离线重放匹配 | 离线重放匹配 |

8 项新测试核对有限单元中每套库存的分母、四个带符号的净事件计数、未知速率与平衡零残差的区别、厂商语法样稿中分子和库存的对应关系，以及输入生成和审批的阻断状态。原有 B.1 速率、单位和化学计量源项，B.2.1 分子计数，B.2.2 相身份和转移，Ni/Cu 原生适配器、兼容入口、数据回读与 Fe(110) 阻断测试一并通过。

首次复跑两树各有 902 通过、1 失败、9 排除。新测试将低层 coverage_analysis 输出与含来源、状态和哈希的完整归档报告相比较；改从公开 analyze_observations 入口重放后，完整结构相符。未修改归档或放宽断言。最终运行包括查阅手册 §4.3 后增加的样稿测试。9 项排除是 1 个 live CATKINAS 和 8 个 native Zacros 测试。全仓其余测试未执行。

```powershell
C:/Anaconda/python.exe -m pytest tests/test_native_rate_adapters.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_kinetic_parameters.py tests/test_mkm_analysis.py tests/test_mkm_single_point.py tests/test_catkinas_closed_cycle.py tests/test_native_model.py tests/test_native_advanced.py tests/test_mkm_drc.py::test_offline_raw_native_replay tests/test_mkm_drc.py::test_published_contract_and_independent_drc tests/test_mkm_drc_cross_reaction.py::test_published_cross_type_result_and_step_stability tests/test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic tests/test_b7_release.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_state_manager.py tests/test_b4_state_governance.py tests/test_execution_gate_compatibility.py tests/test_neb_execution_gate.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_reaction_site_review.py tests/test_reaction_network.py tests/test_multiphase_identity.py tests/test_interphase_transfer.py tests/test_cross_phase_elementary.py tests/test_catkinas_network_mapping.py tests/test_mkm_sensitivity.py tests/test_mkm_composition_order.py tests/test_catkinas_oxide_multidentate_audit.py -k 'not test_live_closed_cycle and not test_native_zacros_replay' --tb=short -r f
```
