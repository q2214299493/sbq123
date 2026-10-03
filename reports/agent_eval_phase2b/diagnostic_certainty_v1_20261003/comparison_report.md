# Phase 2B：单一 Diagnostic Harness 候选实验

结果分类：**IMPROVED_NO_REGRESSION**。基线 3/5；候选 5/5。新增匹配：c002, c005；旧匹配退步：无。

candidate improved performance on this public development set

| 案例 | Baseline | Candidate |
|---|---|---|
| c001 | match | match |
| c002 | diagnosis_mismatch | match |
| c003 | match | match |
| c004 | match | match |
| c005 | diagnosis_mismatch | match |

## 固定输入与唯一改动

- 基线分支：`codex/phase2a-diagnostic-trial-20260930`；结果提交：`697153133a4d430120543b02f6cd5abe1d481c73`。
- public_sha256：`500d33ac92a838371e1f76e096e6bc0db95ec8d864c0993495a2467a191d9ba2`。
- Harness v1：[原始文本](harness/diagnostic_certainty_v1.txt)，SHA-256：`e45bbff5866ec94794be22fb36854b91a9ba5e78dbbb72f8b6259cde948630cc`。
- 实际输入精确等于 Harness 原字节 + 一个换行 + 基线完整公开输入原字节。三个公开文件及 47 份基线/参考材料哈希保持不变，评分器与 policy 身份相同。

## 一次执行与评分

CLI 模型设置 `gpt-6.1-sol`；reasoning effort `high`；service tier `default`。复用同一单次流程、输出格式及工具关闭参数。CLI 从 `codex-cli 0.159.0-alpha.12.1` 变为 `codex-cli 0.160.0`，没有安装或降级；这是真实环境差异，不能将结果变化归因于 Harness 单一因素。

候选仅执行 1 次答题、1 次现有 `cases-evaluate` 评分；耗时 48.844 秒，CLI 退出码 0，scorer 退出码 0。无答案修复或再生成；本轮原始回答与评分输入字节一致：True。底层模型请求次数及实际后端模型标识未知。

保留[首次原始回答](control/first_raw_answer.txt)、[完整 CLI 可见事件](control/first_events.jsonl)、[完整实际输入](control/submitted_input.txt)、[执行设置](control/execution_settings.json)、[执行回执](control/execution_receipt.json)、[机械提取记录](control/extraction_record.json)、[实际评分报告](control/score_report.json)、[评分命令和退出码](control/scoring_execution.json)及[详细对照报告](comparison_report.json)。启动警告原样保留；未为消除警告重试。

可见事件未发现额外工具活动；参考读取与隐含上下文的完整隔离尚未验证，整体污染状态为未知。没有将未观察到的行为写成技术上不可能发生。scorer comparison_ready=True 仅表示评分比较条件满足。

## 核验与边界

准备及执行脚本语法检查通过；使用现有 owning Python sha256_json 校验 public 身份；两处代码工作树及 HEAD 保持不变；运行前后输入、批准参考与基线材料身份一致。本次只读仓库审计退出码 1，保留既有模块投影漂移（[审计](control/repository_audit.json)、[命令](control/audit_execution.json)），未修复、未 sync。没有源码变更，因此未运行生产回归测试。

evaluation_mode = public_development_smoke

reference_access_isolation_verified = false

capability_improvement_established = false

规则依据这五题的开发结果提出，本轮不证明能力提升、泛化、幻觉解决或生产 Agent 改善。未修改 benchmark、参考、评分器、科学标准或生产系统；未计算、训练、访问生产数据库或提交推送合并。Harness v1 保持冻结，等待下一步审核。
