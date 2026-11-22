# B.2.3.2.2 State Handoff

历史事件 `history-stage-b2-3-2-2-oxide-bridge-topology-20261122` 绑定合成图、逐边匹配输出与完成报告的 SHA-256。提案记录所选合成图的最大占位和初态匹配，只涉及各树的 `docs/08_HISTORICAL_RESULTS.md` 与 `data/state_handoff/projection_manifest.json`。

| 工作树 | 待审 proposal ID | 启动审计 | 全局 safe-only 同步 |
| --- | --- | --- | --- |
| 开发 | `proposal-a8f7ae7abbdecae341cc1cd0` | 0 个错误，81 个警告 | 退出 2。既有事件绑定的 `configs/kinetics/scientific_intake.schema.json` 来源哈希已变化。 |
| 独立发布 | `proposal-dcdd787a3ec7e39d017f841f` | 1 个错误，80 个警告，含既有 transition_state_search 模块行漂移 | 退出 2。既有历史压缩事件的来源在生成提案前已变化。 |

同步后已分别核对两个投影目标的当前 SHA-256，均等于各树提案的预期原值。两个提案均待人工选择 `approve` 或 `reject`。[既有来源冲突记录](../stage_b1_5/handoff.md) · [本次审计](completion.md)
