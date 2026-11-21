# Stage B.1.2 · State Handoff

The immutable history event binds the completion report, dimensional schema and usage guide. Each working tree proposed appending this stage to `docs/08_HISTORICAL_RESULTS.md` and updating `data/state_handoff/projection_manifest.json` against its current state.

| Working tree | Current proposal | Global safe-only sync |
| --- | --- | --- |
| Development | `proposal-89d1b6fe49d5a61934ddec0f` | Exit 2. An existing event binds an earlier hash for `configs/kinetics/scientific_intake.schema.json`. |
| Publication | `proposal-cc61d1356bcf67e933970fbf` | Exit 2. A historical state source changed before proposal generation. |

Both proposals are pending. The choices in each corresponding tree are `approve` and `reject`. The startup audit recorded 0 errors / 81 warnings in development and 1 error / 80 warnings in publication. The publication startup error concerned the existing managed transition-state module row. No existing proposal, approval or historical hash was rewritten. [Completion report](completion.md)
