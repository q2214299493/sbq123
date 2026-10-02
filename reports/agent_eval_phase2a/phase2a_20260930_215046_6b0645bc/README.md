# Phase 2A 真实诊断候选交付

当前参考版本：[revision_03_user_approved_20261001](revision_03_user_approved_20261001/README.md)。5项范围限定的本次用户批准参考已构建；隔离尚未验证。该目录保留参考准备阶段记录，材料属于已公开开发/回归案例。

首次[公开开发集受控试运行](public_development_smoke_20261002_45a0ff40/README.md)已保存原始回答与评分：5题可评分、3题匹配。没有建立严格读取隔离或能力提升；本次提交推送依据用户随后明确授权。

以下保留 revision_02 的历史草稿说明。历史状态：**AWAITING_REFERENCE_REVIEW**。5个真实历史候选、1个反应组、47项公开标量；当时已批准参考和可评分案例均为0。

本提交依据准备完成后的“推送”指令，只发布本轮产物。代码审查基线为 b353ba4a00d0ee1d5b3f833dc71d0634f1a1e9cd；未改生产源码、原始历史材料或科学接受标准，未执行repo-state sync。

- [准备报告](report.md)
- [私有审核者队列](REVIEW_QUEUE.md)：逻辑上属于审核材料，在此Git仓库发布不构成私有访问控制。
- [完整字节保真交付包](deliverables.zip)：36份原文件，包括启动上下文、原始/派生快照、清单、审计日志及草稿包。
- [实际逐文件哈希及发布元数据](publication_manifest.json)

ZIP SHA-256：707067151a433394dd3c88d4a1690c314d181f568a50b48fa8eb663b4531381b。

## 使用旧草稿 revision_02（历史说明）

解压到一个新的目录，只使用 revision_02 中的审核队列、intake、draft_bundle和answer_pack。根目录初版包是superseded草稿；保留它们用于追溯二轮范围审查修正，不能混用版本。

revision_02/answer_pack 实际仅有 public.json、TASK.md、FORMAT.json。不得把本仓库、ZIP、private.json、审核队列、来源或日志整体挂载给正式答题者。文件/目录分开不证明读取隔离；还需要经过验证的独立读取环境。本轮参考尚未批准，不进入正式答题。

## 在其他机器重建草稿包

冻结的private.json保留了原准备环境的绝对路径，不能声称直接克隆后就可评分。ZIP是为了避免Git换行规范化破坏源文件字节哈希；先核对publication_manifest.json，再从归档解压原字节。使用原有CLI和同一代码基线构建到新路径：

    python -B -m scripts.ts_strategy_engine.cli learning cases-build --manifest <解压目录>/snapshots/manifest_v2.json --allowed-root <解压目录>/snapshots --bundle <新的草稿包目录>

这只重建草稿，不执行模型或评分，不需要数据库或全局--output。新allowed_root会改变私有包身份，公开规范JSON身份应保持：
46effdb86474a049ba273155e30d7eb430bb889cfee851e0286eff796da51afd。

审核后必须在新版本创建真实独立review.json与reviewed_bundle；不能把pending改成approved来跳过审核。下一步是审核队列中的五项具体问题，不是合并或自动推广策略。

原准备报告中的“不commit/push”描述的是之前的候选整理阶段；本次归档发布是随后单独授权的操作。只读仓库审计当时返回1（模块状态投影漂移），已如实保留，未自动修复。
