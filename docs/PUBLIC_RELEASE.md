---
document_class: CURRENT_REFERENCE
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: CURRENT_CODE_STATE_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Publication scope

CURRENT_CODE_STATE: this B6 branch is based on B5 commit
`3a1bb3f461147a7dc9b5df5efca89de621d27f38`. Development source remains
`C:/Users/86177/Desktop/work`; isolated Git worktrees carry reviewed task-owned
changes on the independent `sbq123` history. They do not imply all development
changes or private runtime evidence were synchronized.

`configs/public_source_snapshot.json` is the immutable 2026-09-08 initial export
manifest (source HEAD `3a4c23f3bae8da264323fea75d6fe593ca562845` plus selected dirty
files). It is HISTORICAL, not a manifest of later B1-B6 commits. Git commits and
scoped completion reports identify subsequent software changes. The manifest is
not regenerated against missing private data.

No production SQLite database, credentials, POTCAR, full model weights or every
runtime output is promised. production_schema_version: NOT_VERIFIED_IN_B6.
See [document governance](DOCUMENT_GOVERNANCE.md) and
[data policy](../configs/data_governance.yaml).

## Historical initial release record — 2026-09-08

Everything below retains the original release-specific scope. Its tests and
paths are HISTORICAL observations, not current release or deployment claims.

# 发布来源与边界

发布日期：2026-09-08。源码来自本地 `work` 当前文件，而不是仅来自旧 HEAD。
源仓库 HEAD 为 `3a4c23f3bae8da264323fea75d6fe593ca562845`，源工作区存在未提交修改；
`configs/public_source_snapshot.json` 逐文件记录本次采样内容。

## 唯一修改来源

修改和科学工作继续在 `C:\Users\86177\Desktop\work` 进行。
`C:\Users\86177\Desktop\sbq123` 仅为发布副本，禁止把它当作第二个开发目录。
后续发布必须重新从 `work` 同步并检查差异；不得仅在发布副本修复功能。
原 `sbq`、`sbq-public` 仓库及旧目录没有在本次发布中删除。

## 包含内容

完整现有 scripts、configs、tests、modules、skills、docs、tasks 和 CI，
以及此前已审查公开的必要测试、校准和结构样例。新增本地三个 Dimer/NEB
辅助脚本及状态事件包含在内。代码和科学配置按源文件复制，不合并旧公开版的独有修改。
仅 README、本说明、公开清单和 .gitignore 为发布说明或打包适配。
Git 按 .gitattributes 规范化部分文本换行；清单同时记录源字节摘要与 Git blob ID。

## 不包含内容

真实 SQLite 数据库、个人报告、下载文章正文、POTCAR、密钥、模型权重、
大型 VASP 输出、临时环境和独立的 scientific-problem-compiler 项目。
不承诺复制了所有运行数据；证据路径和摘要可能指向源机器，本仓库不能据此
恢复正在运行的作业或证明科学结果。

## 验证边界

测试和 Ruff 以本次提交对应的检查记录为准。没有运行或提交任何集群计算。
源工作目录初次测试为 542 passed、2 failed：一次 Windows 并发替换文件错误，
以及临时目录和独立子项目触发目录契约检查。干净副本和 GitHub CI 结果另行记录，
不能据其通过声称源目录问题已修复。

干净发布副本实际验证：`pytest` 544 passed；`ruff check scripts modules tests` 通过；
Sella 与 pymatgen 导入通过；源码差异检查通过；staged 密钥扫描无发现。
源目录的并发文件写入测试单独复测为 1 passed，未修改其实现。
初始全树 diff 检查仍报告来源结构样例的尾随空格，保留原始字节，未批量清理。
GitHub Actions 以本仓库对应提交的实际运行记录为准。
