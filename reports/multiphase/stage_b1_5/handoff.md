# B.1.5 State Handoff

正式入口分别在开发树和独立发布树接收 `history-stage-b1-5-independent-acceptance-20261122`，事件绑定五份报告的 SHA-256。两份本地提案均请求将 B.1 离线验收摘要追加到 `docs/08_HISTORICAL_RESULTS.md`，并更新相应的 `data/state_handoff/projection_manifest.json`。两树对应文件的当前哈希不同，需分别决定。

| 工作树 | 本轮提案 | 启动审计 | 全局 sync --safe-only |
| --- | --- | --- | --- |
| Windows 开发 | `proposal-1b9c5302d58089f06d09629b` | 0 错误，81 警告 | 退出 2。既有 Scientific Intake schema 的历史来源哈希不同。 |
| Windows 独立发布 | `proposal-99fdcb67ca9c8fafd2f2f8a1` | 1 错误，80 警告，包括既有 transition_state_search 受管模块行漂移 | 退出 2。既有历史压缩事件的源文件哈希已变化。 |

每份提案的选项为 `approve` 或 `reject`，尚待审阅。safe-only 后逐项复核，两个目标文件均保留该树提案中的原始哈希。本轮验收记录没有授予科学运行权限。

## 历史阻断的现场依据

- 开发树中 `configs/kinetics/scientific_intake.schema.json` 的当前 SHA-256 为 `45dc70815b0e9ec072909f32bb634859b2c9d50c4dc2f556fed0437d9193e9ec`，与 Phase 2.2.1 事件的绑定一致。较早的 kinetic-data 和 Phase 2.2 thermochemistry 事件分别绑定 `cac5550c382a2bafcf2a20c4f7f90b46331de6fbe9f701ca35cf32200151baf4` 与 `feabcbe76179d3624cead8d6469fcdd6a4796ba8e11c1dbaee30944487f5acab`。这些历史版本的归属需要单独审阅。
- 发布树历史压缩事件 `state-history-compacted-7ca5604cfc573d419007f891` 绑定 `docs/02_CURRENT_STATE.md` 的 SHA-256 为 `f6eee7315643818ddd25c238bc18db07598db7ef48227fda1fdb2f603f8b71ed`，现场为 `17e5c1dd75605115aece7583cd3bce05425e04145f328f65442d092c117f2b7a`。需由审阅者核对压缩所依据的历史版本与当前受管状态。两项历史阻断均已在此前检查点记录。[既有治理记录](../stage_b1_3/handoff.md)
