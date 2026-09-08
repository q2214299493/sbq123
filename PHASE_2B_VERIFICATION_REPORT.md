# Phase 2B 独立回归验收报告

## 最终结论：PASS

唯一科学 evaluator 成立，五入口科学行为等价，CLI、workflow 和 pilot 保持兼容；科学状态、reason code、阈值、Schema 和 execution gate 未改变；Phase 2A 的 24/25 差异完全由 Phase 2B 对 `pilot_validation.py` 的授权修改解释；Ruff、专项 59 项和完整 244 项测试、Git diff 检查全部通过。Phase 2B 可以结束。

## 1. 实际审查文件

生产源码：

- `scripts/neb_agent/path_quality_control.py`
- `scripts/neb_agent/path_quality_service.py`
- `scripts/neb_agent/path_quality_cli.py`
- `scripts/neb_agent/pilot_validation.py`
- `scripts/ts_strategy_engine/workflow.py`
- `scripts/ts_strategy_engine/execution_evidence.py`（consumer contract）
- `scripts/common/artifact_io.py`（写入实现）

测试：

- `tests/test_neb_path_quality_control.py`
- `tests/test_neb_path_quality_entrypoints.py`
- `tests/test_neb_pilot_validation.py`
- `tests/test_artifact_io.py`
- `tests/test_ts_strategy_engine.py`
- `tests/test_neb_execution_gate.py`

基线和实施材料：

- `PHASE_2B_IMPLEMENTATION_REPORT.md`
- `NEB_PATH_QUALITY_ARCHITECTURE.md`
- `PHASE_2B_BEHAVIOR_COMPATIBILITY.md`
- `PHASE_2B_CHANGESET_MANIFEST.md`
- `PHASE_2B_BEHAVIOR_BASELINE.md`
- `PHASE_2A_REPORT.md`
- `PHASE_2A1_CLOSURE_REPORT.md`
- `REVIEW_BASELINE_V2.md`
- Phase 2A source baseline 及旧哈希绑定文件

## 2. 唯一 evaluator

结论：成立。

- 仓库扫描只发现 `scripts.neb_agent.path_quality_control.evaluate_quality` 实现科学 path-quality 状态和 reason 分支。
- service 只调用该 evaluator 一次；CLI、workflow 和 pilot adapter 只调用 service。
- CLI 和 workflow 的科学判断分支数均为 0。
- pilot 不重新计算通用 path-quality 指标，也不把 path-quality 状态重解释为 pilot `passed`。
- 未发现别名副本、局部复制、动态导入、字符串模块路径或 subprocess 调用到第二个 evaluator。
- workflow 的缺 primary 三字段 `INVALID_ENDPOINTS` 是输入完整性短路，不是另一套路径质量科学评价。

职责边界如下：

| 职责 | 权威位置 |
|---|---|
| 输入采集 | `path_quality_control.collect_evidence` |
| 配置读取和验证 | `path_quality_service` |
| 数据标准化 | collector/service 的既有输入适配 |
| 科学评价 | 唯一 `path_quality_control.evaluate_quality` |
| 兼容报告构造 | `path_quality_service` |
| 文件写入 | CLI/workflow 调用 `artifact_io.write_json` |
| CLI 错误转换 | `path_quality_cli.main` 最外层 |
| pilot 独有验收 | `pilot_validation.build_pilot_result` / `validate_pilot_result` |

## 3. service 职责

结论：合理，未演变为 NEB 管理器。

公开接口：

- `PathQualityRequest`：冻结 dataclass，无运行副作用。
- `load_path_quality_thresholds(...) -> dict[str, Any]`
- `build_path_quality_report(...) -> dict[str, Any]`
- `read_configured_nelm(...) -> int`

service 仅执行文件/对象输入读取、配置验证、collector 调用、唯一 evaluator 调用和兼容报告构造。它不定义数值阈值，不产生或排序 reason code，不修改状态，不捕获异常后伪造结果，不依赖 argparse，不调用 `sys.exit`，不写 artifact，不接触 execution gate、scheduler 或 submission。

## 4. 五入口等价性

结论：通过。详见 `PHASE_2B_ENTRY_EQUIVALENCE_REPORT.md`。

- 五个可评价入口在正常、单一警告、电子失败、位移异常、多问题和真实临时文件样例上完整科学结果一致。
- endpoint 输入短路、非法配置、缺失文件、evaluator 异常和写入失败保持失败语义。
- 碰撞由 geometry diagnosis 所有，磁性连续性由 pilot 所有；两者没有被错误搬入 service。
- 无 `INCOMPATIBLE` 样例。

## 5. CLI 兼容性

结论：通过。

- 原模块路径和 `main() -> int` 保留。
- 原参数和默认输出名保留；`--help` 退出码 0。
- Schema、producer、成功退出码 0 保持。
- 配置、输入、evaluator 和写入错误不会生成成功 JSON，已覆盖错误退出码 1。
- argparse 自身的缺少必需参数/非法语法仍由 argparse 处理。
- CLI 不包含科学状态/reason 分支。
- 文档、测试和 consumer 扫描未发现失效旧路径。

## 6. workflow 兼容性

结论：通过。

- 执行顺序仍为诊断/分析/审查与 analysis 写入之后生成 path-quality，再加载 execution evidence 并决策。
- 输出文件名仍为 `neb_path_quality.json`。
- gate consumer 所需字段和 producer 字符串不变。
- 无输出返回 `{}`、缺 primary 返回旧 `INVALID_ENDPOINTS` 结构。
- 正常路径只调用 service/evaluator 一次，只写一份结果。
- 不在 service 结果外再次科学判定；异常不被吞没。
- `AnalyzeRequest` 和 workflow 公共返回结构不变。

## 7. pilot 兼容性

结论：通过。

- 当前相对修改前快照只增加 service 导入和显式 `build_pilot_path_quality_result`。
- `build_pilot_result`、`validate_pilot_result` 和 `main` 的签名及主体逻辑不变。
- 原 `passed` 规则、Schema-v2、磁性连续性规则和输出字段不变。
- adapter 不排序/过滤 reason，不重新解释 PASS/WARN/FAIL。
- 原模块路径和原函数仍可调用。
- 没有增加真实计算、SSH、LSF 或提交副作用。
- 新顶层导入增加 pilot→service→collector 的依赖边；当前项目环境导入及完整测试通过，记录为低残余风险。

## 8. 科学结果、API 和 Schema

- 科学阈值配置文件哈希未变。
- geometry/default threshold 配置哈希未变。
- evaluator 源码哈希未变。
- reason code 的定义、内容、顺序未变。
- 状态优先级和分支顺序未变。
- JSON Schema 与 evaluator 版本未变。
- execution gate、submission 和数据库文件哈希未变。
- 旧公共导入路径未删除；新 API 为加法变更。
- 唯一可观察非科学差异是非法配置更早、以明确 `ValueError` 失败；CLI 仍转换为失败退出，不存在约束放宽。

## 9. Phase 2A 24/25 哈希差异

结论：完全解释。

- Phase 2A source baseline 的 25 个条目中，当前仍为 24 个匹配、1 个不匹配。
- 唯一不匹配文件为 `scripts/neb_agent/pilot_validation.py`。
- 修改前哈希 `db0d00…2e90d`，当前哈希 `8c280c…969d`；Phase 2B changeset 已显式记录两者。
- Phase 2A baseline、Review Baseline v1/v2、changeset manifest 和数据库绑定文件本身哈希未变。
- 未发现第二个未解释源码哈希差异。
- Phase 2B changeset 未纳入计算目录或运行文件。
- `PHASE_2B_BEHAVIOR_BASELINE.md` 的修改时间早于 service 和入口测试生成时间，且其 golden/语义快照覆盖完整科学字段、reason 顺序、CLI/工作流/pilot 边界。
- `PHASE_2B_CHANGESET_MANIFEST.md` 保留实施完成时入口测试的 552 行/原哈希；本次验收新增的 48 行必要碰撞边界测试由追加式 `PHASE_2B_VERIFIED_CHANGESET.md` 绑定，没有回写旧 manifest。
- 本轮通过追加 `PHASE_2B_VERIFIED_CHANGESET.md` 建立新验收绑定；没有把旧 baseline 更新成 25/25。

## 10. 复杂度和重复

| 指标 | 修改前 | 当前 | 结论 |
|---|---:|---:|---|
| 科学 evaluator | 1 | 1 | 不变 |
| 配置合并实现 | 2 | 1 | 重复消除 |
| collect/evaluate 编排 | 2 | 1 | 重复消除 |
| 兼容报告构造 | 2 | 1 | 重复消除 |
| 原子 JSON 写入实现 | 1 | 1 | 继续复用 `artifact_io` |
| CLI 科学判断分支 | 0 | 0 | 无复制 |
| workflow 科学判断分支 | 0 | 0 | 无复制 |
| pilot 通用指标重复计算 | 0 | 0 | 无复制 |
| 最大函数长度 | evaluator 180 行 | evaluator 180 行 | 未增加 |
| 生产源码总行数 | 934 | 1043 | 净增 109 |

service 最大函数 51 行，workflow 最大函数 58 行，pilot 最大函数 51 行。新增 import 图为 control←service←{CLI, workflow, pilot}，静态图无环；未发现重复顶层定义。

## 11. 异常和写入边界

- evaluator 不捕获或改写异常。
- service 不吞异常，配置错误带明确上下文。
- CLI 只在最外层把预期用户错误转换成 stderr + 非零退出。
- workflow 和 pilot adapter 不把异常解释为通过。
- CLI/workflow 均调用 `artifact_io.write_json`；没有固定 `.tmp`。
- 写入失败测试断言不产生成功状态或部分结果。
- 目标代码无裸 `except`、无 broad exception 后继续、无失败后默认成功。
- 新测试只写 pytest 临时目录。

## 12. 实际验证

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/test_neb_path_quality_control.py tests/test_neb_path_quality_entrypoints.py tests/test_neb_pilot_validation.py tests/test_artifact_io.py tests/test_ts_strategy_engine.py tests/test_neb_execution_gate.py -q -ra` | 59 passed，exit 0 |
| `python -m scripts.neb_agent.path_quality_cli --help` | exit 0 |
| `python -m scripts.ts_strategy_engine.cli --help` | exit 0 |
| `python -m ruff check scripts modules tests` | All checks passed，exit 0 |
| `python -m pytest -q -ra` | 244 passed，exit 0 |
| `python -m pytest --collect-only -q` | 244 collected，exit 0 |
| `git diff --check` | exit 0；仅报告任务外既有文件的 LF→CRLF 提示 |

完整测试输出在 `-ra` 下没有 skip 或 xfail 条目。测试数量由实施完成时的 242 项增加为 244 项，没有减少。

## 13. 实际修复

未修改生产源码。独立验收发现“碰撞或原子过近”的职责边界虽实现正确，但缺少显式五入口回归证据，因此仅在 `tests/test_neb_path_quality_entrypoints.py` 增加两个测试实例：

- 用真实临时结构确认 geometry diagnosis 产生 `STOP` 和 `unphysical_contact_pair_0_1`；
- 确认相同碰撞上下文经过五个 path-quality 入口时结果一致，且 service/CLI/workflow/pilot 不复制 geometry 科学判定。

除上述必要回归测试外，本轮只新增四份验收交付文档。

## 14. 尚存风险

1. 部分 Phase 2B 前置文件在 Git 中未跟踪，旧基线只保存哈希、字节数和行数，没有保存完整 preimage；因此无法独立重算精确 gross additions/deletions。净行数、当前内容、行为和哈希链均已验证，不影响本轮行为结论。
2. pilot 的新增顶层 service import 扩大了模块导入依赖；项目当前依赖环境和 244 项测试均通过，但如果未来支持不安装 collector 科学依赖的极简 pilot 环境，需要另行定义其兼容目标。本轮不为假设场景修改生产逻辑。
3. `git diff --check` 显示任务外若干已有工作区文件存在未来 LF→CRLF 转换提示；它们未被本轮修改，也不在 Phase 2B changeset 中。

## 15. 是否允许进入下一主题

Phase 2B 验收条件已满足，可以结束 Phase 2B。任何下一优化主题必须由单独任务显式授权；本轮未开始 TS endpoint 模块整理。
