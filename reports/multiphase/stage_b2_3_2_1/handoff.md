# B.2.3.2.1 State Handoff

正式事件 `history-stage-b2-3-2-1-zacros-mapping-audit-20261122` 绑定五份审计报告的 SHA-256。提案请求在对应工作树的 `docs/08_HISTORICAL_RESULTS.md` 追加历史摘要，并更新 `data/state_handoff/projection_manifest.json`。其范围仅为记录离线证据。

| Windows 工作树 | 当前 proposal ID | 启动审计 | 全局 safe-only |
| --- | --- | --- | --- |
| 开发 | `proposal-a56e38a237e696d4f4aba6a2` | 0 个错误、81 个警告 | 退出 2，既有事件所引 `configs/kinetics/scientific_intake.schema.json` 的来源哈希发生变化。 |
| 独立发布 | `proposal-de389c379e9ca9bea2ce0e83` | 1 个错误、80 个警告，含既有 transition_state_search 模块行漂移 | 退出 2，历史状态压缩来源在生成提案前已变化。 |

两树同步后分别对上述两个目标重新计算 SHA-256，均等于相应提案的预期原值。两份提案分别可选 `approve` 或 `reject`，当前均待人工审阅。[既有治理冲突的来源](../stage_b1_5/handoff.md) · [本次交付](completion.md)
