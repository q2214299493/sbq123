# Phase 3.2.0.2 — Cross-reaction DRC checkpoint

At 400 K the same signed TS displacement and native validation route handles two different kinetic representations in the accepted synthetic Ni/Cu network. The half-step hydrogenate DRC is **0.4502575521**, independently reproduced from net HNO production. Its change on halving the step is **0.0001831611**, within the project tolerance **0.0225128776**. The transfer half-step result is **0.0406904512**. The scope is this network, observable, pressure composition and temperature. [Cross-reaction comparison](comparison.md) · [Step-size convergence and all residuals](fine/comparison.md)

## Execution and provenance

The Phase 3.0 steady state at 81.51277016 turnovers per reference site pair per second was reused after verifying the approval, input/output hashes and scientific acceptance. The immutable network and parent dataset are identified in the [cross-reaction contract](result.json). Each derivative changes the two Gibbs barriers of hydrogenate by the same signed amount at fixed endpoints, prefactors and reaction free energy. The baseline, other elementary parameters, gas pressures, site inventories, initial coverages and solver configuration are preserved. The committed reference files from Phase 3.0 and both transfer studies were checked against commit `01f2aec2ea016e8385b9de7bf1a3faf608f8e4ca`.

| Plan | SHA-256 | Native seconds | Accepted receipt |
|---|---|---:|---|
| A+ | `e81e1393640ab29b945a3e08b2dd9bee7e3b9871f5946ca0e3e9b65c3433de88` | 147.24 | [coarse +](coarse/plus/accepted.json) |
| A− | `85e5f30c40bf38cad2025be86a47a4aec481bf1fa740e1b521c02859bede0d35` | 35.12 | [coarse −](coarse/minus/accepted.json) |
| B+ | `32930d35c859ed3c47ac7a1e58b15e81f870f2af9480da1e65dac3c8410e9101` | 127.65 | [fine +](fine/plus/accepted.json) |
| B− | `961a8680f32111e003c01330f2d5f6367359515fac1212d7a3d0a1aa9c029ac7` | 72.16 | [fine −](fine/minus/accepted.json) |

Four plan-specific human approvals were checked before starting the shared clock. A then B ran sequentially without retries. Pair wall times were 183.41 and 200.16 s of 480 s each. The shared clock recorded 383.89 s of 960 s. Each case directory contains its plan, approval and source reply, acceptance receipt, native MAT and compact log. Replaying those artifacts reproduces the accepted result hashes. [Shared completion receipt](finished.json) · [Pressure-order audit](pressure_order.md)

## Implementation and verification

- `scripts/baseline_mkm/ts_perturbation.py` resolves the selected reaction in the immutable parent, checks uniqueness, reviewed TS identity, parameter binding and Gibbs references, then reproduces the signed dataset. The existing default is transfer.
- `scripts/baseline_mkm/drc_pair.py` carries the selected ID through prepare, verify and report. `drc_cross_reaction.py` preflights four decisions and bounds both sequential pairs by one clock using the existing single-point execution gate.
- `scripts/baseline_mkm/drc_report.py` replays native forward and reverse coefficients and fluxes, binds each fine estimate to its own coarse result and compares studies on their common baseline. `configs/kinetics/mkm_cross_reaction_drc.schema.json` specifies the comparison contract.
- `tests/test_mkm_drc_cross_reaction.py` adds 24 deterministic cases for both reactions, signed displacements, ambiguous or incomplete evidence, asymmetric units, native mass action, step-size evidence, partial failure, budget and replay of all four runs. Existing tests retain coverage of blocked Fe(110), half-pair rejection and transfer compatibility. The module README records the updated capability matrix.

Both development and release trees passed **633** phase regression tests (609 previous + 24 new), with the opt-in live baseline rerun excluded. Both passed compilation, import, scoped Ruff, schema validation and four independent, byte-exact native result reconstructions. The clean full suite recorded 2194 passed, 5 known historical failures and 1 deselected (15 warnings). The repository-wide all-green criterion remains open; the scientific checkpoint and its phase regressions are verified. [Test evidence](test_report.md)

## Next phase

Proceed to design and test a bounded Phase 3.2.1 batch DRC pilot on this synthetic network. Retain plan-specific authorization, aggregate time budgets, first-failure stop and accepted-result reuse. The two studies support that development step. Larger batches, real catalyst rate rankings and missing Fe(110) kinetic evidence remain unvalidated. No batch, real Fe calculation, production database update or changes to VASP/NEB/DIMER execution were part of this checkpoint.
