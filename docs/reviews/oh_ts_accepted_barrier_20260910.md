# O–H TS accepted and electronic barrier registered

## Scope

User explicitly accepted Dimer9746548's current DIMCAR residuals for formal TS
validation. The earlier frequency-only approval and all original calculation
files were retained unchanged. A separate review workspace holds refreshed
source bindings and byte-identical copies of the completed frequency outputs.
No VASP or GPU calculation was submitted, stopped or repeated.

This result covers MID9737143 → FS-A9725471 O–H formation only. It does not
complete the preceding IS-A → MID surface-H migration steps.

## Validation

- Dimer9746548: normal/electronic completion, maximum atomic force
  0.018201 eV/Å, negative curvature -11.8812 eV/Å².
- Accepted residual diagnostics: DIMCAR Force 0.06398 and Torque 1.2054.
- VFA9747902: complete O48/H50 (zero-based 47/49) local partial Hessian,
  one imaginary mode at 1407.654162 cm^-1, mode 6.
- Normalized Cartesian mode displacements of ±0.015 Å give O–H distances
  1.35296760 and 1.38625859 Å around 1.36961288 Å. C–C remains 1.41786729 Å.
  The mode is assigned to the intended O–H reaction coordinate.
- The current pipeline returned `TS_ACCEPTED`. Formal Grade A uses the existing
  explicitly reviewed, complete, single-imaginary-mode Dimer rule; automated
  multi-mode classification remains unconfigured. No numerical frequency
  cutoff was invented. This is not a full-system Hessian validation.

## Accepted energy chain

All three final OUTCAR energies use PBE, the same Fe/C/O/H PAW-PBE potential
titles, ENCUT 400 eV, Gamma 5×5×1, ISPIN 2 with the same magnetic seed,
ISMEAR 1, SIGMA 0.20 eV, identical cells and bottom-18-Fe fixed masks.
The final-energy convention is `fe110_converged_toten_sigma0p20_v1`.
Normal/electronic/ionic completion was checked for the final energy sources.

| State | Job | Final TOTEN / eV |
|---|---|---:|
| Local IS (MID) | 9737143 | -388.43796188 |
| TS | 9746548 | -387.15213470 |
| FS-A | 9725471 | -388.04695175 |

Forward electronic barrier: **1.28582718 eV**.
Reverse electronic barrier: **0.89481705 eV**.
Reaction energy: **+0.39101013 eV**.

No ZPE, entropy or free-energy correction is included. Registry kinetic
eligibility is conditional on completing the remaining thermochemistry; this
result is not kinetics-ready. The workbook explicitly states that limitation.

## Registered outputs

- Validation: `fe110_c2ho_oh_dimer9746548_vfa9747902_accepted_20260910`.
- Barrier: `fe110_c2ho_oh_mid9737143_ts9746548_fs9725471_sigma0p20`.
- Strategy: `fe110_c2ho_oh_local_micro_neb_dimer9746548_grade_a`.
  Barrier and method-only strategy were stored atomically. Canonical template
  retrieval verifies `evidence_valid=true`. Only strategy can transfer to a
  new reaction, not coordinates, atom indices, MODECAR or energies.
- Workbook: `outputs/oh_ts_barrier_20260910/课题一TS.xlsx`, `TS记录` row 6.
- Evidence, current gates and immutable registry/promotion receipts:
  `calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/formal_ts_validation_20260910/`.
- Both calculation workflow projections now read `accepted`, with immutable
  history retained. The two endpoints' scientific status events now match their
  existing accepted compatible final-energy results.

The preceding **35 rows** meant 2 calculation records, 2 jobs, 2 status events,
27 file indexes and 2 reviews—not 35 TS or barrier results. Formal TS/barrier
records were added only after the subsequent explicit acceptance and checks.

## Verification and boundaries

Database schema/integrity and foreign keys passed. The accepted TS, barrier,
template and spreadsheet receipt were queried and their links checked.
Workbook formulas Y6:AA6 are `=V6-U6`, `=V6-X6`, `=X6-U6`; values match the
registry. No formula errors were found. All pre-existing values and formulas
in the three worksheets were preserved. The new identity and energy ranges
were rendered and visually checked; the pre-existing clipped method text in
the earlier C+H row was left unchanged.

The canonical Excel writer now explicitly recalculates before export.
Node syntax check and 45 related registry-promotion, TS-validation and
execution-gate tests passed. No scientific thresholds were changed.

Review-only preparation caught a JSON numeric-serialization hash mismatch,
a malformed generated gate JSON and legacy workflow-state labels. Those
attempts were rejected before their respective writes; corrected exact
documents passed the same validators. No gate was bypassed.

Repository-state sync is independently blocked by conflicting live events
`task-completed-966f70761e2de2c804e6dced` and
`task-migration9748648-open-20260909-v2`; no unrelated event was changed.
The authoritative scientific database and workbook registration are complete.
