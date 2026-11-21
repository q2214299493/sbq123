# B.1.4 State Handoff

The owning CLI recorded `history-stage-b1-4-native-rate-adapters-20261121` with the hashes of the completion report, evidence inventory and two engine qualification reports. Each checkout generated a fresh proposal to append the replay checkpoint to `docs/08_HISTORICAL_RESULTS.md` and update `data/state_handoff/projection_manifest.json`.

| Checkout | Pending decision | Startup audit | Global safe-only synchronization |
| --- | --- | --- | --- |
| Development | `proposal-85ca2b08511986c7b6f11bfa` | 0 errors, 81 warnings | Exit 1. Existing historical evidence binds a different hash of `configs/kinetics/scientific_intake.schema.json`. |
| Publication | `proposal-150a88262e31aefbeaee604f` | 1 error, 80 warnings. Existing drift in the managed transition-state module row. | Exit 1. The history compaction source changed before proposal generation. |

Both proposals remain pending. A reviewer can choose `approve` or `reject` in the corresponding checkout. The historical conflicts predate this checkpoint. Their existing source bindings and decisions were preserved. [Completion report](completion.md)
