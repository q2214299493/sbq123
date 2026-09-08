# Baseline Integrity Report

## 结论

**PASS WITH CONDITIONS**

条件关闭后的 A/B/C 基线在 2A 开始时完整无损；为满足本轮明确要求的
`artifacts/source_baseline/` 交付路径，仓库结构契约测试随后进行了一个
有记录的窄范围扩展。旧条件关闭哈希链未被覆盖，因此当前会准确报告这一项
预期差异。

## 2A 入口快照

执行并交叉核对：

- `CHANGESET_MANIFEST.md`
- `REFACTOR_CHANGESET.md`
- `UNTRACKED_FILE_INVENTORY.md`
- `SUBMISSION_RECOVERY.md`
- `artifacts/refactor_changeset/tracked_changes.patch`
- `artifacts/refactor_changeset/untracked_source_manifest.txt`
- `artifacts/refactor_changeset/changeset_sha256.txt`

入口结果：

| 检查 | 结果 |
|---|---|
| `changeset_sha256.txt` 绑定对象 | 33 项 |
| SHA-256 不一致 | 0 |
| `tracked_changes.patch` 反向适用检查 | 退出码 0 |
| 冻结原始未跟踪文件 | 513 |
| 条件关闭后当前未跟踪文件 | 522 |
| 已记录关闭产物 | 9 |
| 未记录新增未跟踪文件 | 0 |
| 缺失的冻结文件 | 0 |
| 缺失的关闭产物 | 0 |
| 当前 tracked 修改 | 65 |
| 新计算产物 | 0 |

522 项集合严格等于 513 项冻结集合加以下 9 项关闭产物：

- `CHANGESET_MANIFEST.md`
- `CONDITION_CLOSURE_REPORT.md`
- `REFACTOR_CHANGESET.md`
- `SUBMISSION_RECOVERY.md`
- `UNTRACKED_FILE_INVENTORY.md`
- `artifacts/refactor_changeset/changeset_sha256.txt`
- `artifacts/refactor_changeset/tracked_changes.patch`
- `artifacts/refactor_changeset/untracked_source_manifest.txt`
- `tests/test_alpha_fe_bulk_submission.py`

因此，2A 开始前没有新增未知文件、计算产物或未记录源码变化。

## 2A 必需的结构契约扩展

本轮要求生成：

```text
artifacts/source_baseline/
    formal_source_paths.txt
    formal_test_paths.txt
    formal_config_paths.txt
    formal_migration_paths.txt
    baseline_sha256.txt
```

条件关闭阶段的 `tests/test_repository_contracts.py` 只允许
`artifacts/refactor_changeset/`。若不调整该测试，生成本轮规定目录后完整
pytest 必然产生一个结构契约失败。2A 因此只扩展该测试，使其精确允许上述
第二个目录和 5 个指定文件；没有放宽其他根目录、文件或扩展名。

这一测试属于旧 A/B/C 哈希链。扩展后：

- 旧哈希链仅 `tests/test_repository_contracts.py` 一项不一致；
- 旧 `tracked_changes.patch` 内容未改变，但对当前工作树的反向适用检查
  因同一测试的新增 2A hunk 退出 1；
- 旧 `CHANGESET_MANIFEST.md`、patch 和哈希文件均未被覆盖或“修复”；
- 差异来源明确，不是未知修改，也不包含生产逻辑。

## A/B/C 与 D/E/F 边界复核

- 旧隔离 patch 的文件集合没有加入 D/E/F 文件。
- 本轮源码基线目录只包含路径和 SHA-256，不复制任何 E/F 文件内容。
- 474 个冻结计算/运行/生成文件仍在原位，未移动、删除、暂存或复制。
- 23 个 E 类文件的源码内容未修改；其冻结哈希全部一致。
- 数据库和计算目录未修改。

## 条件

在把旧 A/B/C 变更集用于暂存或提交前，必须由人工确认
`tests/test_repository_contracts.py` 的 2A 结构契约 hunk，并建立新的审查
基线。不得静默更新旧条件关闭哈希链，也不得用旧 patch 覆盖当前测试文件。
