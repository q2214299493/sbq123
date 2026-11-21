# B.2.1 状态交接

State Handoff 的正式入口在两套工作树分别记录待审历史事件 `history-stage-b2-1-inventory-conservation-20261122`。事件绑定验收报告、回归明细、两个计数输入和两份验证输出共六个文件的 SHA-256。提案请求追加历史摘要并更新对应投影清单。

| 工作树 | 本轮待审提案 | 启动审计 | 全局 safe-only |
| --- | --- | --- | --- |
| 开发 | `proposal-31ad6877825209269f4fd731` | 0 错误，81 警告 | 退出 2。旧事件绑定的 `configs/kinetics/scientific_intake.schema.json` 摘要与现场文件不同。 |
| 独立发布 | `proposal-e1d6e8c50bd2732d7694bc47` | 1 错误，80 警告。已有 transition_state_search 受管模块行漂移。 | 退出 2。已有历史压缩事件所绑定的状态源文件已变化。 |

两份提案各自接受 `approve` 或 `reject`，均待研究者决定。同步后已分别核对 `docs/08_HISTORICAL_RESULTS.md` 与 `data/state_handoff/projection_manifest.json`，两者仍与各自提案中的原始摘要一致。此前检查点已经记录上述历史来源冲突及其来源哈希。[既有冲突详情](../stage_b1_5/handoff.md) · [本次验收](completion.md)
