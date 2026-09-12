<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete earlier IS-A to MID H surface migration through validated intermediate and TS evidence.

## Current Evidence Snapshot

- SCF9753658 user-stopped and confirmed EXIT after incomplete MPI startup (64/80 ranks; no ranks on gknew0440); no electronic steps.
- User authorized one replacement with identical SCF inputs and 80 cores, excluding gknew0440; SCF9753825 submitted via a current bound gate.
- SCF9753825 cycles RUN/PEND and changes allocations; bjobs -l explicitly reported Failed in talking to server to start the job. Exclusion of gknew0440 remains effective.
- Latest stored checkpoint 2026-09-12T17:18:51Z: RUN redispatched to gknew0444:32/gknew0421:32/gknew0447:16; no verified MPI or electronic startup. Earlier checks found 0 VASP ranks and no output.
- ALGO Normal, EDIFF1e-7, NELM200, original geometry and physical settings preserved; LWAVE/LCHARG enabled for electronic-state recovery.
- SuccessfulSCF9752745 converged96steps without saved restart state; independent Normal Dimer9753172 diverged before movement and remains stopped.
- Require normal electronic convergence, unchanged geometry and valid completed WAVECAR/CHGCAR before restart verification. No migration TS accepted.
- INT06 endpoint and MID->FS O-H TS remain accepted; earlier IS-A->INT06 remains unresolved.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Diagnose scheduler-to-execution-host launch communication for SCF9753825 and verify actual MPI/SCF startup before any scientific convergence claim.

## Submission Boundary

One user-authorized replacement SCF9753825 submitted; no further retry or Dimer submission.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Original-center SCF converges normally with valid saved electronic state, then restart reproducibility is verified before a separately gated short Dimer trial.

## Constraints

- Same H50 moves; preserve SIGMA0.20 and bottom18Fe fixed.
- Do not rerun MID-to-FS O-H work.

## Authoritative References

- docs/reviews/int06_mid_scf9753825_dispatch_failure_20260913.md
- docs/reviews/int06_mid_scf9753825_no0440_20260913.md
- docs/reviews/int06_mid_scf9753658_save_state_20260912.md
- docs/reviews/int06_mid_dimer9753172_stopped_20260912.md
- docs/reviews/int06_mid_dimer9753172_normal_20260912.md
- docs/reviews/int06_mid_scf9752745_20260912.md
- docs/reviews/gpu1517_direct_dimer9749920_20260910.md
- docs/reviews/valley9748648_accepted_20260910.md
- docs/reviews/oh_ts_accepted_barrier_20260910.md
<!-- state-handoff:end current_task -->
