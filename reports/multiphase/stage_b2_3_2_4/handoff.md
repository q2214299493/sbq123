# B.2.3.2.4 State Handoff

Event `history-stage-b2-3-2-4-oxide-zero-event-control-20261122` binds eight files, including the synthetic controls, native input manifest, analytical reference, execution plan, pending execution request and offline results. Each tree generated a proposal against its own managed views.

| Worktree | Proposal | Startup audit | repo-state sync --safe-only |
| --- | --- | --- | --- |
| Development | `proposal-026b361a628937380170e05c` | 0 errors, 81 warnings | Exit 2. Existing evidence hash mismatch for `configs/kinetics/scientific_intake.schema.json`. |
| Publication | `proposal-d0ea6c38f37b21b55d57dc34` | 1 error, 80 warnings, including pre-existing managed module row drift | Exit 2. Existing history-compaction source changed before proposal generation. |

In both trees the actual hashes of `docs/08_HISTORICAL_RESULTS.md` and `data/state_handoff/projection_manifest.json` still matched the respective proposal's expected original hashes after synchronization. The proposed change appends the benchmark preparation result to history and updates the projection manifest. Each proposal remains pending with `approve` and `reject` available. [Existing conflicts](../stage_b1_5/handoff.md)

A separate pending request binds the zero-event native action to plan SHA-256 `2c0a012270fec9a6a11e52411c9993742fe6ffc3017db333857fbc4c2dd1b7d8`. Review of the history entry alone grants no execution permission. [Execution approval request](approval_request.json)
