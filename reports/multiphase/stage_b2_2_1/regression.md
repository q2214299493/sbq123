# Stage B.2.2.1 · Windows 回归与来源核验

发布树和远端的起点为 `7b8a827d223c2d0dc521a45fb37c98e2e562e684`。开发树保留其独立分支 `refactor/v2-architecture-repair@233d5a6c589560094a0e942b6d48708b1fd5a847` 以及已有修改。修改前，核查的 14 个所属实现、契约与文档文件在两树均与发布基线字节一致。

| 验证项 | Windows 开发树 | Windows 独立发布树 |
| --- | ---: | ---: |
| 修改前四组测试，覆盖 Phase 1 契约、网络、位点审阅及 B.2.1 计数 | 161 通过 | 161 通过 |
| 最终专项中，B.2.1 的既有范围（含 B.1） | 711 通过 | 711 通过 |
| 本轮结构身份测试 | 38 通过 | 38 通过 |
| **最终专项总计** | **749 通过，0 失败，52.41 s** | **749 通过，0 失败，51.91 s** |
| 8 个变更 Python 文件的 py_compile、Ruff 及公共入口导入 | 通过 | 通过 |

每树均排除 1 项 live CATKINAS、8 项 native Zacros。全仓其他测试未运行。检查只读取归档、临时测试数据和版本契约，未运行科学计算或写生产 SQLite。

专项涵盖双向版本隔离、封存的十份 B.1 V2 输出及资格重放、源项及原生分母、B.2.1 两份库存结果、缺失和共享容量处理、原 Fe 网络与 Ni/Cu 网络、网络结构及状态和执行门。新用例包含同一相对的不同界面、部分参与面、单侧吸附、非晶面描述、无效结构来源、错误位点所有者、同名库存、顺序及标签置换、旧快照版本核验与只写一次的只读报告。

两树通过同一 CLI 分别生成四个案例的归属报告，逐个核对原输入 SHA-256，再合并为机器回执。两树回执字节一致，SHA-256 为 `b70350daaedea66a67b2b96cf4535f86aef6cea1ae3199e7cc8eebe215477f1e`。每树另与发布基线的 Git blob 比较 **46/46** 个历史文件，覆盖 B.1.4、B.1.5、B.2.1、Phase 3.1.1 归档、指定 Fe 快照与位点报告、六个交换和速率契约、历史 Ni/Cu 与氧化物 fixture。[机器回执](identity_validation.json)

复跑本次离线专项可在任一工作树根目录执行以下命令。

```powershell
C:/Anaconda/python.exe -m pytest tests/test_native_rate_adapters.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_kinetic_parameters.py tests/test_mkm_analysis.py tests/test_mkm_single_point.py tests/test_catkinas_closed_cycle.py tests/test_native_model.py tests/test_native_advanced.py tests/test_mkm_drc.py::test_offline_raw_native_replay tests/test_mkm_drc.py::test_published_contract_and_independent_drc tests/test_mkm_drc_cross_reaction.py::test_published_cross_type_result_and_step_stability tests/test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic tests/test_b7_release.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_state_manager.py tests/test_b4_state_governance.py tests/test_execution_gate_compatibility.py tests/test_neb_execution_gate.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_reaction_site_review.py tests/test_reaction_network.py tests/test_multiphase_identity.py -k 'not test_live_closed_cycle and not test_native_zacros_replay' --tb=short -r f
```
