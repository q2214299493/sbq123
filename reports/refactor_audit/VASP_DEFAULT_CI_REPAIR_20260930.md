---
document_class: CURRENT_REFERENCE
as_of: '2026-09-30T23:07:31+08:00'
source_scope: Local Windows CI repair; software tests only
source_branch: codex/vasp-default-sbq123-20260930
source_version: aa4ab3029c8e9019facb4b60c6125899d26abcd8
source_version_role: Clean starting HEAD, not a reset target
evidence_kind: SOFTWARE_TEST_RECORD
---

# VASP-default CI 定点修复记录

实际工作树：`C:/Users/86177/.codex/worktrees/is-a-int06-resource-72r/work`。
启动时分支与 HEAD 如上，工作区干净；实际导入的 submission.py 位于本工作树。
主开发工作树与诊断工作树未修改，Phase 2A 目录未修改。

## 原因与修改

- `tests/test_execution_lifecycle.py`：替身、禁止网络的断言替身、包装器、
  RemoteSandbox.run 和硬退出子进程明确接受 `stdin=None`。包装器与沙箱透传句柄，
  沙箱仅执行临时 HOME 中的本地 Bash；移除旧 SCP 仿真分支。
- 轻量提交替身与子进程实际读取生成的 tar，核对完整清单及每个文件的字节哈希；
  该观察器只用于终止调用的替身，不消耗转发到 Bash 的文件流。
- 旧 SCP 篡改事件改为成功 tar 解包之后修改本地绑定的 analysis.json。
  断言注入恰好一次、解包文件匹配、门控抛出预期的证据/授权字段失效 ValueError、
  bsub 调用为零、UNKNOWN reservation 保留且后续重试无新远程调用。
- 新增三个测试实例：CRLF/非 UTF-8/NUL 字节和编号子目录保真、清单外文件排除；
  传输失败及真实 Bash/tar 解包失败均不得进入 fake bsub，重试保留原 reservation。
  原有新上传/复用目录、POTCAR 身份、额外文件及符号链接检查保留。
- `tests/test_alpha_fe_bulk_submission.py`：明确 stdin 签名，复用 tar 验证；
  receipt_loss、timeout、missing_job_id、rejection 分别匹配其原定阶段的异常及消息。
  并发单次 dispatch、回执丢失、硬退出码 91、UNKNOWN 和重复提交保护均保留。
- `reports/capability_readiness.json`：现有生成器更新来源哈希。
  更新前逐字段比较确认唯一差异为 `source_sha256["tests/test_ts_strategy_engine.py"]`。
  两次生成逐字节一致；所有模块/科学/生产成熟度字段不变，Markdown 字节不变。
  未手填哈希，未修改生成器或字节一致性断言。

未修改生产代码、账号配置、科学阈值、输入、生产数据库或执行授权。
未新增 skip/xfail，未放宽安全断言或将错误视为成功。

## 实际验证

环境：Windows，`C:/Anaconda/python.exe`，Python 3.13.9；Git Bash 本地沙箱。
已有 pytest 8.4.2、Ruff 0.12.0、pymatgen 2026.5.4、ASE 3.29.0、Sella 2.6.0。
未安装或升级依赖。环境详情见[环境记录](vasp_default_ci_repair_20260930/environment.json)。

| 检查 | 真实结果 | 退出码 |
|---|---|---|
| A0：原三个测试文件 | 17 failed, 95 passed | 1 |
| R1：生命周期和 alpha 测试 | 89 passed | 0 |
| A1：最终相关五个测试文件 | 158 passed | 0 |
| A2：当前 workflow engineering 子集，最终版 | 269 passed | 0 |
| 修改文件 py_compile、导入、Ruff | 通过 | 0 |
| 原生成器两次执行及逐字节比较 | 一致；Markdown 和模块字段不变 | 0 |
| git diff --check | 通过 | 0 |
| 全量 collect-only | 1372 tests collected；未执行测试 | 0 |
| 用户限定授权后，Windows 完整 pytest | 1372 passed；0 failures/errors/skipped，421.05 秒 | 0 |

测试命令、退出码与每个基线失败的实际异常/触发阶段分别见
[命令记录](vasp_default_ci_repair_20260930/commands.txt)、
[17 个失败节点](vasp_default_ci_repair_20260930/baseline_failures.json)。
基线的 17 个失败与附件记录的远端失败类别吻合；95 passed 是本地三个文件的结果，
不能与旧 Linux 全量 CI 的 1352 passed 混为一谈。
原始日志：[A0](vasp_default_ci_repair_20260930/A0_baseline.txt)、
[A1 最终版](vasp_default_ci_repair_20260930/A1_final.txt)、
[A2 最终版](vasp_default_ci_repair_20260930/A2_final_engineering.txt)。

## 冲突操作与未验证项

- 只读 `python -B -m scripts.state_manager.cli audit --phase start` 退出 1：
  已有事件链缺少被 supersede 的事件，三个管理投影视图漂移；另有 16 项工作树归属警告。
  详见审计记录（本地文件 `archive/vasp_default_ci_repair_20260930/start_audit.log`）。未扩展修复。
- 初次检查发现全量 pytest 中的实际 Sella 调用与附件禁令冲突，曾停止全量执行。
  用户随后限定授权本地解析势单元测试；经下面的执行前检查后已运行并通过全量。
  未用 skip/xfail 或过滤命令伪装全量通过。
  全量 collect-only 仅验证测试收集，结果另存收集日志（本地文件 `archive/vasp_default_ci_repair_20260930/full_collection_only.log`）。
- Linux、Python 3.11、新 GitHub CI 及生产远程传输未验证。
  本地测试不证明实际 VASP 作业或科学接受结果。
- 项目默认状态同步/发布规则与本次用户指令冲突；未运行 repo-state sync/apply、
  真实 SSH/SCP/调度操作、生产 SQLite、计算、commit、push 或 merge。

## 继续收口审查

- 对 HEAD 与当前两个测试文件做 AST 比较：原有 29 个测试函数、61 条 assert
  及全部原有参数化装饰器均保留；派生 JSON 与当前 build_readiness 输出仍一致。
  检查退出 0，详见[静态审查记录](vasp_default_ci_repair_20260930/continuation_static_review.json)。
- 检查已有本地环境：WSL 枚举退出 1，未获得可用 Linux 环境；Python launcher
  列出 3.14/3.13，没有 3.11。两个已登记 Conda 环境为 3.12.13，缺少 pytest、Ruff、
  jsonschema；桌面内置 Python 为 3.12.14，也缺少项目测试依赖。
  未安装组件或改动环境。WSL 错误文本存在编码乱码，仅以枚举退出码确认不可用，
  不据此推断具体安装状态。详见[环境检查](vasp_default_ci_repair_20260930/continuation_environment.json)
  和[环境补充](vasp_default_ci_repair_20260930/continuation_environment_addendum.json)。
- 本轮没有新增代码修改或重复运行已通过的回归；此前真实结果仍为相关回归
  158 passed、engineering 269 passed，均退出 0。

## 用户限定授权后的 Sella 执行前检查

用户随后明确允许：先检查 Sella 测试及 fixture，确认合成结构、解析势、本地 CPU、
临时目录隔离且不使用真实反应体系、生产目录/数据库、模型权重或真实 VASP 计算器后，
可以执行完整 pytest。其余真实计算、远程、训练、同步和发布禁令继续有效。

已审查六个含 Sella 引用的测试文件及相关 fixture/调用实现。
实际 Sella 优化的五个节点为：

- `tests/test_ml_sella_candidate.py::test_real_sella_finds_analytic_saddle_preserves_fixed_cell_and_restart`
- `tests/test_ml_sella_candidate.py::test_real_sella_records_geometry_failure_and_last_valid_iterate`
- `tests/test_matris_sella_local_peak.py::test_real_sella_starts_from_unconverged_multi_peak_path_and_joins_labels`
- `tests/test_matris_sella_local_peak.py::test_budget_or_geometry_stop_preserves_last_valid_seed[1-0.15]`
- `tests/test_matris_sella_local_peak.py::test_budget_or_geometry_stop_preserves_last_valid_seed[200-0.001]`

上述测试使用 `_seed()` 或 `_fixture(tmp_path)` 生成的小型合成结构，计算器为
SaddleCalculator、MultiPeakCalculator 或其 BudgetCalculator 包装，均为本地解析势。
结构、请求、轨迹、日志和结果限于 tmp_path；checkpoint 是占位测试字节，
calculator_loader 明确替换为解析计算器，不加载模型权重。部分结构含 Fe/C/O/H
元素标签，但不是来自真实反应体系或生产计算目录。

其余引用文件为 `tests/test_matris_sella_smoke.py`、
`tests/test_aqcat25_ts_active_learning.py`、`tests/test_ts_strategy_learning.py`、
`tests/test_repository_contracts.py`：分别检查本地 EMT 力预算/合成请求、临时交接数据、
临时 SQLite 学习记录及静态配置契约，不运行生产 Sella、训练、GPU、SSH 或 VASP。
`test_partial_selective_dynamics_rejected_without_discarding_mask` 在构建优化器前拒绝无效约束。
完整引用清单见[Sella 测试清单](vasp_default_ci_repair_20260930/sella_test_inventory.txt)。

执行环境固定 `JAX_PLATFORMS=cpu`、`CUDA_VISIBLE_DEVICES=`、`PYTHONUTF8=1`；
执行前 `jax.devices()` 返回仅 `cpu:0`，断言通过，退出 0。

完整执行命令（以上三个环境变量保持生效）：

```text
python -B -m pytest -o addopts= -q --junitxml=archive/vasp_default_ci_repair_20260930/A3_full.xml
```

实际退出码 0，`1372 passed in 421.05s (0:07:01)`。JUnit 独立核对为
1372 tests、0 failures、0 errors、0 skipped；上列五个 Sella 优化节点均有通过记录，
并非收集成功或因缺依赖跳过。未新增 skip/xfail、删除断言或扩大权限。
详见[完整 pytest 日志](vasp_default_ci_repair_20260930/A3_full_pytest.txt)、
JUnit（本地文件 `archive/vasp_default_ci_repair_20260930/A3_full.xml`）、
[节点结果摘要](vasp_default_ci_repair_20260930/A3_full_summary.json)。

这次完整回归只证明 Windows/Python 3.13.9 的软件测试通过，不证明真实 TS、
科学接受、生产部署或真实远程传输。没有运行真实 SSH/SCP、集群/调度操作、
VASP/GPU/Sella 科学计算、模型训练、生产数据库或 repo-state sync；没有 commit/push/merge。
Linux/Python 3.11 验证缺口及既有状态审计问题仍保留。

下一步：审查本地 diff 与本记录，再由用户决定后续 CI 或提交操作。

## 发布准备

用户于 2026-10-01 明确要求推送。本分支提交携带上述源码修复、派生 JSON、
本修复记录及必要测试证据副本；原始 JUnit、完整收集清单和工作树审计日志保留在本地。
发布前从未改变的 A0 日志重新提取全部 17 个失败节点的异常，修正先前摘要因
错误识别 traceback 分隔线而产生的空字段；原始日志和测试结果不变。
发布用 A0 文本副本仅清理 pytest 输出的行尾空白；完整原始日志仍保留在本地 archive。
