# B.2.2.3 状态交接

事件 `history-stage-b2-2-3-cross-phase-elementary-20261122` 绑定验收报告、回归报告、机器回执和三份合成输入的 SHA-256。通过两棵工作树各自的正式入口生成提案，均等待人工审阅。

| 工作树 | 当前 proposal ID | 启动审计 | safe-only 同步 |
| --- | --- | --- | --- |
| 开发树 | `proposal-5ae5b76495c80eb5ec0c9a25` | 0 个错误，81 个警告 | 退出 2。既有历史事件引用的 Scientific Intake schema 与当前文件哈希不符。 |
| 独立发布树 | `proposal-1e2454509490a451ae3af717` | 1 个错误，80 个警告，含既有 transition_state_search 受管行漂移 | 退出 2。历史状态压缩事件引用的源文件已变化。 |

两份提案均请求将本轮摘要追加至本树的 `docs/08_HISTORICAL_RESULTS.md` 并更新 `data/state_handoff/projection_manifest.json`。可在对应工作树分别选择 `approve` 或 `reject`。同步结束后逐项验证，这两个目标文件仍匹配各自提案的预期原始哈希。

开发树 `configs/kinetics/scientific_intake.schema.json` 的现场 SHA-256 为 `45dc70815b0e9ec072909f32bb634859b2c9d50c4dc2f556fed0437d9193e9ec`。发布树 `docs/02_CURRENT_STATE.md` 的现场 SHA-256 为 `17e5c1dd75605115aece7583cd3bce05425e04145f328f65442d092c117f2b7a`。需独立审阅旧事件所依据的历史版本。[历史来源哈希与事件](../stage_b1_5/handoff.md)
