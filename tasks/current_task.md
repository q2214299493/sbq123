<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete earlier IS-A to MID H surface migration through validated intermediate and TS evidence.

## Current Evidence Snapshot

- 9748648: LSF DONE; ordinary valley06 relaxation completed in 79 steps; electronic and force criteria passed (0.0177274761 eV/A < 0.020).
- INT06 accepted as intact C2HO* + H* mapped migration endpoint; final TOTEN -388.50564344 eV under fe110_converged_toten_sigma0p20_v1.
- Schema9 registry completion applied: 12 inserted records and one workflow projection change; receipt in h_migration1357_valley06_relax_20260909/completed_review_20260910/registry_receipt.json.
- IS-A -> INT06 and INT06 -> MID are two path intervals awaiting TS evidence; image02 remains an unresolved first-interval ML minimum.
- The previously accepted MID -> FS O-H TS and 1.28582718 eV forward electronic barrier remain complete; do not repeat.
- No new NEB/Dimer/frequency/static/GPU calculation submitted; no Hessian, exhaustive symmetry equivalence or complete migration-barrier claim.
- INT06 -> MID local input package prepared: 3 interior images, 96 cores; VTST movie/distance, exact-MIC geometry, INCAR and input preflight checks completed. Execution gate has no allowed submission action without exact-package user authority. No new calculation was submitted.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Obtain exact-package authorization for INT06 -> MID ordinary NEB (3 images, 96 cores, NSW=300; bundle 1e34b1df2a0b4ee304cc2d5040e4fed365e0ead2421e049bba873cb232631735); then verify backend POTCAR, bind authorization, reevaluate the execution gate and submit only if SUBMIT_VASP is allowed.

## Submission Boundary

Local evidence review/preparation only. New NEB, Dimer, frequencies, static labels and GPU jobs require exact-package user authority.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Independent valley relaxation and geometry reviewed; then define scientifically supported migration segments.

## Constraints

- Same H50 moves; preserve SIGMA0.20 and bottom18Fe fixed.
- Do not rerun MID-to-FS O-H work.

## Authoritative References

- docs/reviews/valley9748648_accepted_20260910.md
- docs/reviews/int06_mid_path_prepared_20260910.md
<!-- state-handoff:end current_task -->
