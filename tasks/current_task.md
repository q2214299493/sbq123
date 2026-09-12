<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete earlier IS-A to MID H surface migration through validated intermediate and TS evidence.

## Current Evidence Snapshot

- Dimer9749920 and9753172 remain user-stopped; no migration TS accepted.
- SuccessfulSCF9752745 converged96steps, but its electronic state was not saved; an independent Normal Dimer cold start diverged before center movement.
- User resumed staged recovery: save converged original-center electronic state, then verify restart before a short Dimer trial.
- Step1 SCF9753658 submitted via current hash-bound gate on sunboquan-codex,80cores,Gkn_normal; checkpoint2026-09-12T13:02:29Z PEND.
- Compared with successfulSCF9752745, only LWAVE/LCHARG are enabled. Original geometry,ALGO Normal,EDIFF1e-7,NELM200 and physical settings preserved.
- Require electronic convergence, normal completion, unchanged geometry and valid completed WAVECAR/CHGCAR before restart verification; file existence alone is insufficient.
- INT06 endpoint and MID->FS O-H TS remain accepted; earlier IS-A->INT06 remains unresolved.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Monitor SCF9753658 and validate electronic convergence, unchanged geometry, and completed compatible WAVECAR/CHGCAR before preparing restart verification.

## Submission Boundary

One fixed-geometry SCF9753658 submitted for step1; no automatic retry or long Dimer submission.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Independent valley relaxation and geometry reviewed; then define scientifically supported migration segments.

## Constraints

- Same H50 moves; preserve SIGMA0.20 and bottom18Fe fixed.
- Do not rerun MID-to-FS O-H work.

## Authoritative References

- docs/reviews/int06_mid_scf9753658_save_state_20260912.md
- docs/reviews/int06_mid_dimer9753172_stopped_20260912.md
- docs/reviews/int06_mid_dimer9753172_normal_20260912.md
- docs/reviews/int06_mid_scf9752745_20260912.md
- docs/reviews/gpu1517_direct_dimer9749920_20260910.md
- docs/reviews/valley9748648_accepted_20260910.md
- docs/reviews/oh_ts_accepted_barrier_20260910.md
<!-- state-handoff:end current_task -->
