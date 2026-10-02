# 首次公开开发集受控试运行

本轮使用 `286ad0c` 的 `revision_03_user_approved_20261001`。一次新 Codex 答题任务、一次现有 `cases-evaluate` 评分；5 题完整可评分，3 题匹配。c002、c005 的 `root_cause_status` 与批准参考不匹配，首次回答保持原样。

- evaluation_mode = public_development_smoke
- reference_access_isolation_verified = false
- capability_improvement_established = false

CLI 模型设置为 `gpt-6.1-sol`，耗时 52.164 秒、退出码 0；实际后端模型标识及底层请求次数未知。可见事件没有明确额外工具调用或参考读取，整体污染状态仍为未知，不能据此证明技术隔离或能力提升。评分器的 comparison_ready 只说明可执行参考比较。

## 交付

- [运行报告](run_report.md)
- [字节保真归档](deliverables.zip)：20 个原文件，包含三个公开输入、首次原始回答、完整 CLI 可见事件、执行设置与回执、原样评分输入和实际评分报告。
- [发布清单及逐文件身份](publication_manifest.json)
- [本次只读仓库审计](repository_audit.json)及[实际命令与退出码](audit_execution.json)

归档不包含 CLI 内部 SQLite 临时状态、登录凭据或额外私有参考。公开输入、回答、评分报告及冻结运行记录均保持原始字节；ZIP 避免 Git 换行规范化改变身份。

## 范围与复核

这是已公开开发/回归案例的接口试运行，不是严格隔离能力基线。未再次答题、重试、修答案、改源码、改题面、改参考或重跑评分。运行记录中的“未 commit/push”描述执行阶段；本次发布依据随后独立的“提交推送”授权。

本次只读仓库审计返回 1，存在既有 docs/06_MODULE_MAP.md 模块状态投影漂移；未修复或运行状态同步。发布前检查归档成员哈希、CRC、首次回答与评分输入一致性，以及 Git diff 检查。新提交的 CI 尚未验证。

跨机器评分需要从[已批准参考版本](../revision_03_user_approved_20261001/README.md)按现有接口重建路径绑定；本次未验证可移植重放，也未新增执行或评分尝试。
