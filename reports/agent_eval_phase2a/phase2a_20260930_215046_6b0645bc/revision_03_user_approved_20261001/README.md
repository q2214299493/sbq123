# Phase 2A 用户批准版本

状态：已准备好等待独立答题，隔离尚未验证。5题、47项公开标量、1个反应组，5项范围限定的本次用户批准参考。没有正式答案、模型运行或评分成绩；本材料为已公开开发/回归案例，不是保密留出集。

本次发布由准备完成后的明确“推送”指令授权。原 curation 报告中的不 commit/push 描述的是当时的准备范围；本次仅发布任务产物。旧 revision_02 草稿与归档保留原样。

- [核验报告](report.md)
- [完整字节保真交付包](deliverables.zip)：28个文件，包括批准原文、来源说明、独立 review.json、cases_manifest.json、原样来源快照、reviewed_bundle、answer_pack 及核验记录。
- [逐文件哈希和发布元数据](publication_manifest.json)

新公开规范 JSON 身份：500d33ac92a838371e1f76e096e6bc0db95ec8d864c0993495a2467a191d9ba2。

批准绑定 f5690e2 中 revision_02 的原公开身份 46effdb86474a049ba273155e30d7eb430bb889cfee851e0286eff796da51afd。c003 题面仅补充用户要求的三步预算停止条件范围，其他四题输入不变；全部47项原生证据均未修改。参考只代表给定快照的范围限定诊断，不是独立专家审核、科学接受或执行授权。历史观测时间与完整可见范围仍为 partially_verified。

## 答题与读取范围

answer_pack 仅包含 public.json、TASK.md、FORMAT.json。TASK 要求 evidence_ids 逐项列出本题全部公开 ID；该字段仅检查输入覆盖，不评价证据筛选或因果相关性。不能把本仓库、归档、参考、审核来源或当前会话整体提供给盲测答题者。当前会话已看过参考，不能充当盲测答题者。目录分离不是访问隔离；隔离尚未验证。

## 在新位置重建

ZIP 避免 Git 换行规范化破坏原字节哈希。解压前后核对 publication_manifest.json。冻结 private.json 保留原始 allowed_root 绝对路径，不能声称从其他机器克隆后直接可加载。使用同一代码基线和现有 CLI，在全新输出目录重建：

    python -B -m scripts.ts_strategy_engine.cli learning cases-build --manifest <解压目录>/cases_manifest.json --allowed-root <解压目录> --bundle <全新的包目录>

新位置改变私有包身份，公开规范 JSON 身份应保持本页所列新身份；本次未执行跨机器重建验证。不要改动 review.json、批准原文或证据来适配路径。

本次已有构建和加载核验通过。发布前只读 repo-state audit 返回1：docs/06_MODULE_MAP.md 的 managed_projection_drift 未修复；未运行 sync。没有生产源码、原始科学证据、科学接受标准或数据库修改；没有 SSH、计算、训练或评分。下一步是验证独立答题者的读取范围，再获取首次答案。
