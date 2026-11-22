# V.2.2.1 Ni/Cu CATKINAS qualification

**Awaiting independent native execution approval.** The existing Scientific Intake, single-point preparation and execution gate reached `AWAITING_APPROVAL` for `nicu-v221-400k-001`. The handoff from an accepted run to V2.1 rates has been exercised with offline native-output replay. Fresh native convergence, a new native output archive and a scientific result for this run remain pending.

## Decision requested

| Field | Bound value |
| --- | --- |
| Action | `RUN_CATKINAS_SINGLE_POINT` |
| Run | `nicu-v221-400k-001` |
| Plan state SHA-256 for the execution gate | `8178e960eaaef1b2f3887b0a032e4df4bec1665bbc7220ed27adab2592e021fa` |
| SHA-256 of the exact plan file bytes | `ee1ad8dabb76fc0d68268ba0a2cd47469b4fc21216b10a688550dff4d4b9aaaa` |
| Question ID | `fa88441b9d3eac0c1513b3eed53b11f57b8c75a701dc41821fed1ce8cde2ee0a` |
| Budget | One local single point, one MATLAB invocation, 210 s wall limit, MaxTime 3 and MaxOdeTime 3, zero automatic retries |
| Executables | `D:/BaiduNetdiskDownload/bin/matlab.exe` (R2025b), SHA-256 `6dc32276086121e44edf4846f033066ba5b0fae9bad002d8917a411e0a59afa9`. `D:/CATKINAS.p` (distribution 20261106), SHA-256 `2b70a3511a19065f843b65d8601874700dd792e8d31d620046ef3805df399ff0`. Both files were hashed locally without launching them. |
| Evidence | [Execution plan](plan.json), [separate approval request](approval_request.json), [write-once waiting receipt](AWAITING_APPROVAL.json) |

Preparation used a fresh isolated synthetic H7 ticket. The host-specific run directory and ticket database in the plan must be preserved for the pending decision. The gate requires an independently supplied `mkm-execution-approval/1` decision with the reviewer's identity, exact question, allowed action, plan state hash and digest of approval evidence. Presenting the request itself to preflight raised `Explicit single-point approval required`. All eleven prepared files retained their hashes. No native process, terminal execution receipt, DRC perturbation or automatic retry occurred.

## Model and archived numerical comparison

The public V.2.1 inspection of the F1.2 Ni/Cu project/task reproduced the saved readiness document. The four-step network and all eight directional parameters qualified at 400 K and 1.6 bar. H₂, NO and HNO partial pressures were 1.0, 0.5 and 0.1 bar. The largest absolute log detailed-balance residual was 2.67 × 10⁻¹⁵ or less. The native input SHA-256 was `b793e6f37f2262e4a006f912d18950c17581ccc014aa9779008741a4e31890f8` in the model, the new plan and the accepted archive. The network and kinetic dataset versions, source-file hashes, initial coverages and both site inventories are in the plan.

The CATKINAS rate adapter independently parsed the archived MAT and convergence log, reconstructed directional mass action, checked the normalized result and reproduced the accepted V2.1 rate payload. The network-bound validator passed against the actual network file. The original receipt, rates, normalization and MAT hashes are in the [offline numerical record](offline_verification.json).

| Archived quantity | Replayed value |
| --- | --- |
| Endpoint scope | Synthetic Ni/Cu, one Ni top site and one Cu bridge site per reference pair |
| Species coverages | H₂-top 0.30710124, HNO-top 0.40121221, H₂-bridge 0.69667948 (network IDs) |
| Vacancies | Ni 0.29168655, Cu 0.30332052. Both occupied-plus-vacant residuals are zero. |
| Elementary net rates | Adsorption and transfer 81.51277016 each. Hydrogenation and desorption 163.02554032 each, events per pair per second |
| Gas source terms | H₂ −81.51277016, NO −163.02554032, HNO +163.02554032 molecules per pair per second. Element flows close for H₂ + 2 NO ⇌ 2 HNO. |
| Steady-state residual | 5.68434 × 10⁻¹⁴ against tolerance 1.63026 × 10⁻⁵ per pair per second |
| TOF and selectivity | 81.5127701616477 events per reference pair per second. HNO molar selectivity 1 within the declared single-product set. |
| Archived stable DRC | Hydrogenation 0.45025755212448043, transfer 0.040690451158404334. These values come from the existing perturbation study. |

These comparisons retain their original conditions. For a new result the parser must find successful solver convergence and termination, then independently verify the input echo, conditions, species, elementary coefficients, fluxes, site/element balances and overall extent. Changes in settings require a separate comparison. The single-point approval request does not include DRC runs.

## Operation after an independent decision

The existing `scripts.baseline_mkm.single_point execute RUN DECISION` entry point enforces the plan binding and reserves one invocation before launch. The native files remain under `RUN/runtime`. `console.log` captures both stdout and stderr. Terminal receipts include elapsed process time and the returned exit code when available, together with digests of collected output files. Timeout, nonzero exit, missing output, missing convergence and numerical validation failure retain their stage and available evidence.

After acceptance, `python -m scripts.baseline_mkm.analysis run RUN OUTPUT --options reports/multiphase/phase3_1/benchmark_normalization.json` produces the analysis report. From the prepared checkout, the following PowerShell example reads an accepted run and emits the V2.1 payload. Adding `--qualification` emits the numerical qualification record.

```powershell
$r = 'archive/v221_catkinas/nicu-v221-400k-001'
python -m scripts.baseline_mkm.rate_adapter "$r/ACCEPTED.json" --network "$r/network.json" --dataset "$r/dataset.json" --config "$r/configuration.json" --input "$r/input/INPUT_phase25.m" --normalization reports/multiphase/phase3_1/benchmark_normalization.json
```

The adapter reuses the existing approval/output integrity checks, MAT parser, result validator and V2.1 builder. Both archived receipt layouts remain supported. The simulated-process test independently checks the new run's rate binding, rejects an unaccepted run and detects alteration of a supplemental output.

## Regression and repository state

Windows offline pytest ran 14 modules with **329 passed and one explicitly gated native test skipped**. The selection covered V.2.1, F1.2, CATKINAS assembly, single-point execution authorization, result parsing and numerical analysis, V2.1 network binding, archived rate replay, DRC, isolated imports and architecture boundaries. A first test run identified a missing distribution label in the test executable fixture. The fixture was corrected. An additional run after extracting the native output inventory check had 105 passed and the same native skip. Ruff and py_compile passed on all four changed Python files. The full repository suite and Linux were not run.

The isolated worktree was created at `dd051607dead5eaa190dfdb117bb8e7095454b23`. Existing production databases and historical scientific archives were preserved. State Handoff `proposal-9eab3f8170cc45eb33cd8f12` awaits `approve` or `reject` for the [preparation history event](../../../modules/state_handoff/events/history-v2-2-1-catkinas-preparation-20261122.json). The existing module-map drift was present at startup. The separate `sync --safe-only` check returned code 2 with `state history source changed before proposal generation`. All 356 checked event/cache and selected projection files retained their membership and hashes.

## Exact changed files

```text
modules/baseline_mkm/README.md
modules/state_handoff/events/history-v2-2-1-catkinas-preparation-20261122.json
reports/workflow_development/stage_v2_2_1/AWAITING_APPROVAL.json
reports/workflow_development/stage_v2_2_1/approval_request.json
reports/workflow_development/stage_v2_2_1/completion.md
reports/workflow_development/stage_v2_2_1/offline_verification.json
reports/workflow_development/stage_v2_2_1/plan.json
scripts/baseline_mkm/drc_pair_records.py
scripts/baseline_mkm/rate_adapter.py
scripts/baseline_mkm/single_point.py
tests/test_mkm_single_point.py
```
