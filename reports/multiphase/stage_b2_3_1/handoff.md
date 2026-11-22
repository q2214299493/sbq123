# B.2.3.1 状态交接

正式事件 `history-stage-b2-3-1-catkinas-network-mapping-20261122` 绑定本轮完成报告、回归报告、能力矩阵、映射规范和机器回执。两棵工作树分别通过 repo-state propose 生成以下提案。提案请求把本轮验证摘要追加到历史视图并更新受管投影清单。

| 工作树 | 待审 proposal ID | 启动审计 | repo-state sync --safe-only 实测 |
| --- | --- | --- | --- |
| 开发 | `proposal-4ff4fdb11267ba77b82f4c26` | 0 错误、81 警告 | 退出 2，既有 Scientific Intake schema 的证据哈希与旧事件不匹配 |
| 发布 | `proposal-bbe141068143561e4cf46e68` | 1 错误、80 警告，transition_state_search 的受管模块行已有漂移 | 退出 2，既有历史压缩事件的来源已变化 |

每份提案可在其原工作树独立选择 `approve` 或 `reject`，目前均为待审。同步后逐项检查了 `docs/08_HISTORICAL_RESULTS.md` 和 `data/state_handoff/projection_manifest.json`，两者的当前 SHA-256 均与本树提案的 expected_sha256 相等。

开发树 `configs/kinetics/scientific_intake.schema.json` 实测 SHA-256 为 `45dc70815b0e9ec072909f32bb634859b2c9d50c4dc2f556fed0437d9193e9ec`。发布树 `docs/02_CURRENT_STATE.md` 实测为 `17e5c1dd75605115aece7583cd3bce05425e04145f328f65442d092c117f2b7a`。这两项需要分别审阅早期 schema 版本和状态压缩事件绑定的来源。[历史事件与原始哈希](../stage_b1_5/handoff.md)
