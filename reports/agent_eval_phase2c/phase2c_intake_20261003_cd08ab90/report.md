# Phase 2C 历史候选准备

当前状态：**AWAITING_INDEPENDENT_REFERENCE_REVIEW**。已整理7个不同事件线索、5个分组，构建6题 incomplete 草稿；已批准参考和可评分案例均为0。未执行A/B或评分，题面尚未冻结。

## 完成的工作

固定开发结果6971531、候选eccfaa2和Harness字节身份；未修改原五题、参考、policy、scorer或Harness。核实历史根目录为C:\Users\86177\Desktop\work，源码根目录为C:\Users\86177\.codex\worktrees\phase1-diagnostic-cases\work；源码与发布工作树干净。历史工作树原有755条状态记录保持原样。

材料沿现有错误记录、状态索引和明确的反应/任务目录只读查找。发现索引指向archive/state_history/ERROR_LOG_through_20260627.md不存在，记录缺口，未补文件或扫描整盘。成功计算没有强行改为失败；同一计算的重试只作为谱系材料，不扩成独立案例。

候选详见[intake.json](intake.json)、[审核队列](REVIEW_QUEUE.md)及[不含Harness/开发答案的审核请求](reviewer_packet/README.md)。h001为历史并行启动配置失败；h002为当时可选频率分类配置缺口；h003为C-H路径分辨率观测；h004包装器故障因存在后续TMPDIR归因且缺少原始因果日志而暂不入草稿；h005为不同Dimer事件的SCF症状；h006为formyl吸附弛豫检查点；h007为不同SCF派发事件、但谱系仍须确认。

## 来源及独立性限制

g004与开发集属于同一大反应家族，不能计作反应完全留出；h007与其他迁移恢复的关系还待确认，不能宣称所有候选统计独立。h001/h005/h006/h007只有历史摘要而缺少本地原始故障文件，保留partially_verified，独立审核可要求补证或排除。h002/h003为原有诊断分析中的观测字段，原始/派生身份如实标注。晚于所选快照的接受结论用于私有范围核对，未作为早期公开题面的证据。

参考由待指定的独立审核者依证据制定，组织者未填写任何expected、root_cause_status提案或approved。h001/h002可供审核者核验直接原因反例；目前尚不能宣称至少两个confirmed确实正确，也未建立confirmed/hypothesis/unknown三类覆盖。h004不能删除既有归因材料来凑unknown。缺少的状态覆盖如实保持缺口。

## 已执行核验

现有cases-build退出码0，6题草稿来源/类型/身份通过现有loader；未运行cases-evaluate，未创建answers。草稿public_sha256为c22ea216a59b715411c8a2760694826c4b7432b9ea5821d91f9892533315c8b4，不与原开发集身份混用。旧28份批准版本材料、Harness和已读源码/历史材料共48份核验未变。[产物核验](artifact_checks.json)、[实际命令与退出码](control/commands.json)。只读repo-state audit退出码1，输出保留；未修复投影或运行sync。

这里的draft_bundle仅证明既有构建/加载接口可用，参考为null且provenance=incomplete；它不是冻结的held-out评测包，不能交给模型答题。关键词及结构检查不构成公开题面的语义无泄漏证明，独立审核仍须确认。

## 下一步审核材料

请独立审核上述真实观测、范围与谱系，逐项给出现有四字段参考、完整evidence_ids和可核验批准来源；必要时排除或补证。审核完成后才新建review.json/reviewed_bundle并冻结公开三文件。随后按[待审核A/B执行与度量约定](ab_protocol_pending_review.json)，在相同当前CLI软件环境中先A后B各一次；按总分、参考确定性分层、false_confirmed/false_uncertain报告。当前没有泛化结论或晋级结果。

未修改生产源码、AGENTS、科学阈值、execution gate、数据库或模型权重；未访问生产数据库、运行SSH/HPC/VASP/Sella/训练、sync、commit/push/merge。新输出只在独立output_root。
