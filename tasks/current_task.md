<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete earlier IS-A to MID H surface migration through validated intermediate and TS evidence.

## Current Evidence Snapshot

- INT06 endpoint9748648 and MID->FS O-H TS remain accepted; earlier IS-A->INT06 unresolved.
- Reviewed GPU1517 frame02 remains a predicted starting candidate; direct reviewed-GPU-to-Dimer policy remains in force.
- Dimer9749920 stopped by user; scheduler EXIT. Ten completed SCF cycles exhausted NELM200 without convergence; no accepted migration TS.
- Structure diagnosis: C2HO and neighboring Fe adjust, H50 stays near Fe38-Fe41 bridge; unconverged forces cannot prove geometric overshoot.
- User authorized one original-center fixed-geometry SCF test. ALGO Normal, EDIFF1e-7, NELM200,80cores, same physical branch; LORBIT11 adds local magnetic projections.
- SCF diagnostic9752745 submitted through current bound gate on sunboquan-codex; checkpoint2026-09-12T03:23:46Z PEND; no output acceptance.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Monitor SCF9752745; after electronic convergence and exact-geometry validation, compare atom-resolved forces and local Fe moments before deciding transverse relaxation or Dimer.

## Submission Boundary

One fixed-geometry SCF9752745 authorized and submitted; no automatic retry, Dimer restart or TS acceptance.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Independent valley relaxation and geometry reviewed; then define scientifically supported migration segments.

## Constraints

- Same H50 moves; preserve SIGMA0.20 and bottom18Fe fixed.
- Do not rerun MID-to-FS O-H work.

## Authoritative References

- docs/reviews/int06_mid_scf9752745_20260912.md
- docs/reviews/gpu1517_direct_dimer9749920_20260910.md
- docs/reviews/valley9748648_accepted_20260910.md
- docs/reviews/oh_ts_accepted_barrier_20260910.md
<!-- state-handoff:end current_task -->
