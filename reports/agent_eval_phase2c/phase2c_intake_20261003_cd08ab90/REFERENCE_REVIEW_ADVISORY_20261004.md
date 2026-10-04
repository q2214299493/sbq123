# Phase 2C 参考审核建议

## 身份与状态

保存日期：2026-10-04（Asia/Shanghai）。来源：本次用户要求对 h001–h007 进行参考审核后，当前 Codex 会话给出的审核回复；随后用户明确要求“推送”。没有另行编造审核者姓名、消息 ID 或历史审核时间。

**ADVISORY_ONLY / AWAITING_APPROVAL**。当前会话保留此前开发实验上下文，不能声称属于全新上下文的独立审核。本文件保存既有建议，不构成独立专家批准，不将任何 pending/incomplete 状态改为 approved。

审核对象：本目录既有 Phase 2C intake 归档中的 reviewer_packet、policy、公开草稿及对应历史来源。发布前 HEAD 为 `3d917c1ecc9011d7a75269fa3585682f5cf03b39`。本次没有重新制定参考、修改题面、重新构建案例或运行评分。

## 逐案例建议

建议 h002、h003 INCLUDE，其余五项 NEED_MORE_EVIDENCE。不为满足标签分布补造案例或提高确定性。

| 案例 | 建议 | 理由与限定范围 |
|---|---|---|
| h001 | NEED_MORE_EVIDENCE | 历史摘要记录并行配置及初始化错误，支持调查启动配置；原始启动输入、M_divide/MPI 错误上下文及适用配置约束缺失，尚不能确立因果参考。替代任务属于同一事件链。 |
| h002 | INCLUDE | 快照中两项频率分类阈值为 null，可以确认该阈值型分类缺少必要配置。confirmed 仅限分类配置缺失，不代表计算失败、DIMER 缺陷或 TS 无效。公开的派生分类/接受状态有答案提示风险，此题适合作为配置读取案例，不能作为原始日志因果诊断的证明。后续接受结果不得反向纳入早期题面。 |
| h003 | INCLUDE | 三节点、内部 C–H 距离及较大的相邻 H 位移支持局部采样不足的解释；观测确认给定区间缺少内部采样点，但未建立路径生成过程为何产生缺口，原因保留 hypothesis。一步预算不证明优化器缺陷，也不证明模型误差。1.3–1.8 Å 仅作为本题给定条件，不推广为统一科学标准。公开证据未包含私有审核中的最终失败判词。 |
| h004 | NEED_MORE_EVIDENCE | 现有材料仅建立 wrapper 阶段退出。TMPDIR=/tmp 不证明临时目录故障，后续授权中的归因不能替代原始错误证据。缺对应 stderr/临时目录操作错误、时间绑定及公开证据 ID。原任务、探针、重试不能分别计作独立案例。 |
| h005 | NEED_MORE_EVIDENCE | electronically unconverged forces 是派生诊断，直接提示 SCF 分类；需要电子停止条件、残差或收敛标志与力评估的对应记录。NELM 耗尽、力升高、曲率变化不能单独建立底层原因。 |
| h006 | NEED_MORE_EVIDENCE | 摘要支持达到步数上限且未记录离子收敛，但不足以区分优化、几何或其他原因。需要原始终止记录、实际收敛条件及对应力/步数历史。局部键长不能确认 H 转移或脱氢。 |
| h007 | NEED_MORE_EVIDENCE | 通信失败摘要支持调查运行启动问题；缺原始带时间的调度查询、MPI 探针，具体原因及事件谱系未建立。历史 RUN 不证明电子计算已启动，不能据此认定 SCF 失败或节点故障。 |

## INCLUDE 案例的四字段建议

以下仅是待确认建议，不是已批准 reference。

```json
{
  "h002": {
    "failure_class": "validation",
    "root_cause_status": "confirmed",
    "next_review": "owning_ts_validation_review",
    "evidence_ids": ["e003", "e004", "e005", "e006", "e007", "e008", "e009", "e010"]
  },
  "h003": {
    "failure_class": "geometry",
    "root_cause_status": "hypothesis",
    "next_review": "review_path_repair_without_assuming_model_error",
    "evidence_ids": ["e011", "e012", "e013", "e014", "e015", "e016", "e017", "e018"]
  }
}
```

## 分组、证据与未验证事项

- g004 的 h004、h005、h007 即使后续纳入，也只支持同反应家族鲁棒性检查，不计作跨反应泛化。不同阶段可属于不同事件，但须先核实谱系、排除计算及重试重复计数。
- 前一轮审核回复记录了 22 个选定文件与清单哈希一致；本次仅保存该审核意见，没有重新执行这 22 项检查。字节身份不能证明历史观测时间、当时可见范围或摘要诊断正确。
- 当前只有两项建议纳入，尚不足以组成要求的 6–10 个可评分案例；至少两个 confirmed 反例及可靠 unknown 参考尚未建立。
- 全新上下文独立性未成立；参考批准、题面最终冻结、A/B、评分、泛化及晋级均未验证。

## 本次发布检查

- 实际发布工作树：`C:\Users\86177\.codex\worktrees\phase2a-publication\work`。
- 分支：`codex/phase2a-diagnostic-trial-20260930`。写入前 `git status --short` 无输出。
- `git ls-remote --heads sbq123 refs/heads/codex/phase2a-diagnostic-trial-20260930`：退出码 0，远端为 `3d917c1ecc9011d7a75269fa3585682f5cf03b39`。
- `python -B -m scripts.state_manager.cli audit --phase start --format json`：实际子进程退出码 1；1 error、17 warning、18 review_required。错误为既有 `docs/06_MODULE_MAP.md` 的 transition_state_search 管理投影漂移；警告为其他工作树需所有权复核。本次未修复这些既有事项，未运行 repo-state sync。
- 本次只新增此 Markdown 审核建议；源码、Harness、题面、参考、原始证据、科学标准、生产数据库及计算状态未修改。没有模型答题、A/B、评分、训练或真实计算。

下一步：补齐其余五项原始证据与事件链绑定，再进行参考复审。
