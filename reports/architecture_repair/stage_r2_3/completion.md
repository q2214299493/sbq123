# R.2.3 completion — Zacros input spelling and native test authorization

The synthetic oxide control now emits finite Zacros R8 tokens and enforces integer types on integer controls. The corrected [five-file bundle and manifest](native/input_manifest.json) is an offline artifact. Ordinary pytest replays native evidence. Its sole live CATKINAS benchmark requires an explicit command-line selection and an external decision for an already prepared plan. Dynamic Ni/Cu Zacros replay has no matching plan-bound execution gate in this repository, so the eight cases use their archived outputs.

## Baseline and evidence preservation

The repair started directly at `0e36efa0f1bc75055a394c5f235b4956e9a3c77f`, the verified remote head of `codex/stage-r2-2-safe-only`. Production `codex/multiphase-phase0-integration` was at `dd3a5cbbd180c97fe09a0554a6ef2a845ef95f73`. Both production and R.2.1 `5fb520a6eb5d4161949edef78bd3b86ce0585c05` are ancestors of the baseline. R.2.2 implementation `977968c75a310eb4b3881184b007ef1c48b580b4` is its direct parent. The isolated development and publication worktrees tested implementation `3b9360b9986197c3a219ff7236dbfe3abcb66e89`. The desktop development tree's 242 tracked modifications, three deletions and 1,100 untracked entries were left in place.

The entire historical `reports/multiphase` tree retains Git tree ID `150e0850364fda4307b0cda10966f070c1c3eba5`. This covers the Ni/Cu archives, oxide inputs, plan, decision, one-use claim, failed native receipt and raw output. Historical receipt tests independently check the source, executable identity, archive members, plan bindings and the single consumed launch.

| Historical artifact | SHA-256 |
| --- | --- |
| Zero-event execution plan | `2c0a012270fec9a6a11e52411c9993742fe6ffc3017db333857fbc4c2dd1b7d8` |
| Native execution approval | `8ab9ff958de76f25055bf6a6d40b98cc3aee385728b35770d04927010e0d6108` |
| Consumed claim | `3e92050bcf94d08c999c6e0296b8e5bec11644426a069020eac4b3993287f699` |
| Failed execution receipt | `fdf1fa59f76a8e09c6ecea6aee48f1dadacf0ce513d979936e08f2fbb5a6ae16` |

## R1-002 — cause, reproduction and corrected bytes

The old renderer validated the converted float with `finite_number`, discarded it and interpolated the original JSON value. Python accepted integer `400` numerically and wrote `temperature 400`. Baseline offline reconstruction reproduced the historical input bytes. In the raw native archive, Zacros 4.0 reported error 1002 at simulation input line 2, printed abnormal termination and exited with code 0. Subsequent readers and the event loop were never reached.

The installed distribution ZIP was inspected as data. Its SHA-256 is `55ae665d845ad1120241b98e0a72192bb3737ade801275ec13c06d81fae9abae`. The simulation parser at lines 1656–1663 requires `AA/R8` for temperature. The real recognizer at lines 186–265 and R8 dispatch at lines 352–358 in `parser_module.F90` require a decimal point or an exponent marker. The parser member hashes to `8f6019e33ace873e78fe4c835edbc07e10c22be41299fdbb55bfb993623acff5`. The regression oracle checks the decimal/exponent subset produced by Python and independently compares decimal values.

| Control in a real-valued field | Before | After |
| --- | --- | --- |
| JSON `400` | Bare `400` | `400.0` |
| JSON `400.0`, `400.000` | `400.0` | `400.0` |
| JSON `1e-5` | `1e-05` | `1e-05` |
| JSON `1e13` | `10000000000000.0` | `10000000000000.0` |
| Integer literal `10000000000000` in the archived prefactor | Bare integer | `10000000000000.0` |
| String (including numeric strings), bool, null, list, NaN or signed infinity | Rejected | Rejected |
| Integer that loses precision on conversion to binary64 (e.g. 2^53+1) | Original integer emitted after rounded range check | Rejected before publication |
| Floats equal to an integer execution setting or gas stoichiometry | Python equality could accept them | Rejected; integer graph multiplicity also remains strictly typed |

The corrected writer uses the validated float and guards integer-to-real precision loss. The scientific values, unit checks, fixed budgets, topology and gas direction are unchanged. A new destination is mandatory; a second CLI publication to the same path fails and leaves every byte intact.

| File | Exact delta |
| --- | --- |
| `simulation_input.dat` | Four real tokens: temperature, pressure, gas reference energy and mole fraction. SHA-256 changed from `4e2936fe930c1ed30b0b4301e515f5e5ee4155184776a649a28a03b48f447b27` to `dd9978438bb52098a808378df00ecf458788fba2cad4f5b1abe7c2a347af7689`. |
| `mechanism_input.dat` | Two prefactors gained a decimal point. New SHA-256 `ff5b3bceeb55554eb9387eb46e89138225c6a22f99c3eae8c53e700c82d9442c`. |
| `energetics_input.dat` | Two zero-valued cluster energies gained a decimal point. New SHA-256 `e1fb080c2dea34013c5d9ce8355037fb1fe143a06fcd9a7ad8614b653c9673c1`. |
| `lattice_input.dat`, `state_input.dat` | Identical bytes and hashes. |
| `input_manifest.json` | Historical SHA-256 `023b40ad208b77a8028d9e03e2131fdc53bd34c2f88f09cdcf2fe19c39f0c285`. Corrected SHA-256 `f475a45a53d91ee3f6a9b5c2277ac0a364d8909381c53227e3ee8e04d721d3d6`. |

## R1-007 — execution authorization

The former Zacros pytest path accepted an inherited executable and compared its digest before direct subprocess dispatch. It had no approved plan for those dynamic cases. The CATKINAS test previously generated its own approval from an environment-provided source. The repaired tests keep execution authority in the existing engine gates. The CI workflow invokes ordinary pytest; the `native_execution` marker is a classification only.

| Attempt | Verified outcome |
| --- | --- |
| Default suite, inherited legacy Zacros executable, MKM approval-source and run-root variables | Eight archived Ni/Cu cases run offline. CATKINAS live test skips before reading a run or decision. |
| Inherited `PYTEST_ADDOPTS` supplies the new CATKINAS option | Still skips. Literal command-line opt-in is required. The subprocess regression supplies inert paths. |
| Explicit benchmark selection with a prepared fixture and a denied decision | Existing single-point gate refuses. Neither READY claim nor runtime directory exists. |
| Wrong action, plan hash, source digest, question, run directory, ticket, changed configuration or runtime identity | Existing owner refuses before dispatch. No test-generated decision enters the live benchmark. |
| Matching CATKINAS fixture decision, plan and tool identity | Existing positive preflight succeeds with inert fixture tools; replay tests use mocked execution. |
| Corrected Zacros bundle against the old execution approval | Existing gate rejects the stale plan hash. Changing the binary, a member, budget or bound evidence also blocks preparation. |
| New temporary preparation with the corrected members | Existing zero-event gate verified the actual installed executable by reading its SHA-256 (`84a8f88d6df633eeea9eeac8aa9227237cdf2564a4dc72e0cab8a18c4ce119d2`) and returned `pending` with an empty allowed-action list. The temporary plan was discarded. A separate positive test checks an exact decision with fixture identities only. |

The repaired CATKINAS benchmark takes an existing RUN and DECISION via `--catkinas-reviewed-run RUN DECISION`, checks the benchmark input bytes, and delegates to `single_point.execute`. The owner revalidates the ticket, reviewed plan, sources, MATLAB/CATKINAS hashes, staged input and atomic execution claim. The oxide gate remains limited to zero-event initialization. No native benchmark approval or replacement execution plan is published here.

## Regression scope

The original baseline passed **818** focused tests with all nine live cases explicitly deselected before dispatch. Development and publication each passed **850** focused tests (83.10 s and 88.31 s, respectively); the single skipped test was the live CATKINAS benchmark without explicit authorization. The selection includes the 509-test R.2.1 contract/adapter group and all 185 State Manager/State Handoff/Registry cases from R.2.2. Both worktrees passed py_compile and Ruff on all five changed Python files. Prior focused test failures: none.

The 29 test modules are listed below for reproduction with `python -m pytest -o addopts= -q -rs`. Each name is a file under `tests/` with prefix `test_` and suffix `.py`.

- State/Registry: `state_manager`, `b4_state_governance`, `state_log_projection`, `state_sync_repository_items`, `state_sync_task_ownership`, `state_sync_safe_only`, `registry_schema`, `registry_write`, `registry_excel_promotion`, `b4_registry_governance`.
- Contracts/adapters: `rate_network_binding`, `rate_output_v2`, `rate_dimensions`, `native_rate_adapters`, `b1_contract_acceptance`, `b1_native_acceptance`, `kinetic_parameters`, `reaction_network`, `stoichiometric_sources`, `multiphase_contracts`, `interphase_transfer`, `cross_phase_elementary`.
- Serialization/gates/archive: `zacros_zero_event_control`, `zacros_zero_event_native_receipt`, `native_advanced`, `mkm_single_point`, `native_model`, `zacros_bridge_input`, `catkinas_closed_cycle`.

Validation was offline on Windows. New native reader acceptance and the full repository suite were not tested. No scientific calculations or production SQLite writes were performed. The real repository's existing history-compaction source mismatch still makes strict safe-only preview exit 2, without mutating the inspected files. End audit still flags `transition_state_search` module-map drift.

## Exact changed files relative to the repair baseline

- `modules/baseline_mkm/README.md`
- `modules/state_handoff/events/history-stage-r2-3-zacros-native-safety-20261122.json`
- `modules/surface_kmc/README.md`
- `pyproject.toml`
- `reports/architecture_repair/stage_r2_3/.gitattributes`
- `reports/architecture_repair/stage_r2_3/completion.md`
- `reports/architecture_repair/stage_r2_3/native/energetics_input.dat`
- `reports/architecture_repair/stage_r2_3/native/input_manifest.json`
- `reports/architecture_repair/stage_r2_3/native/lattice_input.dat`
- `reports/architecture_repair/stage_r2_3/native/mechanism_input.dat`
- `reports/architecture_repair/stage_r2_3/native/simulation_input.dat`
- `reports/architecture_repair/stage_r2_3/native/state_input.dat`
- `scripts/surface_kmc/oxide_control.py`
- `tests/conftest.py`
- `tests/test_mkm_single_point.py`
- `tests/test_native_advanced.py`
- `tests/test_zacros_zero_event_control.py`

The new history event proposes recording this software repair. Its State Handoff review is independent of native execution authority.
