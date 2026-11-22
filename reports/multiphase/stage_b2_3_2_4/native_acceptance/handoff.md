# Review of the failed native initialization

The event `history-stage-b2-3-2-4-oxide-native-init-failed-20261122` asks to append the real fatal reader result and the consumed authorization to the project's history. It binds seven evidence files. No original history event or preparation report was edited.

| Tree | Independently generated pending proposal | Startup audit | Global safe-only sync |
| --- | --- | --- | --- |
| Development | `proposal-31dd8fa1ae15acfcca386af9` | 0 errors, 81 warnings | Exit 2, existing Scientific Intake schema evidence hash mismatch |
| Publication | `proposal-306a5e31d84d6b19dac5694c` | 1 error and 80 warnings, including existing managed module row drift | Exit 2, existing history-compaction source changed before proposal generation |

After synchronization the current hashes of `docs/08_HISTORICAL_RESULTS.md` and `data/state_handoff/projection_manifest.json` in both trees matched each proposal's pre-change hashes. Both proposals await an independent `approve` or `reject` decision. These decisions concern historical reporting. The sole execution approval is already consumed. [Previously identified source conflicts](../../stage_b1_5/handoff.md) / [Native failure](native_acceptance.md)
