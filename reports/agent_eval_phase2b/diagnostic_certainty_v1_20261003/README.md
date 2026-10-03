# Phase 2B：单一诊断 Harness 候选实验

**IMPROVED_NO_REGRESSION**：基线 5 题可评分、3 题匹配；候选 5 题可评分、5 题匹配。原成功案例 c001/c003/c004 保留，c002/c005 新增匹配。

candidate improved performance on this public development set

## 交付

- [Harness v1 原文](harness/diagnostic_certainty_v1.txt)及[版本与 SHA-256](harness/manifest.json)
- [冻结对照报告](comparison_report.md)
- [完整字节保真归档](deliverables.zip)：33 个原文件，含 Harness、三个公开输入、完整实际输入、首次原始回答、CLI 可见事件、实际设置/耗时/退出码、机械提取记录、一次评分报告及最终核验。
- [发布清单及逐文件身份](publication_manifest.json)
- [本次只读发布审计](publication_repository_audit.json)及[实际命令与退出码](publication_audit_execution.json)

冻结对照报告内的 control/ 相对链接用于解压完整归档后查阅。ZIP 保留原始字节，避免 Git 换行规范化改变身份；不包含 CLI 内部 SQLite 临时状态、登录凭据或额外私有参考副本。

## 固定基线及结果边界

基线分支 codex/phase2a-diagnostic-trial-20260930，结果提交 697153133a4d430120543b02f6cd5abe1d481c73。公开规范 JSON 身份保持 500d33ac92a838371e1f76e096e6bc0db95ec8d864c0993495a2467a191d9ba2。

候选仅在原完整公开输入前加入一条通用 Diagnostic certainty rule。模型设置 gpt-6.1-sol、reasoning effort high、service tier default 和工具关闭参数复用；CLI 从 0.159.0-alpha.12.1 变为 0.160.0，不能将变化完全归因于 Harness。

仅一次候选答题、一次评分，48.844 秒，两者退出码 0。首次原始回答与评分输入字节相同，无修答案或再生成。实际后端模型标识和底层模型请求次数未知。可见事件没有明确额外工具活动；完整读取隔离及隐含上下文仍未验证，整体污染状态未知。

- evaluation_mode = public_development_smoke
- reference_access_isolation_verified = false
- capability_improvement_established = false

本轮规则依据这五题的公开开发结果提出；未证明能力提升、泛化或生产 Agent 改善，未推广到生产。冻结记录中的不 commit/push 描述之前实验阶段；本次归档发布依据随后单独的“推送”授权。

发布前 31 个清单原文件、33 个 ZIP 成员及 47 份基线/参考材料通过字节身份核验。只读审计返回 1，既有 docs/06_MODULE_MAP.md 模块状态投影漂移原样记录，未修复、未 sync。生产源码、benchmark、参考、评分器及科学标准未修改；未重跑答题或评分。新提交 CI 与跨机器评分重放尚未验证。
