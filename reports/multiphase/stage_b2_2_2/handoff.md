# Stage B.2.2.2 | State Handoff

Event `history-stage-b2-2-2-interphase-transfer-20261122` records the offline software validation and binds five artifacts by SHA-256. The normal proposal command was run separately in each worktree. Each proposal requests a historical results entry and the corresponding projection manifest update.

| Worktree | Current proposal | Read-only startup audit | Safe-only synchronization |
| --- | --- | --- | --- |
| Windows development | `proposal-1df2cb6115a7962c1ce79496` | 0 errors, 81 warnings | Blocked by a historical source hash for the Scientific Intake schema |
| Windows publication | `proposal-06e1c07367468d1c6c14135f` | 1 error, 80 warnings, including existing drift in the transition state search module row | Blocked by the historical state compaction source hash |

Both proposals are pending. Each tree offers `approve` and `reject` for its own exact changes. After safe-only synchronization the historical results document and projection manifest still matched each proposal's pre-change hashes.

The current development SHA-256 for `configs/kinetics/scientific_intake.schema.json` is `45dc70815b0e9ec072909f32bb634859b2c9d50c4dc2f556fed0437d9193e9ec`. Earlier events bind older revisions. The publication event `state-history-compacted-7ca5604cfc573d419007f891` expects `f6eee7315643818ddd25c238bc18db07598db7ef48227fda1fdb2f603f8b71ed` for `docs/02_CURRENT_STATE.md`. Its present digest is `17e5c1dd75605115aece7583cd3bce05425e04145f328f65442d092c117f2b7a`. These conflicts require historical source reconciliation independent of the transfer validation. [Historical source bindings](../stage_b1_5/handoff.md)
