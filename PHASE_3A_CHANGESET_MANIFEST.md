# Phase 3A Changeset Manifest

Date: 2026-07-27
Scope: endpoint pre-refactor audit, behavior freeze, and planning only

This additive manifest does not replace Review Baseline v3 or any historical
baseline. It intentionally does not hash itself.

## Frozen production and configuration inputs

| SHA-256 | Bytes | Path | Phase 3A action |
|---|---:|---|---|
| `db07eea4541cfdb414cc8957a50dd14b5881264c5310d20df7f6900c28ddc1da` | 6015 | `modules/ts_endpoint_generator.py` | read-only |
| `b0bc707a97c3a032bd5d7d610cb96a961034e17ad763cc1ccb3e7d645f808882` | 18639 | `modules/ts_endpoint_validator.py` | read-only |
| `f68fbb78a7e5f4926cb0531a5b4b0e38211fc839bd8304f1ad96d846651749b5` | 9668 | `modules/structure_purpose_manager.py` | read-only |
| `8145e739bf80b0eee5e017a28b3caf4e0dac9310b85090f60d6bcef77208a702` | 7763 | `modules/ts_endpoint_database.py` | read-only |
| `a4bc47e51e21a612e067b8a4fd123703db3da207219c3ebc7a28f16164ad5315` | 441 | `configs/structure_purpose_routing.yaml` | read-only |
| `43427e5bd1a7950d7ee6defc0ce43c14c80b37b04175ee790fba1f61c629fe88` | 300 | `configs/ts_connectivity_gate.yaml` | read-only |

## Test changes

| Before SHA-256 | After SHA-256 | After bytes | Path | Change |
|---|---|---:|---|---|
| not present | `eb02490f8da047e6c5bd2abfe2e6fc32644deba37b3300bb4b6e2139ae8d7615` | 26256 | `tests/test_ts_endpoint_contracts.py` | 17 endpoint API/behavior/database-boundary contract tests |
| `f3b7b2a78e1f0bc84a5d46b9982ee94334018f277b253c908428657ece286398` | `50925073645d14e44378c6383f7fa20a4b339e465be0b44ce350c3370572eee8` | 18772 | `tests/test_repository_contracts.py` | admit exact v3 layout and verify its five bindings |

`tests/test_structure_purpose_manager.py` was not modified. Its tests that
execute the blocked migration were not run.

## Additive baseline and reports

| SHA-256 | Bytes | Path |
|---|---:|---|
| `3e395bac41f647ddd9b8f7b2887c7554f9f8647aa513581c642c0219b0099307` | 702 | `artifacts/review_baseline_v3/baseline_v3_sha256.txt` |
| `0726c986fa35e2ab847f3efb92f1fe5cdb9f64af4b023c1b13669c41030ec6ab` | 2287 | `REVIEW_BASELINE_V3.md` |
| `5b72a46e653e4c88b61cd7ffc4dd2da5d2c9dca684c1e62410aed897329d31ee` | 10248 | `TS_ENDPOINT_API_CONTRACT.md` |
| `42cfa74f65efaeda4197bb876653bd487015622c6051c51d544df818c59b324e` | 7991 | `TS_ENDPOINT_CURRENT_ARCHITECTURE.md` |
| `bc94eeafb5bb190f0825632e2713d9a2e543ca570509288707b5161e4acf82fe` | 6865 | `TS_ENDPOINT_BEHAVIOR_BASELINE.md` |
| `1bbad8e93f63899b400bad798f2ad023c7eb86ca863acfee18570b69a209918e` | 4867 | `PHASE_3B_IMPLEMENTATION_PLAN.md` |
| `6951ebde995d4221fe0baefc140213403915a87b2f7f799614809665d107e2e2` | 7661 | `PHASE_3A_REPORT.md` |

The five individual v3 artifact files are transitively bound by
`baseline_v3_sha256.txt`. No calculation, runtime, database, SQL migration,
scheduler, submission, SSH, LSF, execution-gate, or NEB path-quality file is
included.
