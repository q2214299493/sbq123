# Phase 3.2.2.1 native validation and Phase 3.2.2 completion

Four individually approved replacement CATKINAS runs recovered the NO constrained-composition reaction order of the synthetic Ni/Cu cycle at 400 K. All four matched the declared 1.600000 bar total and 10:1 H₂:HNO remainder ratio. The original Phase 3.2.2 report remains the historical record of the first failed campaign.

Baseline NO was 0.50000 bar and baseline overall turnover was 81.5127701616 per reference site pair per second. The observed order follows the fixed-total composition path, including the compensating changes of H₂ and HNO. The forward hydrogenation elementary NO order is 1 and its reverse order is 0.

| Step | x minus | x plus | Negative side | Positive side | Endpoint secant | Quadratic slope at zero |
|---|---:|---:|---:|---:|---:|---:|
| coarse | -0.0399473771 | 0.0401049375 | 0.5012397328 | 0.4883179049 | 0.4947661024 | 0.4947915353 |
| fine | -0.0199986465 | 0.0200378937 | 0.4980687729 | 0.4916082698 | 0.4948353548 | 0.4948416879 |

The absolute coarse/fine change is 5.015259187e-05. The project threshold max(0.002, 0.05 × |fine|) is 0.0247420844, giving status **stable**. Each x coordinate uses the actual native NO pressure. The quadratic interpolates the baseline and both signed samples in logarithmic coordinates. This is a local estimate for this feed and temperature.

| Sample | H₂ / bar | HNO / bar | NO / bar | Net TOF | Δθ HNO-top | Δθ H2-top | Δθ H2-bridge | Native s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| coarse plus | 0.98140 | 0.09814 | 0.52046 | 83.12484681 | +0.00340528 | -0.00671612 | -0.00627442 | 85.54 |
| coarse minus | 1.01780 | 0.10178 | 0.48042 | 79.89685453 | -0.00352900 | +0.00668629 | +0.00599824 | 45.90 |
| fine plus | 0.99080 | 0.09908 | 0.51012 | 82.31970363 | +0.00171957 | -0.00335525 | -0.00310221 | 75.99 |
| fine minus | 1.00900 | 0.10090 | 0.49010 | 80.70487608 | -0.00175050 | +0.00334782 | +0.00303319 | 75.32 |

All replacements converged sequentially. Total native time was 282.75 s of 840 s and elapsed campaign time was 284.15 s of 960 s. No retries were used. All actual pressure components matched their predicted values. Across the four points the largest absolute site residual was 0, H/N/O balance residual 0, steady-state residual 8.52651e-14, and log detailed-balance residual 3.34023e-06. Per-direction coefficients, activities and fluxes are recorded with each case. [Native result and response matrices](result.json)

Four acceptance receipts, signed plans, human approval sources, native MAT files and log extracts accompany the results. All 16 native output hashes were checked in the development archive. Both development and release worktrees independently reconstructed the accepted result bytes and recovered both derivatives by solving a three-point polynomial using MAT NO pressures and HNO production divided by two. [Plans and numerical method](review.md)

The earlier four HNO-top energy perturbations and the unperturbed baseline were reused. HNO-top sensitivity remains 0.401872339 at ±0.010 eV and 0.401377874 at ±0.005 eV. All 76 earlier evidence files match the checkpoint hashes, including the rejection of the original 1.600005 bar feed. Fe(110) continues to lack reviewed kinetic, site and endpoint free-energy evidence. [Earlier results and limitations](../phase3_2_2/completion.md)

The recovery regression passed 150 focused tests in each worktree. After adding two raw MAT replay tests, the final broader suites in both worktrees had 709 passed, eight optional native Zacros tests skipped and the live baseline case deselected. The preceding full-suite checkpoint retains five historical failures. [Development regression](regression/development-final.txt.gz) · [Release regression](regression/release-final.txt.gz) · [Historical failures](../phase3_2_0_1/historical_regression_debt.md)
