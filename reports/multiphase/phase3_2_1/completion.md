# Phase 3.2.1 bounded batch DRC pilot

The four-step synthetic Ni/Cu network at 400 K yielded four accepted fine-step DRC estimates. Transfer and hydrogenate reuse both of their earlier step sizes. Adsorption and desorption each supplied one newly approved ±0.005 eV pair. The common positive net baseline was 81.51277016 turnovers per reference Ni-top/Cu-bridge site pair per second.

| Reaction ID | Origin | +0.005 eV TOF | −0.005 eV TOF | Central DRC | Positive / negative one-sided DRC | Stability |
|---|---|---:|---:|---:|---|---|
| ads | New | 78.73448981 | 84.17409496 | 0.23027551 | 0.23906822 / 0.22148281 | Second step size missing |
| transfer | Reused | 80.99801594 | 81.95984947 | 0.04069045 | 0.04367290 / 0.03770800 | Stable |
| hydrogenate | Reused | 76.19477340 | 86.82706813 | 0.45025755 | 0.46510731 / 0.43540780 | Stable |
| desorb | New | 78.10978110 | 84.70550389 | 0.27942666 | 0.29398487 / 0.26486845 | Second step size missing |

Among the stable estimates the ranking is **hydrogenate**, then **transfer**. Their published coarse-step estimates were 0.45044071 and 0.04113191 respectively. All four estimates lie in [0,1] without clipping. The one-sided gaps quantify observed finite-step asymmetry; no statistical error bar is assigned. The ranking is limited to the supported subset of this synthetic benchmark. [Reaction-level results, signed coverage, utilization and flux changes](network_report.md) · [Numerical evidence and provenance](result.json)

## Execution and scientific checks

The four plan-specific approvals were preflighted together before launching the first member. Native times were 138.71, 29.70, 148.45 and 91.67 s in execution order. Native time used **408.54 of 840 s**. The batch used **409.56 of 960 s** wall time. All four invocations were sequential, each completed below 210 s, and no retry occurred. Historical native executions are excluded from this count. Reopening the completed batch with the native launch method disabled verified every member and returned its original completion receipt. [Approval plan](approval_plan.md) · [Approval index](approvals.json) · [Batch clock](finished.json)

Both directional coefficients in each new pair scaled by the expected Boltzmann factor for its signed TS shift. Reaction Gibbs energy, electronic energies, prefactors, pressure orders, other reactions, starting coverages and solver settings were preserved. Native partial pressures and surface activities reconstruct directional fluxes. Independent replay of net HNO production divided by 2 recovers both new DRC values. Across the four fine-step pairs, maximum absolute site and H/N/O elemental residuals were zero, surface steady-state residual was at most 8.53 × 10⁻¹⁴ and native log detailed-balance residual was at most 3.35 × 10⁻⁶ (limit 10⁻⁴). [Rate-law review](kinetic_review.json) · [Adsorption evidence](pair-1/pair-result.json) · [Desorption evidence](pair-2/pair-result.json)

Ninety-three historical reference files were checked against release commit `05c4ce6ed2964415bae92ca655de669ce8bbc6aa`. Both working trees independently reconstructed all four signed datasets, configurations and native inputs, verified the MAT, approvals and input hashes, and reproduced each normalized result hash.

## Missing evidence and next phase

All four synthetic reactions are eligible. Ads and desorb lack a second accepted step for the project convergence criterion. No further perturbations were submitted. Real Fe(110) was excluded by the planner with null DRC and zero planned runs. It lacks endpoint Gibbs corrections, confirmed site and charge balances, confirmed reversibility and scoped kinetic parameters. [Fe(110) missing-evidence record](fe110_exclusion.json)

The general planner supports a read-only eligibility scan, hash-bound reuse and per-reaction missing data. The orchestrator reuses the existing signed pair, single-point gate and campaign clock. The batch result contract distinguishes sampled, stable and unavailable values. The production database, original calculation files and VASP/NEB/DIMER execution mechanisms were untouched. [Implementation and use](../../../modules/baseline_mkm/README.md) · [Validation record](test_report.md)

The bounded synthetic engine is ready for separately scoped Phase 3.2.2 development. Any claim of a four-reaction **stable** ranking requires a separately approved second step for ads and desorb. Neither reaction-order scans nor MLIP/DFT priority automation were started.
