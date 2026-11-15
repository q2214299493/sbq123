# CH + CO: VFA2260 mode12 review — 2026-11-15

## Result and scope

Mode12 is the target C45–C46 opening/closing mode for CH* + CO* -> CH-C-O*.
This is a target-mode diagnostic review, not formal TS acceptance or a barrier
registration. Atom indices below are zero-based. No scientific job was submitted,
restarted or stopped; no registry or workbook scientific result was changed.

## Verified evidence

- Scheduler:2260 DONE. VASP completed normally with25 force evaluations,
  12 vibrational modes and exactly one imaginary mode:12,318.644011cm^-1.
- Eleven collected source files match remote SHA256 inventory;submitted inputs
  are unchanged. Complete49-row mode data were parsed,including zero components
  on all45 fixed Fe atoms. Reference coordinates match the submitted POSCAR
  within7.39e-7A under periodic mapping.
- The normalized dynamical-matrix eigenvector was divided by sqrt(actual OUTCAR
  atomic mass),then normalized in Cartesian displacement space. Fe/C/O/H masses
  are55.847/12.011/16.0/1.0. The sign is arbitrary;the illustrated positive sign
  shortens C45–C46. See official VASP guidance on
  [finite-difference modes](https://vasp.at/wiki/Phonons_from_finite_differences)
  and [mass conversion](https://vasp.at/wiki/Improved_dimer_method).

For a unit-norm physical displacement vector,the bond-length derivatives are:

| Coordinate | Derivative A per unit mode displacement |
|---|---:|
| C45–C46 | -1.116760 |
| C46–O47 | +0.077641 |
| C45–H48 | +0.002261 |

C–C response is14.38 times C–O response. The two C atoms account for78.21% of
squared Cartesian mode displacement;H48 accompanies the CH group rather than
primarily stretching C–H. Absolute cosine to final Dimer NEWMODECAR is0.934 on
the same active set (0.880 in full49-atom space);this is alignment,not accuracy.

The actual top/side three-frame plot was visually reviewed. These illustrative
displacements have maximum atomic amplitude0.10A;they are not optimized
endpoints,IRC or a connectivity test.

| Frame | C–C A | C–O A | C–H A |
|---|---:|---:|---:|
| -q | 1.906328 | 1.222075 | 1.107513 |
| reference candidate | 1.739964 | 1.227804 | 1.100799 |
| +q | 1.575192 | 1.245000 | 1.108179 |

## Acceptance boundary

The partial Hessian covers C45/C46/O47/H48,not the full slab. The approved VFA
profile uses SIGMA0.10;its energy is not imported into the SIGMA0.20 final-TOTEN
chain. Dimer9998592 max atomic force0.015198eV/A and negative curvature pass hard
checks,but its last complete DIMCAR Force0.06316/Torque0.20789 were accepted only
for diagnostic frequency. Terminal49 has force only;missing fields were not filled.

Owner analysis:principal mode accepted;overall NEEDS_REVIEW/Ungraded,
dimer_technical_acceptance=false,kinetic_eligible=false. The current review is
accepted_for_target_mode_review_only,not an overall scientific acceptance.
Project meaningful-imaginary and additional-soft-mode thresholds remain null.
Next:formal TS acceptance review,including explicit residual acceptance for that
purpose and reviewed frequency policy. No automatic Grade-A/barrier promotion.

## Reproducibility and validation

Evidence directory:
`calculations/fe110_ch_co_to_chco_ts_20261109/vfa_mode12_review_20261115_v1/`.
It contains preserved raw sources,collection receipt,mode12_metrics.json,
mode12_three_frames.png,mode12_review.json,vfa_analysis.diagnostic.json and
verification.json. Verification PASS:11 hashes,geometry identity,scope and
diagnostic-only acceptance boundary.

Task adapter:`archive/chco_mode12_20261115/review.py`;regression tests:
`tests/test_chco_mode12_review_20261115.py`. Python compilation,Ruff and targeted
pytest (new tests plus tests/test_ts_validation.py) passed:19 tests. No model or
scientific calculation was run by these tests.

RSI was invoked once with the original research goal and default budgets. Stable
entry resolved CLI0.169.0-alpha.11.1;protocol admission passed,but model turn1
failed with `ValueError: unexpected notification or turn mismatch`. Zero host
tool executions,zero selected policies,no usable RSI research opinion;no retry.
Independent raw-data review above supplies the conclusion. Receipt:
`C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/runs/chco_mode12_assignment_20261115_v1/run_receipt.json`.
Dashboard:
`C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html`.
