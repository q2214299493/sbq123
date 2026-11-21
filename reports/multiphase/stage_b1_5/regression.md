# Windows 离线回归与重放回执

| 最终验证范围 | 开发工作树 | 独立发布工作树 |
| --- | ---: | ---: |
| B.1.4 既有范围，含两种适配器、历史 MKM/KMC 离线测试 | 502 通过 | 502 通过 |
| State Manager、B4 状态治理、执行门兼容性及 NEB 执行门 | 73 通过 | 73 通过 |
| B.1.5 新增的归档数值复核 | 11 通过 | 11 通过 |
| B.1.5 新增的契约、计量、部分观测与跨引擎身份检查 | 10 通过 | 10 通过 |
| **最终专项运行** | **596 通过，0 失败，0 错误** | **596 通过，0 失败，0 错误** |
| JUnit 测试用时 | 41.815 s | 41.388 s |
| py_compile 与 Ruff，两份新增 Python 文件 | 通过 | 通过 |
| 复算报告，两次独立 Python 进程 | 字节一致 | 字节一致 |

两套工作树使用 Windows、Anaconda Python 3.13.9 独立执行。开发树为 `refactor/v2-architecture-repair@233d5a6c589560094a0e942b6d48708b1fd5a847`，含开发者已有修改。发布树从 `codex/multiphase-phase0-integration@a301ff159a47f8b55451cc2c5be7b94a18abc823` 开始。两套树的状态和执行门测试也分别单独通过 73 项。合计数按最终运行去重。

## 范围和排除项

既有 502 项覆盖 V1 bundle、V2 输出、量纲、计量、参数集、MKM 分析和单点结果、CATKINAS 闭环、Zacros 原生输入与高级离线样例、归档 DRC、维护范围导入图及发布检查。下列命令在两套树分别执行，JUnit 输出写入各自的临时路径。筛除了 1 项 live CATKINAS 和 8 项 native Zacros。全仓其他测试未运行。原生引擎和 VASP 系列计算的现场执行能力不属于本次验证。

```powershell
C:/Anaconda/python.exe -m pytest tests/test_native_rate_adapters.py tests/test_stoichiometric_sources.py tests/test_multiphase_contracts.py tests/test_rate_output_v2.py tests/test_rate_dimensions.py tests/test_kinetic_parameters.py tests/test_mkm_analysis.py tests/test_mkm_single_point.py tests/test_catkinas_closed_cycle.py tests/test_native_model.py tests/test_native_advanced.py tests/test_mkm_drc.py::test_offline_raw_native_replay tests/test_mkm_drc.py::test_published_contract_and_independent_drc tests/test_mkm_drc_cross_reaction.py::test_published_cross_type_result_and_step_stability tests/test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic tests/test_b7_release.py tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py tests/test_state_manager.py tests/test_b4_state_governance.py tests/test_execution_gate_compatibility.py tests/test_neb_execution_gate.py -k 'not test_live_closed_cycle and not test_native_zacros_replay' --tb=short -r f
C:/Anaconda/python.exe -m py_compile tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py
C:/Anaconda/python.exe -m ruff check tests/test_b1_native_acceptance.py tests/test_b1_contract_acceptance.py
```

## 十份输出和来源复现

在每套工作树中分别以 `PYTHONHASHSEED=23` 和 `79` 启动新的 Python 进程。每次从两份 MAT 和八份 Zacros ZIP 及其原始回执、网络和参数数据重建，逐个比较 10 份序列化 V2、两份整组 qualification、逐案例摘要、输出身份、父 run、输入摘要及归一化声明。检查每个 V2 解码后的网络校验及 `unreviewed` 状态。两份整组 qualification 的 SHA-256 为 CATKINAS `9b8bb716277180587c32eb5cd0f4b90c3dfc32ce638a458d4a1717db18bac65d`、Zacros `fa1577a131e850937cf5822cf8c2fc3f40bd5909c21ddb317cf990b4b20c70f5`。四个进程各自得到的独立回执 SHA-256 均为 `5eeb6ddcdcfdc7c0f87ff22c66916728122ad4427b0774c04be640d04ca4d5bb`。[各父记录、输入输出和资格摘要](independent_replay.json)

在仓库根目录运行以下 Python 可在内存中复算并验证回执。对历史文件仅执行读取。

```python
import sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('tests').resolve()))
from test_b1_native_acceptance import catkinas_oracle,zacros_oracle,NATIVE_CASES
from test_b1_contract_acceptance import replay_all,encoded
observation=dict(catkinas={k:catkinas_oracle(k) for k in ('phase2_5_2','phase3_0')},zacros={k:zacros_oracle(k) for k in NATIVE_CASES},replay=replay_all())
raw=encoded(observation)
assert raw == Path('reports/multiphase/stage_b1_5/independent_replay.json').read_bytes()
print(hashlib.sha256(raw).hexdigest())
```

## 历史文件字节核查

以发布基线 Git 树的 blob 摘要分别核验两份 Windows 工作目录。抽取 Phase 2.5.1、2.5.2、3.0 的报告与原始归档，Phase 3.1 的归一化证据，B.1.1 至 B.1.4 的报告、原始重放快照，以及选定的 V1/V2 schema 和契约 fixture。两个工作目录均有 **73/73** 个选定文件的原始字节与基线完全相同，无换行归一化。独立数值测试另核对归档内部各受绑定输出成员，来源检查覆盖重放使用的每个原生输入。生产 SQLite、生产适配器、科学数据、历史回执及批准记录均未写入。
