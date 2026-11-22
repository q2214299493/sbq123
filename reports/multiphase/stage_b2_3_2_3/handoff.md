# State Handoff for the oxide structural preflight

The formal history event `history-stage-b2-3-2-3-oxide-zacros-structural-preflight-20261122` binds eight evidence files including the source graph, native member manifest, both unexecuted status receipts and the offline results. Each tree generated its own proposal to append that result to `docs/08_HISTORICAL_RESULTS.md` and update `data/state_handoff/projection_manifest.json`.

| Working tree | Pending proposal | Read-only startup audit | Global safe-only synchronization |
| --- | --- | --- | --- |
| Development | `proposal-c2c9d7b351f3a6fd7e21dfdb` | 0 errors, 81 warnings | Exit 2, existing `configs/kinetics/scientific_intake.schema.json` evidence hash conflict. |
| Publication | `proposal-f5df4648a2331b19b63df1ba` | 1 error, 80 warnings, including the existing transition_state_search managed-row drift | Exit 2, existing historical source changed before proposal generation. |

After synchronization, both projection targets in each tree matched that proposal's expected pre-change hashes. The available decisions for each proposal are `approve` and `reject`. An approval here concerns the offline history entry only. Native execution requires its own separately qualified inputs and authorization. [Existing conflict identities](../stage_b1_5/handoff.md) / [Preflight scope](completion.md)
