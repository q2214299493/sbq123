# Phase 3.2.2 partial validation

**The intermediate sensitivity passed. The native gas-order pilot stopped at its first rejected run. Phase 3.2.2 does not meet its completion criteria.** Four HNO-top runs were accepted, one NO run was rejected and three approved NO runs never started. All eight decisions and immutable plans are retained. The original accepted 400 K baseline supplied the net TOF of 81.51277016 per reference Ni/Cu site pair per second.

## Intermediate formation Gibbs sensitivity

Raising the reviewed HNO-top Gibbs energy (baseline −0.140 eV) raises net turnover for this synthetic model. The shared intermediate participates in hydrogenation and desorption. Both reaction Gibbs energies and the corresponding forward or reverse barriers were updated with their absolute transition-state energies held at 0.740 and 0.660 eV respectively. The derivative uses positive kBT times the log-TOF slope per eV.

| Step (eV) | Raised TOF | Lowered TOF | Central | Positive side | Negative side |
|---|---:|---:|---:|---:|---:|
| ±0.010 | 90.6738723 | 71.8149381 | 0.401872339 | 0.367131318 | 0.436613361 |
| ±0.005 | 86.1815930 | 76.7084365 | 0.401377874 | 0.383967132 | 0.418788617 |

The change of 0.000494465 satisfies the project threshold of 0.020068894. For the fine positive and negative displacements, HNO-top coverage changed by −0.03429689 and +0.03529234, H2-top by +0.01758990 and −0.01810044, and H2-bridge by zero. The largest absolute native log detailed-balance residual across these four runs was 3.67426e−6. Maximum steady-state residual was 5.68435e−14. Both site inventory residuals and the H/N/O balance residuals were zero. [All signed energies, coverages, vacancies and fluxes](result.json)

## First failure and feed reconstruction

The user selected a fixed-total composition response at 1.600 bar with H₂:HNO = 10:1 in the remaining gas. NO has an elementary order of one in forward hydrogenation and zero in its reverse law. The other three steps have zero explicit NO order. The overall local NO composition order and its step stability remain unavailable. A fixed-other-pressure order is a separate experiment outside the validated symmetric pressure window at this baseline.

| Gas | Signed input (bar) | Native MAT (bar) | Independently recovered from flux (bar) |
|---|---:|---:|---:|
| H₂ | 0.9814496480943691 | 0.98145 | 0.98145 |
| HNO | 0.09814496480943691 | 0.098145 | 0.098145 |
| NO | 0.5204053870961941 | 0.52041 | 0.52041 |
| Total | 1.600000 | 1.600005 | 1.600005 |

The signed feed reached the native input and the echoed frozen-pressure settings. The MAT parameter vector and independent directional fluxes agree on the rounded pressures actually used. Dividing adsorption's forward flux by its coefficient and two vacancies gives H₂ pressure. Dividing hydrogenation's forward flux by its coefficient and H2-top coverage gives NO pressure. Dividing desorption's reverse flux by its coefficient and the Ni-top vacancy gives HNO pressure. The solver converged, but this feed exceeds the reviewed 1.600000 bar boundary. Validation rejected the run, and the campaign stopped. [Rejection](gas_order-coarse/plus/rejected.json) · [Pressure reconstruction and native hashes](gas_order-coarse/plus/pressure_diagnostic.json)

## Budget and evidence

Eight plans had separate human decisions. There were five sequential launches, zero retries and no unperturbed rerun. Native durations in order were 126.84, 87.78, 40.25, 23.79 and 21.58 s. Total native time was 300.23 s of 1680 s. Elapsed time from the study start receipt to rejection was 301.72 s of 1920 s. The study has no successful finish receipt. All 16 accepted native output hashes were checked locally. The rejected member has distinct raw hashes, timestamps, MAT data and a log extract. [Plans](study.json) · [Approvals](approvals.json) · [Comparison](comparison.md)

Both development and independent release worktrees reproduced all four accepted result files byte for byte from the native MAT and log extracts, validated both schemas, and independently recovered the two derivatives from net HNO production divided by two. Both reproduced the rejected feed and confirmed null estimates for both gas pairs. The four sensitivity and DRC test files passed again in both worktrees (137 cases per tree). Each broader phase regression passed 702 cases with one live test deselected. Full clean-checkout regression passed 2263, retained five known historical failures, and deselected one live test. Earlier evidence matched 140 reference files and all 12 prior TS DRC datasets. [Test logs and historical debt](test_report.md)

The scoped implementation adds two derivative builders, intermediate eligibility and pressure qualification, paired study coordination and reporting, two schemas, 43 deterministic tests and module documentation. It reuses the existing execution gate. Fixed-other-pressure and fixed-total feed construction have deterministic coverage. Native validation at this checkpoint covers HNO-top intermediate sensitivity. Real Fe(110) still lacks compatible endpoint Gibbs corrections, confirmed site balance and reversibility, and reviewed kinetic parameters. Its reported sensitivities remain null. [Missing evidence](eligibility.json)

## Next decision

A possible replacement gas-only study would use an explicitly reviewed pressure grid. The following offline candidates sum to 1.60000 bar, maintain H₂:HNO = 10:1 and each component is representable at five significant decimal digits. Their effective log steps differ slightly in magnitude on the two sides. An accepted estimator would need to use the actual log-pressure coordinates and baseline, with independent native pressure and flux verification for each run.

| Intended step | H₂ (bar) | HNO (bar) | NO (bar) | Actual ln(P_NO / 0.5 bar) |
|---|---:|---:|---:|---:|
| +0.04 | 0.98140 | 0.09814 | 0.52046 | +0.0401049375 |
| −0.04 | 1.01780 | 0.10178 | 0.48042 | −0.0399473771 |
| +0.02 | 0.99080 | 0.09908 | 0.51012 | +0.0200378937 |
| −0.02 | 1.00900 | 0.10090 | 0.49010 | −0.0199986465 |

This changes the approved pressure protocol. A separate gas-only campaign, numerical review and four fresh plan-specific execution decisions would be required. These candidates have not been natively run.
