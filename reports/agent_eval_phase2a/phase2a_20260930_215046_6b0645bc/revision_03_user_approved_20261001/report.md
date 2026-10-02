# Phase 2A 用户批准版本

已核对 f5690e2 的全部 36 个 ZIP 成员与本地产物字节一致；revision_02 规范 JSON 身份为 46effdb86474a049ba273155e30d7eb430bb889cfee851e0286eff796da51afd。

本次用户批准原文、来源说明和字节 SHA-256 分别记录于 user_approval.txt、approval_source.json 和 review.json。审核者为“本次用户批准”，不是独立专家；平台消息 ID 和原始批准时间不可用，未编造。recorded_at 仅为本地记录生成时间。

构建了 5 个 reviewed_real 参考、47 项未改动的公开标量、1 个反应组。reviewed_real 仅表示存在本次范围限定的真实用户批准；历史时间与全部可见范围仍为 partially_verified。c003 题面补充三步预算停止条件范围，其他四题输入不变；全部证据均与旧包规范 JSON 身份一致。

新公开身份：500d33ac92a838371e1f76e096e6bc0db95ec8d864c0993495a2467a191d9ba2。全部 ID 逐项记录在 JSON 中。TASK 明确全部引用只检查输入覆盖，不评价证据筛选或因果相关性。未修改评分器或生产代码。

现有 cases-build CLI 退出码 0；现有 _load_bundle 接受全部 5 题。核验了参考源哈希、精确 ID 集合、公开字段白名单、独立公开包文件集合、c003 范围和旧文件/科学原件/Git 状态不变。详见 artifact_checks.json 与 execution_log.json。

只读 repo-state audit 退出码 1；完整结果保存在 repository_audit.json。审计漂移未修复，未运行 sync，不代表科学状态。首次只读检查末尾因默认 GBK 读取 UTF-8 文件退出 1；显式 UTF-8 后成功，无写入受到影响。

未执行 pytest/Ruff 全仓测试（没有源码修改）；未生成正式 answers，未运行模型、评分、真实计算/训练、生产数据库操作、SSH、commit、push 或 merge。

已准备好等待独立答题。隔离尚未验证。五题是已公开开发/回归材料，当前会话不能充当盲测答题者。不能声称保密留出集、独立反应泛化、科学接受或实测性能提升。

下一步：验证独立答题者只可读取 answer_pack，再收集首次答案。
