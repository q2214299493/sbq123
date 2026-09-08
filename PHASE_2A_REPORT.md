# Phase 2A Report

## 最终结论

**PASS WITH CONDITIONS**

正式源码候选基线已明确，23 个 E 类文件均有唯一归属，migration 已有独立
结论，2B 已选定一个不涉及数据库的单一主题。三个条件必须保留：

1. `AGENT_RULE_TS_ENDPOINT.md` 需要项目所有者确认正式治理文档地位；
2. 两个 endpoint migration 在 `MIGRATION_REVIEW.md` 的修订项关闭前不得
   执行；
3. `tests/test_repository_contracts.py` 的 2A artifact-directory 契约扩展
   需要人工接受并建立新审查基线；旧条件关闭哈希链不得静默覆盖。

不得直接进入涉及上述规则文档、migration 或数据库的重构。选定的 NEB
path-quality 2B 主题不涉及这些文件，但实施前仍应确认新的测试契约基线。

## 完成内容

已生成：

- `BASELINE_INTEGRITY_REPORT.md`
- `SOURCE_PROVENANCE_REPORT.md`
- `MIGRATION_REVIEW.md`
- `E_SOURCE_ARCHITECTURE.md`
- `SOURCE_BASELINE_PLAN.md`
- `PHASE_2B_PROPOSAL.md`
- `PHASE_2A_REPORT.md`
- `artifacts/source_baseline/formal_source_paths.txt`
- `artifacts/source_baseline/formal_test_paths.txt`
- `artifacts/source_baseline/formal_config_paths.txt`
- `artifacts/source_baseline/formal_migration_paths.txt`
- `artifacts/source_baseline/baseline_sha256.txt`

没有执行 `git add`、commit、push、clean、reset、checkout、stash、文件删除或
目录移动。

## 基线完整性

2A 入口时：

- 旧 A/B/C 哈希 33/33 一致；
- 旧隔离 patch 反向适用检查退出 0；
- 522 个未跟踪文件严格等于 513 个冻结文件加 9 个关闭产物；
- 没有新 unknown、计算产物或未记录源码变化。

本轮要求新增 `artifacts/source_baseline/`，与关闭阶段过窄的 root artifact
测试冲突。只修改了 `tests/test_repository_contracts.py`，使其精确允许第二个
目录和 5 个指定文件。生产源码没有修改。

因此最终旧 A/B/C 哈希链有一项已解释差异：

`tests/test_repository_contracts.py`

旧 patch 内容和哈希文件均未更新；其对当前测试文件的反向适用检查不再
成功。该差异已在 `BASELINE_INTEGRITY_REPORT.md` 记录。

## E 类归属

| 状态 | 数量 |
|---|---:|
| FORMAL_SOURCE | 10 |
| FORMAL_TEST | 6 |
| FORMAL_CONFIG | 3 |
| FORMAL_MIGRATION | 2 |
| DUPLICATE_CANDIDATE | 1 |
| HUMAN_REVIEW | 1 |

唯一重复候选：

`scripts/neb_agent/path_quality_cli.py`

唯一人工确认项：

`AGENT_RULE_TS_ENDPOINT.md`

没有 E 类文件被判为废弃、legacy、incomplete 或 generated/runtime。

## Migration

结论：**NEEDS_REVISION**

- SQL 与 Python model 字段、约束和索引基本一致；
- forward 对正确 Schema 重复执行幂等；
- rollback 与 Schema 对象对称但会删除全部 endpoint 业务数据；
- 同名不兼容表无法被当前检查发现；
- endpoint version 尚未纳入主 schema v5 migration 链；
- 当前唯一真实数据库不存在 endpoint table/version key；
- 数据库只读检查前后 SHA-256 保持
  `4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb`。

本轮未执行任何 SQL migration。

## E 类架构

- E 类内部无循环依赖；
- endpoint DB 访问集中在一个 adapter；
- execution gate 仍是唯一动作 authority；
- path-quality core 只有一个科学 evaluator；
- standalone path-quality CLI 与 unified workflow 存在 orchestration 重复；
- path-quality 测试覆盖 evaluator，但未覆盖两个入口等价性；
- pilot、active calibration 和 endpoint manager 仍混合部分规则与 I/O，
  本轮只记录，没有修改。

## 正式源码基线

机器清单绑定：

- 10 个 source；
- 6 个 test；
- 3 个 config；
- 2 个 migration；
- 4 个路径清单。

`baseline_sha256.txt` 共检查 25 项，失败 0。Migration 路径进入版本审查
候选清单不代表允许执行。

## 2B 选择

选择：**NEB 路径质量模块职责整理**

建议限制在 5 个主要源码文件和 2 个测试文件，保持：

- 判定状态、reason code、阈值和优先级不变；
- CLI 参数和模块路径不变；
- standalone CLI 保留为兼容薄层；
- execution gate 权威不变；
- 无数据库、scheduler、submission 或真实计算变更。

本轮没有实施 2B。

## 验证结果

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `python -m ruff check scripts modules tests` | 0 | All checks passed |
| `python -m pytest -q -ra` | 0 | 225/225 通过 |
| `git diff --check` | 0 | 无 whitespace error；仅既有 LF/CRLF 提示 |
| skip/xfail 源码扫描 | — | 0 项 |
| 新源码基线 SHA-256 | — | 25/25 一致 |

测试期间没有真实 SSH、LSF、`bsub`、`bkill`、VASP 或 NEB 调用。没有修改
数据库、计算输入、计算结果、任务状态或科学参数。

生成本报告前未跟踪文件为 533 项：522 项关闭基线加 11 项已记录 2A
输出。本报告本身是第 12 项，最终预期为 534 项；没有新增 unknown 文件或
计算产物。
