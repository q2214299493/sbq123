# Stage B.2.2.1 · 状态交接

正式入口在开发树和独立发布树分别记录待审历史事件 `history-stage-b2-2-1-structural-identity-20261122`。事件绑定验收报告、回归明细、四例机器回执和通用结构 fixture 的 SHA-256。

| 工作树 | 当前提案 | 启动审计 | 全局 safe-only 同步 |
| --- | --- | --- | --- |
| Windows 开发树 | `proposal-7f6528ba3485f0873d981dcb` | 0 错误，81 警告 | 退出 2。既有事件引用的 Scientific Intake schema 来源与 `configs/kinetics/scientific_intake.schema.json` 现有哈希不符。 |
| Windows 独立发布树 | `proposal-0c04aa61187159733b01b229` | 1 错误，80 警告，含原有 transition_state_search 受管模块行漂移 | 退出 2。既有历史压缩事件的源状态文件已变化。 |

每份提案均请求在本树的 `docs/08_HISTORICAL_RESULTS.md` 追加摘要并更新 `data/state_handoff/projection_manifest.json`。两者可分别选择 `approve` 或 `reject`，目前均待审。同步后核对两个目标文件，在各自工作树中仍与提案预期的原始哈希一致。历史冲突及其来源已有独立记录。[此前交接](../stage_b2_1/handoff.md) · [本轮验收](completion.md)
