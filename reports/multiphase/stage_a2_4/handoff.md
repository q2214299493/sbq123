# P4 State Handoff 现场回执

| 工作树 | 本轮历史记录提案 | safe-only 结果 |
|---|---|---|
| 开发 | `proposal-5a319103ea6e0e88d1edb512` | 退出 1，`ERROR: evidence hash changed: configs/kinetics/scientific_intake.schema.json` |
| 发布 | `proposal-8d0efbb0c8c747d16faf53e0` | 退出 1，`ERROR: state history source changed before proposal generation` |

两份提案由本轮事件在各自工作树生成，涉及 docs/08_HISTORICAL_RESULTS.md 和 data/state_handoff/projection_manifest.json 的历史记录投影。各自可选 `approve` 或 `reject`。这项选择只对应本次历史记录。

在提出 P4 事件后、调用 safe-only 前后，对两树全部受管视图、投影清单和事件目录逐文件比对摘要，两处均相同。没有自动选择待审决定。发布树的历史压缩在生成提案前失败，因此没有本轮可审批的压缩提案 ID。开发树旧模块事件的既有决定仍绑定当时的来源。受影响的行、源路径、完整 SHA-256 以及已缓存的关联提案见[冲突清单](state_conflicts.json)。
