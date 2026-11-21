# Stage B.1.1 · Existing V2 contract audit and hardening

The existing V2 validator and both schemas now preserve missing directional fluxes, explicitly excluded directions, known zeroes and independently measured net progress. Source totals inherit missing data only from reactions that change the species or inventory. A typed denominator can identify the site's inventory and distinguish a single site from a pair. An optional complete output binding identifies the output dataset, run and hashed native inputs separately from the upstream parameter dataset version.

The initial numeric V2 fixture and old V1 fixture both remain readable. Earlier V2 records lacking a typed denominator or run binding retain their declared rates. Physical conversion and cross-run identification require additional evidence. Original 2.0.0 readers can reject the additive representations. See the [field, caller and issue audit](audit.md) for compatibility in each direction.

The archived Ni/Cu overall turnover is 81.5127701616477 per reference pair per second. The average over the two modeled individual sites is 40.75638508082385 per second. The input manifest, separate inventory balances, two MAT files and Phase 3.1 normalization establish this model-specific interpretation. Physical area, mass and reactor-volume conversions remain unavailable. [Evidence, equations and hashes](reference_site.md)

## Verification

Development and publication were tested independently on Windows. The development checkout retains its separate history and local modifications. The publication parent is `49ca89afae5d44f06acda41987d2422a822167db`.

| Check | Development | Publication |
| --- | ---: | ---: |
| Pre-change V1 and V2 contract tests | 132 passed | 132 passed |
| V1 multiphase contract, post-change | 76 passed | 76 passed |
| V2 rate output, including 35 new cases | 91 passed | 91 passed |
| Kinetic parameter units, laws and export | 35 passed | 35 passed |
| Native model assembly and readback | 32 passed | 32 passed |
| Advanced native model/archive tests, offline selection | 23 passed | 23 passed |
| CATKINAS MAT reader and malformed input | 10 passed | 10 passed |
| Archived Phase 3.0 result replay | 1 passed | 1 passed |
| **Main post-change selection** | **268 passed in 13.38 s** | **268 passed in 13.36 s** |
| Historical Zacros output parser, separate package | 1 passed | 1 passed |
| Python compilation, Ruff, MKM/KMC adapter imports | Passed | Passed |
| Reader subprocesses, actual exits for six cases | 0, 0, 0, 1, 1, 1 | 0, 0, 0, 1, 1, 1 |

In order, the subprocess checks used V1 reading its fixture, V2 reading its old numeric fixture, V2 reading explicit unknown rates, V2 rejecting an unsubstantiated zero net, V2 rejecting a V1 bundle and V1 rejecting V2. The original B.1.1 event's evidence hashes reproduce against its published Git tree `6b287c92`. All 31 files in the evidence/legacy comparison matched the pre-change state in both trees and the Git baseline byte-for-byte. The comparison covers the two complete tracked benchmark report directories, the archived Phase 3.1 closed-cycle analysis directory, five V1 kinetic schemas, the V1 reader and the original V2 fixture.

The main selection used the following pytest inputs with `-k 'not test_native_zacros_replay'`. Eight live Zacros parametrizations were explicitly deselected in each tree. This was a focused suite. Validation used existing archives, fixtures and temporary files, with no native engine run or production SQLite write.

```text
tests/test_multiphase_contracts.py
tests/test_rate_output_v2.py
tests/test_kinetic_parameters.py
tests/test_native_model.py
tests/test_native_advanced.py
tests/test_catkinas_closed_cycle.py::test_single_point_reader_cli_and_archived_observation
tests/test_catkinas_closed_cycle.py::test_result_reader_rejects_malformed_native_output
tests/test_mkm_single_point.py::test_published_native_result_replays
```

The archived VASP2Kinetics package separately ran `tests/test_result_parser.py::SimulationResultParserTests::test_normal_zacros_result`. The additional adapter import check loaded both native renderers and the CATKINAS single-point reader.

## Exact changed files

- `configs/kinetics/rate_output_v2.schema.json`
- `configs/kinetics/rate_source_terms_v2.schema.json`
- `scripts/rate_output_v2.py`
- `tests/test_rate_output_v2.py`
- `modules/kinetic_data/multiphase_contracts.md`
- `reports/multiphase/stage_b1_1_audit/audit.md`
- `reports/multiphase/stage_b1_1_audit/reference_site.md`
- `reports/multiphase/stage_b1_1_audit/completion.md`
- `modules/state_handoff/events/history-stage-b1-1-existing-rate-contract-audit-20261121.json`

## State Handoff

Both proposals append this audit to the historical results view and update its projection manifest. Each remains pending for `approve` or `reject` in its own tree.

| Working tree | Actual proposal ID | Global safe-only sync |
| --- | --- | --- |
| Development | `proposal-f797dd224be8597c9e0b82e3` | Exit 2. An older event's scientific intake schema hash differs from the current file. |
| Publication | `proposal-efd096c3ddc74239759b72af` | Exit 2. The history source changed before proposal generation. |

The startup audit found 0 errors / 81 warnings in development and 1 error / 80 warnings in publication. The publication error identifies the existing managed transition-state module row. Historical event hashes and approvals were preserved. No later checkpoint was started.
