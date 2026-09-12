<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete earlier IS-A to MID H surface migration through validated intermediate and TS evidence.

## Current Evidence Snapshot

- INT06 endpoint9748648 and MID->FS O-H TS remain accepted; earlier IS-A->INT06 remains unresolved.
- Original Dimer9749920 remains user-stopped EXIT after persistent SCF failure.
- Exact original-center SCF9752745: DONE, normal completion,96steps electronically converged at EDIFF1e-7, no BRMIX, geometry unchanged.
- Converged original-center residual forces persist: C47 fmax0.352661eV/A, Fe37 approximately0.221065eV/A. This does not establish a TS.
- User explicitly requested Dimer after SCF diagnosis. New9753172 uses original reviewed GPU1517 frame02/01/03/MODECAR; only ALGO changes Fast->Normal,80cores, all other Dimer settings unchanged.
- Dimer9753172 passed current hard/input/execution gates and was submitted on sunboquan-codex. Checkpoint2026-09-12T08:34:23Z PEND.
- Direct reviewed-GPU-to-Dimer candidate policy remains valid; Dimer and frequency acceptance are still required before reporting a migration barrier.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Monitor Dimer9753172: electronic convergence, atomic forces, center/rotation progress and C2HO-Fe/H50 geometry before frequency handoff.

## Submission Boundary

One Dimer9753172 submitted under explicit user authority; no automatic retries or TS acceptance.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Independent valley relaxation and geometry reviewed; then define scientifically supported migration segments.

## Constraints

- Same H50 moves; preserve SIGMA0.20 and bottom18Fe fixed.
- Do not rerun MID-to-FS O-H work.

## Authoritative References

- docs/reviews/int06_mid_dimer9753172_normal_20260912.md
- docs/reviews/int06_mid_scf9752745_20260912.md
- docs/reviews/gpu1517_direct_dimer9749920_20260910.md
- docs/reviews/valley9748648_accepted_20260910.md
- docs/reviews/oh_ts_accepted_barrier_20260910.md
<!-- state-handoff:end current_task -->
