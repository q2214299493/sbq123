# Stage B.1.1 · State Handoff

The immutable history event binds the completion report, both V2 schemas and the validator. Each working tree generated its own proposal from current inputs. The requested action appends the contract validation result to `docs/08_HISTORICAL_RESULTS.md` and updates `data/state_handoff/projection_manifest.json`.

| Working tree | Current proposal | Startup audit | Global safe-only sync |
| --- | --- | --- | --- |
| Development | `proposal-d4ea6b53d17617f08b6dbcd4` | 0 errors, 81 warnings | Exit 2. The historical evidence hash for `configs/kinetics/scientific_intake.schema.json` differs from the current file. |
| Publication | `proposal-61f0a2f141e29b49460f87d1` | 1 error, 80 warnings | Exit 2. The history source changed before proposal generation. The previously identified source is `docs/02_CURRENT_STATE.md`. The startup error concerns the managed `transition_state_search` module row. |

The two proposals target different versions of the history document and manifest. Each remains pending for a researcher to choose `approve` or `reject` in the corresponding checkout. Historical source conflicts still require their own review. The new event leaves both existing authority records and scientific eligibility intact.

[Completion and test scope](completion.md) · [Pre-existing conflict details](../stage_a2_6/governance.json)
