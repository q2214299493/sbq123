# Stage A.2.3 · DRC 扰动对与报告依赖拆分

基线：`046dd867f6e75a021263f9fa32f4bbd49ae81935`，即用户已发布的 A.2.2。本次只处理 P3 的第一组 `drc_pair` / `drc_report` 循环。

**状态：目标代码拆分已实现；没有新增回归失败，但当前 Linux 环境的全绿验收尚未达到。** 修改前已有一项批次数据身份重建失败，修改后保留同一用例、同一断言差异。本报告生成时尚未发布 GitHub，也未同步或验证 Windows 开发目录。

## 具体实现

| 文件 | 修改与效果 |
|---|---|
| `scripts/baseline_mkm/drc_pair_records.py` | 原样承接 7 个共享记录函数和 4 个常量：接受回执核验、基准绑定、确定性输入重建、成员校验、完成回执核验及不可变 JSON 写入。 |
| `scripts/baseline_mkm/drc_pair.py` | 保留旧函数及常量导入入口；准备、计时、执行、失败记录和 CLI 留在原编排模块。 |
| `scripts/baseline_mkm/drc_report.py` | 仅将共享记录函数的导入改为下层记录模块，消除对执行编排模块的反向依赖。 |
| `tests/test_mkm_drc.py` | 新增旧入口身份及 JSON 幂等写入回归；已有基准故障注入改到新函数归属，原断言不变。 |
| `tests/test_b5_architecture_boundaries.py` | 新增报告与记录模块不直接或间接依赖 `drc_pair` 的约束。 |

运行时代码共涉及 3 个文件，净增加 21 行。7 个迁移函数、7 个保留的编排函数以及 8 个报告函数，共 **22 个原有函数的 AST 与基线全部一致**。

新模块具有明确的记录写入职责：`put` 仍允许已存在且 JSON 值相同的文件，保留原文件字节；冲突仍拒绝，新文件继续调用已有独占写入函数。因此不能把整个记录模块称为纯函数模块，也不能用只支持首次写入的接口替换 `put`。

旧公开导入继续可用。函数迁移后，内部全局依赖以新归属为准；`test_baseline_must_match_accepted_receipt` 的注入点从 `pair.accepted` 改为 `records.accepted`，仍检验同样的成功路径和批准身份冲突。这里不承诺任意旧模块全局 monkeypatch 都保持原作用。

## 专项验证

环境：Python 3.12.14、Linux / glibc 2.41、pytest 8.4.2、Ruff 0.17.6。只使用离线解析、封存结果和模拟执行；本组测试没有需要排除的原生运行用例。

| 范围 | 修改前 | 修改后 |
|---|---:|---:|
| `test_mkm_drc.py` | 44 通过 | 46 通过 |
| `test_mkm_drc_batch.py` | 25 通过，1 失败 | 25 通过，同一项失败 |
| `test_mkm_sensitivity.py` | 43 通过 | 43 通过 |
| `test_mkm_drc_cross_reaction.py` | 24 通过 | 24 通过 |
| 新增 DRC 依赖边界 | — | 1 通过 |
| **合计** | **136 通过，1 失败** | **139 通过，1 失败** |

失败节点和断言消息前后一致，没有修改 `test_mkm_drc_batch.py`，没有排除、标记预期失败或放宽这项测试。完整命令：

```bash
python -m pytest tests/test_mkm_drc.py tests/test_mkm_drc_batch.py \
  tests/test_mkm_sensitivity.py tests/test_mkm_drc_cross_reaction.py \
  tests/test_b5_architecture_boundaries.py::test_drc_report_records_do_not_depend_on_pair_orchestration
```

另完成：

- 21 个修改前后行为探针一致，覆盖基准身份字段故障注入、预算回执、拒绝状态及不可变 JSON 写入。
- 9 种 CLI 调用的退出码、标准输出及错误末行一致；覆盖帮助、缺参数及缺证据的报告请求。缺证据时没有创建报告目录。
- 4 份封存 DRC 报告由原 `result.json` 重渲染后与 `comparison.md` 逐字节一致，涵盖原步长、半步长以及第二反应的两种步长。
- 原有离线原生结果重放、压力阶数、批准门、预算、首错停止、部分恢复和零重试回归保留。封存报告重渲染不等于重新验证原始运行目录的全部实时绑定。
- 5 个改动的 Python 文件均通过 Ruff 和 `py_compile`，差异检查通过。独立代码审阅未发现本次新增阻断项。

## 保留的基线失败：浮点结果与精确身份

失败为 `tests/test_mkm_drc_batch.py::test_pilot_plan_is_reproducible_without_native_execution`。单独执行也复现，排除了其它测试污染。它早于本轮源码调整。

脱附反应 `desorb` 的负向 0.005 eV 扰动中，字段 `rates.forward.activity_coefficient_s^-1` 当前重算为 `802.2839447511138`，封存身份对应 `802.283944751114`。两者相差 1 ULP，即约 `1.14e-13`，精确数据哈希随之变化：

- 封存版本前缀：`ce3d2031cc1ebec3`。
- 当前版本前缀：`d37e15be163218ff`。

仅在内存副本中将这一字段提高 1 ULP，整个规范数据哈希和按原格式序列化的文件哈希同时恢复到封存值，支持差异仅来自这个字段的定位。该诊断副本没有作为科学数据保存或放行；真实测试仍失败。完整数值、完整哈希和环境见 `baseline_float_identity.json`。

具体上游原因仍需区分原数学库舍入和历史生成实现差异，本轮没有 Windows 对照，不能将原因直接定为 Windows 数学库。没有修改 `laws.py`、参数生成器、数值容差、身份规则、封存数据、运行 ID 或原批准。

此问题影响跨环境重新生成已批准数据的身份，是独立的数值可复现性待办。后续需要明确版本化的生成与身份约定，并保留旧批准绑定的原始输入。不能靠四舍五入、替换旧哈希或近似匹配给当前重算数据继承旧批准。

## 架构结果与边界

按现有 B5 静态导入图口径，模块 / 边数为 `288 / 1047 → 289 / 1052`；循环组数由 **3 降至 2**。原 `drc_pair` / `drc_report` 循环消失，报告与记录模块的传递依赖中也不含 `drc_pair`。剩余 DRC 批次和灵敏度两组的成员完全不变；没有修改既有全仓无环测试。

批准检查顺序、480 秒成对预算、单次上限、外部期限、首错停止、接受结果重用与零重试逻辑均未重写。没有运行原生科学计算、写生产 SQLite、修改科学协议或授予执行资格，也没有运行全仓测试。

开工 State Handoff 审计仍发现既有 `transition_state_search` 模块行投影漂移，并提示另一个本任务所有的隔离工作树需要识别归属。本次保留这些工作树和已有事件。历史记录及新发现待办通过 State Handoff 形成待审提案；收尾仅执行 `sync --safe-only`，不代选历史审批或修补旧来源哈希。

下一现场动作是在 Windows 开发树和独立发布树核对本补丁及基线失败，分别记录结果，再按已有发布授权处理任务分支。A.2.3 的 Linux 记录不能替代两树现场验收。随后逐组处理剩余 P3 循环；P4/P5 和后续统一供率、KMC 统计、SPC/H7 往返与理想反应器仍按各自职责推进。
