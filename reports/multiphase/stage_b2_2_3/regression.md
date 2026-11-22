# Windows 双树专项验收

独立发布树与远端任务分支的起点均为 `2058f84e6c0d746f02f1d7c2ef32e73a95514a14`。开发树保留在 `refactor/v2-architecture-repair@233d5a6c589560094a0e942b6d48708b1fd5a847`。修改前，两树的十份关联实现、契约、文档及上轮回执逐字节相同。开发树的其他修改保留在原处。

| 实际检查 | 开发树 | 独立发布树 |
| --- | ---: | ---: |
| 修改前的反应网络、交换契约、目录身份和转移回归 | 186 通过 | 186 通过 |
| 最终专项中的 B.1 至 B.2.2.2 既有范围 | 779 通过 | 779 通过 |
| 本轮跨相基元反应测试 | 36 通过 | 36 通过 |
| 最终专项合计 | **815 通过，0 失败，66.10 秒** | **815 通过，0 失败，65.72 秒** |
| 六个修改或新增 Python 文件的编译、Ruff、公共入口导入及反应 JSON Schema 自检 | 通过 | 通过 |
| 归档文件与发布基线 Git blob 的原始字节比较 | 28/28 一致 | 28/28 一致 |

首次静态检查发现组网函数的复杂度超过既有 Ruff 上限。将新增分类的字段检查和资格输出放到所属网络模块后，原检查规则通过。最终运行覆盖成功路径、非法输入、错误接触、遗漏相、未知足迹、逐库存冲突、由另一侧已知化学证据揭示的 TS 矛盾、独立拒绝决定、顺序和 ID 置换，以及两种引擎各自的资格边界。

两树分别运行既有网络 CLI，重建两个新样例和封存的 B.2.2.2 转移样例。旧样例的网络版本为 `e50f1520e3d792d106ad98d232d141e6466ce1c754dbd59cea35a8290a69394c`，输出文件 SHA-256 为 `ae00afb986f289731019e5e871feed81a1536640acd57594d74b8b6e693e9865`，两者均与旧回执一致。B.1 V2.1、原 Fe(110) 和 Ni/Cu 网络、氧化物 fixture 及 B.2.1 覆盖率记录均纳入历史文件核对。两树验证回执逐字节一致，SHA-256 为 `74ad49c72408f5a8113aab67f8076053c271e9330abf99eb8964675ea9e682c0`。[各文件及新样例哈希](validation.json)

每树均排除 1 项 live CATKINAS 和 8 项 native Zacros。本轮仅执行离线软件回归和归档重放；其余全仓测试未执行。未调用原生科学引擎或写入生产 SQLite。

在任一工作树根目录复跑最终专项：

```powershell
C:/Anaconda/python.exe -m pytest tests/test_native_rate_adapters.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_kinetic_parameters.py tests/test_mkm_analysis.py tests/test_mkm_single_point.py tests/test_catkinas_closed_cycle.py tests/test_native_model.py tests/test_native_advanced.py tests/test_mkm_drc.py::test_offline_raw_native_replay tests/test_mkm_drc.py::test_published_contract_and_independent_drc tests/test_mkm_drc_cross_reaction.py::test_published_cross_type_result_and_step_stability tests/test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic tests/test_b7_release.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_state_manager.py tests/test_b4_state_governance.py tests/test_execution_gate_compatibility.py tests/test_neb_execution_gate.py tests/test_inventory_accounting.py tests/test_multidentate_coverage.py tests/test_reaction_site_review.py tests/test_reaction_network.py tests/test_multiphase_identity.py tests/test_interphase_transfer.py tests/test_cross_phase_elementary.py -k 'not test_live_closed_cycle and not test_native_zacros_replay' --tb=short -r f
```
