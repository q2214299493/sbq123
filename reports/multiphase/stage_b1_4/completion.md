# Stage B.1.4 · CATKINAS and Zacros native result adapters

Ten cost-free archive replays produced strictly validated `kinetic-rate-output/2` revision `2.1.0` records. Both adapters return their V2 output and a qualification report. The latter retains native coverage, residual, lattice and statistical details which have no field in the strict schema. The original V1/V2 readers, both native solvers and the execution gates retain their existing entry points. Each derived output carries its own identity, run binding and unreviewed status.

## Evidence and bindings

The publication baseline was `d96f9752579468565cfa7a499de44b870c714ae9`. The development tree remained on its own branch at `233d5a6c589560094a0e942b6d48708b1fd5a847`. The audit inspected MAT field dimensions and receipt hashes for all 24 portable multiphase MAT files, the contents and output hashes of all eight Zacros benchmark ZIPs, and the earlier smoke receipt. Two MAT bindings serve as diagnostics for pressure handling. They do not qualify new rates. The closed-cycle MAT files are from separate runs and have distinct raw file digests. A failed CATKINAS standalone attempt has no converged point to convert. [Pre-implementation availability matrix](evidence_availability.md) · [Member and receipt inventory](evidence_inventory.json)

The public kinetic-interface network supplies the ordinary Zacros cases. The archived bidentate and absorbing models identify two distinct network versions. The existing synthetic fixture builder `tests/test_kinetic_parameters.py::case` reproduces these with `gas=True` and `gas="dissociative", reversible=False`, respectively. The stored network files are deterministic rematerializations. Their canonical network digests match the versions carried by the original archived datasets. Their raw file digests identify these new serializations. The adapters require a supplied network, verify its canonical version, and compare reaction stoichiometry and parameter IDs to the bound dataset.

## CATKINAS benchmark and units

| Derived observable at 400 K | Phase 2.5.2 | Phase 3.0 |
| --- | ---: | ---: |
| Overall turnover per reference site pair per second | 81.5127701616477 | 81.5127701616477 |
| HNO molecules produced per reference pair per second | 163.0255403232954 | 163.0255403232954 |
| Mean turnover per individual modeled site per second | 40.75638508082385 | 40.75638508082385 |
| Net Ni-top and Cu-bridge vacancy sources per pair per second | 0 each | 0 each |

MAT values supply both coefficients, both fluxes and signed progress for each step. For adsorption the observed forward coefficient is 1062.5334512545078 bar⁻¹ s⁻¹ and the reverse is 58.39820737222975 s⁻¹. The native engine reports version 20230524. Distribution label 20261106 and the executable digest retain separate provenance. Both inputs bind 400 K, 1.6 bar total pressure and one Ni-top plus one Cu-bridge per reference pair. The source projection uses that native pair denominator throughout. The site average is a separately labeled diagnostic. Both reports retain the native arbitrary-precision residual text as well as the independently reconstructed floating-point residual. [Phase 2.5.2 output](replay/catkinas-phase2_5_2.json) · [Phase 3.0 output](replay/catkinas-phase3_0.json) · [CATKINAS qualification](catkinas_qualification.json)

## Zacros benchmark and statistical limits

All eight receipts describe synthetic Zacros 4.0 runs. The case key, selected seed 13201, native file hashes, exact lattice, matching multiplicity and model-specific state definitions bind each observation. Counter differences are divided by measured elapsed physical time on the whole simulation cell. The eighteen modeled sites are retained as lattice metadata.

| Archive | Sampled event interval | Forward events | Reverse events | Window net progress, events per simulated lattice per second |
| --- | --- | ---: | ---: | ---: |
| mono | 0–19 | 13 | 6 | 528.440143 |
| dent | 0–19 | 13 | 6 | 334.105613 |
| full | 0–19 | 8 | 11 | −128.804839 |
| interacting | 0–19 | 8 | 11 | −383.432480 |
| attractive | 0–8 | 8 | excluded | 1295.760083 |
| continuous | 0–19 | 13 | 6 | 211.395331 |
| split | 0–7 | 6 | 1 | 3314.728205 |
| resume | 8–19 | 6 | 5 | 32.260553 |

The resumed process and species tables lack headers. Their assignments come from the hash-verified checkpoint writer. The sampled interval starts at 0.0021157056693776517 s and ends at 0.03311331418725626 s. Its 11 events exclude the eight already counted at its first sample. The terminal receipt reports event 20. The unsampled tail contributes no rate estimate. The attractive case ends its physical window at event 8. Its terminal clock sentinel remains explicitly unavailable as a physical duration. The Phase 2.5 smoke receipt independently matches the continuous archive's lattice, process-statistics and species-number bytes by SHA-256. It provides an additional observation binding and supplies no independent replicate for uncertainty estimation. [Zacros qualification and sample windows](zacros_qualification.json)

Matched population changes agree with the stoichiometric projection. Every window supplies a finite transient observation. A stationary regime, independent repeats and a statistical uncertainty estimate remain unverified for all eight cases. When an applicable process series or positive time interval is missing, its rate and dependent source terms are null. An explicitly excluded direction stays `not_applicable`. A corrupt hash-bound member fails verification. Comparing whole-lattice KMC window rates to pair-normalized mean-field turnover would require a compatible physical denominator, reaction definitions, conditions and observables.

## Verification on Windows

| Final check | Development | Publication |
| --- | ---: | ---: |
| New adapter regressions, including both CLIs, qualification and deterministic replay | 24 passed | 24 passed |
| Previous V1/V2, units, stoichiometric sources, kinetics, native input, MKM, historical DRC and architecture/release regressions | 478 passed | 478 passed |
| **Combined focused run** | **502 passed, 0 failed in 32.42 s** | **502 passed, 0 failed in 31.92 s** |
| py_compile and Ruff on all five task Python files | Passed | Passed |

Each run deselected one live CATKINAS case and eight native Zacros cases. These are focused test results. The full repository suite was outside this checkpoint. Replaying each archive twice checked output and qualification equality. The V2 output bytes also matched their published replay snapshots. Integrity tests covered changed files, wrong networks, missing declared archive members, counter regressions and partial observations. Eighty-three original archive, diagnostic and contract files in both trees matched the published baseline byte-for-byte. No solver, production SQLite database or historical evidence was modified.

## Exact changed files

- `modules/kinetic_data/multiphase_contracts.md`
- `modules/kinetic_data/native_result_adapters.md`
- `modules/state_handoff/events/history-stage-b1-4-native-rate-adapters-20261121.json`
- `reports/multiphase/stage_b1_4/catkinas_qualification.json`
- `reports/multiphase/stage_b1_4/completion.md`
- `reports/multiphase/stage_b1_4/evidence_availability.md`
- `reports/multiphase/stage_b1_4/evidence_inventory.json`
- `reports/multiphase/stage_b1_4/handoff.md`
- `reports/multiphase/stage_b1_4/networks/attractive.json`
- `reports/multiphase/stage_b1_4/networks/dent.json`
- `reports/multiphase/stage_b1_4/replay/catkinas-phase2_5_2.json`
- `reports/multiphase/stage_b1_4/replay/catkinas-phase3_0.json`
- `reports/multiphase/stage_b1_4/replay/zacros-attractive.json`
- `reports/multiphase/stage_b1_4/replay/zacros-continuous.json`
- `reports/multiphase/stage_b1_4/replay/zacros-dent.json`
- `reports/multiphase/stage_b1_4/replay/zacros-full.json`
- `reports/multiphase/stage_b1_4/replay/zacros-interacting.json`
- `reports/multiphase/stage_b1_4/replay/zacros-mono.json`
- `reports/multiphase/stage_b1_4/replay/zacros-resume.json`
- `reports/multiphase/stage_b1_4/replay/zacros-split.json`
- `reports/multiphase/stage_b1_4/zacros_qualification.json`
- `scripts/baseline_mkm/rate_adapter.py`
- `scripts/kinetic_data/native_rate_output.py`
- `scripts/surface_kmc/rate_adapter.py`
- `scripts/surface_kmc/trajectory_statistics.py`
- `tests/test_native_rate_adapters.py`

[Commands and supported receipt formats](../../../modules/kinetic_data/native_result_adapters.md) · [Pending State Handoff decisions](handoff.md)
