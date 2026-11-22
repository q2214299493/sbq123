# Windows 离线回归与历史重放

开发树为 `refactor/v2-architecture-repair@233d5a6c589560094a0e942b6d48708b1fd5a847`，保留现场开发修改。独立发布树和远端任务分支从 `910dcd2639c7b4974975b0d4b3a324ec7e473122` 开始。实施前核对了两树的关联输入与实现，然后分别验证。

| 实际检查 | 开发树 | 独立发布树 |
| --- | ---: | ---: |
| 修改前 native_model、closed_cycle 和 single_point 三组 | 76 通过，1 项 live CATKINAS 排除 | 76 通过，1 项排除 |
| 先前 B.2.2.3 离线范围单独复跑 | 815 通过，9 项排除 | 815 通过，9 项排除 |
| 最终专项，含上行、24 项本轮测试及 57 项灵敏度和组成反应级数回归 | **896 通过，9 项排除**，81.64 秒 | **896 通过，9 项排除**，81.45 秒 |
| 7 个修改或新增的 Python 文件 | py_compile、Ruff 通过 | py_compile、Ruff 通过 |
| 原生输入和两次离线发布的 manifest | 原生输入与历史字节相等；两次 manifest 字节相等 | 同一结果 |
| 两份独立 MAT、两份 V2 记录及资格回执 | 重放匹配 | 重放匹配 |
| 对照正式基线的 32 个原始文件 | 全部逐字节相同 | 全部逐字节相同 |

最终范围覆盖 B.1 契约、单位、化学计量源项、历史结果适配器、准入和发行检查，B.2.1 库存与占位，B.2.2 的相身份、转移和跨相反应，以及受影响的单点、审批和状态管理入口。9 个排除项为 1 个 live CATKINAS 测试及 8 个 native Zacros 测试。全仓其余测试未执行。编写新负例时，同组成异构物因缺少 configuration_id 被物种指纹检查提前拒绝；为该合成测试补上独立构型身份后，验证了整网连接判定。另一个负例维持六个物种和四条可匹配方程，只改一个反应的物种连接，整网仍被正确阻断。

仓库根目录的最终命令如下。

```powershell
C:/Anaconda/python.exe -m pytest tests/test_native_rate_adapters.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_kinetic_parameters.py tests/test_mkm_analysis.py tests/test_mkm_single_point.py tests/test_catkinas_closed_cycle.py tests/test_native_model.py tests/test_native_advanced.py tests/test_mkm_drc.py::test_offline_raw_native_replay tests/test_mkm_drc.py::test_published_contract_and_independent_drc tests/test_mkm_drc_cross_reaction.py::test_published_cross_type_result_and_step_stability tests/test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic tests/test_b7_release.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_state_manager.py tests/test_b4_state_governance.py tests/test_execution_gate_compatibility.py tests/test_neb_execution_gate.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_reaction_site_review.py tests/test_reaction_network.py tests/test_multiphase_identity.py tests/test_interphase_transfer.py tests/test_cross_phase_elementary.py tests/test_catkinas_network_mapping.py tests/test_mkm_sensitivity.py tests/test_mkm_composition_order.py -k 'not test_live_closed_cycle and not test_native_zacros_replay' --tb=short -r f
```

两树的映射清单 SHA-256 均为 `3fc09536fff44cdf8520a8930bfc846c56aba66ce374536421a791be76be1fb6`。两树独立生成的 validation.json 均为 `ea6467b98ce3f52d574a04c59553652f979d5f5d08d5a9c74e44e7a42c6725c4`。其中包含逐文件摘要、原生运行记录、通用到原生字段对应，以及受阻样例的逐项原因。[机器回执](validation.json)
