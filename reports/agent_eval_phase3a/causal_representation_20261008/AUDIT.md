# Phase 3A：最小诊断因果表示实现与审计

日期：2026-10-08（Asia/Shanghai）。完成代码与测试，不运行模型。

## 实际工作树与范围

实现工作树：本会话已附加的 `phase2a-publication/work` 独立工作树。
分支：`codex/phase2a-diagnostic-trial-20260930`。
开始 HEAD：`32a9d0b52123a8b94b3ac09e293846fd50f7f889`，开始工作树干净。
另一个开发工作树存在既有修改；本轮未编辑该工作树。
两份 current_task 指向既有科学任务，本轮明确用户请求优先，不重写科学任务或状态文档。

只读 startup audit 命令：
`python -B -m scripts.state_manager.cli --root <publication-worktree> audit --phase start --format json`
退出码 1：error=1 / warning=17 / review_required=18。
已有 error 是 `managed_projection_drift`：`docs/06_MODULE_MAP.md#module_row:transition_state_search`。
未把审计发现作为科学证据，未恢复投影或运行 sync；完整输出保存在外部交付目录。

## 使用点：先区分 A 与 B

A 是离线 case answer/reference；B 是生产 learning outcome/event。
离线格式通过 learning_cli 的 cases 分派独立读写，先于 database 分派返回。
生产 _outcome_record、历史导入、修订及 retry assessment 不读取 offline ANSWER_KEYS/DIAGNOSIS_KEYS。
代码未显示必须同步生产 schema 的依赖。因此只迁移 A；B 的 root_cause_status、确定性失败阻断与事件存储不变。

以下仓库行号绑定修改前 HEAD。另已只读核查 33 份已知外部冻结历史文件中的 190 个匹配行，均归为历史 A 数据并保留原字节。公开审计不包含本机路径索引、历史参考或答案内容；完整本地检查记录保留在原交付目录。

| 文件 | 修改前行号 | 分类 |
|---|---|---|
| `modules\transition_state_search\LEARNING.md` | 38, 55 | A_offline_case_documentation |
| `modules\transition_state_search\LEARNING.md` | 186 | B_production_outcome_documentation |
| `reports\agent_eval_phase2a\phase2a_20260930_215046_6b0645bc\REVIEW_QUEUE.md` | 7, 8, 9, 10, 11 | historical_A_artifact_or_advisory_preserved |
| `reports\agent_eval_phase2a\phase2a_20260930_215046_6b0645bc\public_development_smoke_20261002_45a0ff40\README.md` | 3 | historical_A_artifact_or_advisory_preserved |
| `reports\agent_eval_phase2a\phase2a_20260930_215046_6b0645bc\public_development_smoke_20261002_45a0ff40\run_report.md` | 33 | historical_A_artifact_or_advisory_preserved |
| `reports\agent_eval_phase2c\phase2c_intake_20261003_cd08ab90\REFERENCE_REVIEW_ADVISORY_20261004.md` | 33, 39 | historical_A_artifact_or_advisory_preserved |
| `reports\agent_eval_phase2c\phase2c_intake_20261003_cd08ab90\report.md` | 17 | historical_A_artifact_or_advisory_preserved |
| `scripts\ts_strategy_engine\learning_cases.py` | 18, 69, 71, 72 | A_offline_case_evaluation |
| `scripts\ts_strategy_engine\learning_evaluation.py` | 16, 65, 124 | A_offline_case_evaluation |
| `scripts\ts_strategy_engine\strategy_learning.py` | 147, 170, 246, 252, 262 | B_production_outcome_event |
| `tests\test_ts_learning_cases.py` | 22, 110, 281, 320, 382 | A_offline_case_evaluation |
| `tests\test_ts_strategy_learning.py` | 52, 164, 165 | B_production_outcome_event |

### 读写责任

- `learning_cases.py`：原 expected schema 在 _reference 校验；build_cases 写 private reference，validate_built_case 在加载时重验。pointer token 仅防选择私有字段，仍保留旧字段防泄漏。
- `learning_evaluation.py`：ANSWER_KEYS/_answer_error 读答案；evaluate_cases 读参考、确定性比较并写 summary report。报告原本只含状态/计数/身份，不包含独立 root_cause_status 字段。
- `strategy_learning.py`：_outcome_record 校验并产生 outcome；record_outcome/revise_outcome/import_failure 写事件；retry_assessment 读取 confirmed+deterministic 条件；task_lessons 读取并输出摘要。
- `learning_store.py` append_event/save_event/read_events 和 registry_schema 的 ts_strategy_events 使用通用 hash-bound payload JSON，没有独立 root_cause_status 数据库列。
- 离线测试的 synthetic 写入/读取迁移；生产 learning outcome 测试保留。
- 旧 reports/queues/FORMAT/answers/reference/外部冻结记录属于历史数据，不是当前运行 schema 定义；保持原字节。

## Schema diff

```diff
  failure_class: string
- root_cause_status: confirmed | hypothesis | unknown
+ causal_claim: string | null
+ causal_status: confirmed | hypothesis | unknown
+ causal_evidence_ids: list[string]
  next_review: policy route
  evidence_ids: list[string]
```

answer 额外保留 case_id/input_sha256；reference expected 使用上述六字段。
case manifest/public/answer set/report schema 1 → 2；private bundle format 2 → 3。
公共 evidence 仍仅 scalar；源边界、hash/ID 检查及 write-once 输出保留。
源码 schema patch 和 SCHEMA_DIFF.json 随交付保存。

## 最小实现

在已有 learning_cases.py 中增加一个共用 diagnosis_error，builder/loader/evaluator 复用；不新增模块、类、依赖、数据库或框架。
unknown 必须 null/[]；hypothesis/confirmed 必须非空 claim/causal IDs。
两个 ID 列表均唯一，causal IDs 必须属于 evidence_ids，evidence_ids 必须来自本题公开 evidence。
额外或缺少字段拒绝。causal_status 不选择 failure_class；现有 policy 只由 failure_class 选择 route。
reference 保持显式 approval/basis、独立来源和 hash binding。confirmed 仅修饰实际 claim，不能延伸到更深原因。
代码只验证形状，不验证 claim 的真实性、具体性、可检验性或支持力度；这些仍属于参考审核职责。
评测比较六字段：claim 原文精确相等，ID 列表按集合比较。不加入关键词式科学验证。

## Migration decision：fail-closed

当前 builder 拒绝 schema 1 manifest；loader 拒绝旧 private format（在来源校验与报告写出之前），要求重新审核参考并重建。
新 bundle 的旧答案格式被标为结构/版本错误，不补 causal_claim，不自动把 root_cause_status 映射成 causal_status。
历史 JSON 可供只读人工审计；历史评分复现需要历史代码 checkout，不给新 scorer 增加第二套兼容路径。
本轮没有重建或更改任何 Phase2A/2B/2C benchmark/reference/answers/results。
将来迁移须在新路径先重新审核明确 claim 与 supporting ID binding，不在原冻结包内修改。
生产 outcome/event 没有迁移，registry schema/policy/execution gate 不变。

## 验证

- Python py_compile 与导入检查：退出码 0。
- 最终 `python -B -m pytest tests/test_ts_learning_cases.py -q -o addopts=`：82 passed，退出码 0。
- `python -B -m pytest tests/test_ts_strategy_learning.py tests/test_code_structure.py tests/test_b5_architecture_boundaries.py -q`：68 passed，退出码 0。
- 修改 Python 文件的 Ruff：退出码 0。
- diff whitespace 检查和最终保护文件 hash 核验记录在 FINAL_VERIFICATION.json；最终命令结果作为事实依据。
- 初次测试阶段 78 cases 通过，补充缺字段拒绝与 causal IDs 比较测试后，最终 82 cases 通过；没有隐藏失败或以重答改变实验结果。
- 覆盖用户要求的八类结构规则、三种 certainty 与 class/route 独立、同一 observation 下 claim A confirmed / claim B hypothesis，以及 claim 改变/引用集合改变造成 mismatch。
- 继续覆盖 F1–F4、false/0、true/1、1/1.0 的公开 evidence 类型伪造、来源越界/失效、reference 隔离、重复 ID、未评分分母、write-once、CLI 退出码与版本 hash。
- 所有案例测试是临时合成文件；生产学习回归仅使用既有测试临时 fixture，不操作生产数据库。

## 未解决问题与未验证范围

1. claim 的语义等价/改写尚未评估。不同文本即使语义相同也会 mismatch；本轮不引入第二评分器或 LLM judge。
2. 结构通过不能证明科学因果；reference reviewer 必须明确层级与支持证据。
3. 历史参考尚未迁移为明确 claim；不替历史 reviewer 编写新 claim。
4. 生产 outcome 仍缺 explicit claim，这是独立设计问题。本轮无必要同步依赖，不自行扩大迁移。
5. 未验证模型诊断能力/实际读取隔离/生产部署或科学收益；未运行模型、v3、Phase2C A/B、训练或真实计算；未跑全仓库测试。
6. 启动审计的状态投影漂移仍未处理。

实现阶段未 commit/push/merge。2026-10-08 用户后续明确授权只在独立分支 commit/push 供代码复审；禁止 merge、部署、repo-state sync 及生产操作的边界继续有效。未改 AGENTS/生产 Agent/execution gate/科学阈值/数据库/模型权重。
下一步仅审核这个 schema diff、兼容性决定与未解决问题。
