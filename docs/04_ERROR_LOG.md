# Error Log

Only unresolved problems belong here. Resolved detail through 2026-06-27 is preserved in `archive/state_history/ERROR_LOG_through_20260627.md` and Git history.

| ID | Open problem | Impact | Next action / owner |
|---|---|---|---|
| `E-20260905-ROOT-LAYOUT` | `test_root_contains_no_executable_or_download_clutter` rejects the existing `.codex_tmp` and `scientific-problem-compiler` root directories | Strategy-learning regression run: 170 passed, one repository-layout failure; feature and scientific-gate tests passed | Review directory ownership and intended project placement before moving files or changing the layout contract; no cleanup or allowlist relaxation was performed |
| `E-003` | Historical policy required missing compatible true Fe(110) adsorbed final statics | Superseded on 2026-08-07: formal Fe(110) surface energies now use compatible converged `SIGMA=0.20 eV` final `OUTCAR` `TOTEN`; existing `SIGMA=0.10 eV` statics are optional evidence | Do not submit replacement statics solely for energy promotion; instead verify and register each converged relaxation/DIMER output under `fe110_converged_toten_sigma0p20_v1` |
| `E-006` | CatApp and OC20NEB/CatTSunami machine access remain unverified | Whitelist retrieval has incomplete production connectors | Confirm official access methods in `catalysis_data_retrieval` |
| `E-007` | TS meaningful-imaginary and soft-mode thresholds need confirmation | The production threshold values are `null`; completed frequency outputs therefore remain `Ungraded` and cannot receive an automatic frequency-count A/B/C grade | Resolve both thresholds from reviewed project evidence before the first final frequency grade |
| `E-008` | CATKINAS/Zacros have only software smoke tests, not project models | MKM/KMC outputs cannot be treated as Fe/CO science | Wait for validated kinetic data and reaction network |
| `E-010` | Slurm accounting storage is disabled on MZ73 | A GPU job that has left `squeue` has no independently queryable terminal state through `sacct`; the new hash-bound producer exit record is process evidence, not scheduler authority | MZ73 administrator: enable Slurm accounting storage and job accounting; keep producer exit records mandatory before and after that change |
| `E-013` | AQCat25 has compatible near-relaxed Fe45 adsorption force calibration but no TS/path-domain calibration or per-candidate uncertainty model | Adsorption ranking may use the bounded Fe45 gate; NEB/BA-Sella/path/saddle candidates remain prediction-only and cannot receive an in-domain TS verdict | Calibrate only when compatible off-equilibrium/path/saddle VASP force labels exist; until then keep TS domain status `uncalibrated` |
| `E-014` | Fe(110) CO-dissociation pilot `9638307` completed but image 06 converged to `93.1102 muB`, about `12.6–12.9 muB` below adjacent images 05/07; it also required 179 SCF iterations | Exact-geometry diagnostic `9639279` proved the cold start selected an erroneous high-energy magnetic branch: the `2.4 muB/Fe` seed converged to `105.0202 muB` in 52 SCF cycles and was `2.29958246 eV` lower | Use the approved high-spin seed. Adjacent total-magnetization differences above `2.0 muB` now trigger review only and are not an independent stop/submission gate |
| `E-015` | The exact-path 56-core pilot `9653580` passed, but the 112-core pilot `9654240` and seeded fixed-coordinate image06 recovery `9654834` both failed electronically. Job `9654834` read WAVECAR, then `rms(c)` jumped at DAV 30 and ended with `BRMIX`, subspace-matrix and fatal `EDDDAV/ZHEGV`; it produced no force block or CONTCAR | The path itself is not rejected, but image07, the 112-core pilot retry and coarse NEB are blocked | Obtain explicit user approval for a revised image06 electronic-recovery strategy; do not reuse job-9654834 output |
| `E-016` | Nine-image pilot `9655434` used 126 ranks, giving 14 ranks/image with `NPAR=4`; VASP immediately failed `M_divide` and MPI communicator initialization before any electronic or ionic step | The launch failure has no scientific meaning; the replacement 108-rank pilot `9655921` is awaiting execution | Preflight now enforces per-image ranks divisible by `NPAR`; validate job `9655921` before resolving this item or allowing coarse NEB |
| `E-017` | Dimer job `9656664` reached LSF `DONE` and VASP's atomic-force stopping condition, but the final complete DIMCAR row has Force `0.05994 eV/A` and Torque `0.14817 eV/A`, above the project technical gates `0.02` and `0.01 eV/A` | The candidate retains stable negative curvature and a target-aligned final mode, but it is not technically converged and cannot advance to frequency or TS acceptance | Review a low-cost continuation from the hash-bound CONTCAR and NEWMODECAR with a tighter structural stopping condition; require a new preflight, user authorization, and `START_DIMER` gate before submission |
| `E-018` | C2HO*+H* -> C2H2O* MatRIS staged-release job `1324` converged its restrained 17-image preconditioning path but lost required O-H `1.1-1.8 A` coverage at the first half-strength release (three internal images became two) | No fully released ML path, Dimer parent, TS, or barrier exists; another threshold-only retry would not establish model accuracy | Use the immutable snapshot and coverage-loss boundary for the prepared exact MatRIS/AQCat25-to-VASP active-learning round; require VASP error assessment and, if needed, a new accepted checkpoint before a complete-path rerun |

Update this table in place. Move resolved items to historical results or Git history; do not append routine job checkpoints.

## 2026-08-02 - 112-Core Exact-Path Pilot Electronic Failure in Images 06-07

- Job `9654240` was stopped through the user-authorized `STOP_JOB` gate and is
  scheduler `EXIT`; no ionic step completed.
- Images 01-05 reached `EDIFF=1E-5`, but image06 shows repeated
  `BRMIX: very serious problems` with runaway electronic energies, and image07
  exhausted `NELM=200` without reaching the threshold.
- This is electronic failure evidence, not an ionic-force or path-convergence
  result. Sequential fixed-coordinate recovery is authorized and image06 job
  `9654834` was attempted but failed electronically; image07, the 112-core
  pilot retry and coarse NEB remain blocked.

<!-- state-handoff:start task_error_events -->
## Managed Open Errors

<!-- state-handoff:end task_error_events -->
