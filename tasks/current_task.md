<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete earlier IS-A to MID H surface migration through validated intermediate and TS evidence.

## Current Evidence Snapshot

- Dimer9753172 explicitly stopped by user; scheduler EXIT confirmed2026-09-12T12:52:03Z. Outputs retained; no retry.
- SCF9752745 genuinely converged96steps on unchanged original geometry; this did not establish reproducible cold-start stability.
- Normal Dimer9753172 diverged during first fixed-center SCF, exhausted200steps, no complete DIMCAR row; forces/energies are invalid for TS interpretation.
- POSCAR/POTCAR/KPOINTS hashes and major effective electronic settings match the successful static; both ISTART0/ICHARG2 cold starts, no converged wavefunction transferred.
- Initial SCF trajectories separate before any center movement; step21 BRMIX precedes massive non-Hermitian DAV warnings. Specific numerical/implementation root cause remains unresolved.
- No migration TS accepted. INT06 endpoint and MID->FS O-H TS remain accepted; earlier IS-A->INT06 unresolved.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Review successful-static versus failed-Dimer cold-start evidence; prepare a reproducible electronic restart strategy only after user resumes work.

## Submission Boundary

User stopped Dimer9753172; no further calculation, retry or Dimer restart authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Independent valley relaxation and geometry reviewed; then define scientifically supported migration segments.

## Constraints

- Same H50 moves; preserve SIGMA0.20 and bottom18Fe fixed.
- Do not rerun MID-to-FS O-H work.

## Authoritative References

- docs/reviews/int06_mid_dimer9753172_stopped_20260912.md
- docs/reviews/int06_mid_dimer9753172_normal_20260912.md
- docs/reviews/int06_mid_scf9752745_20260912.md
- docs/reviews/gpu1517_direct_dimer9749920_20260910.md
- docs/reviews/valley9748648_accepted_20260910.md
- docs/reviews/oh_ts_accepted_barrier_20260910.md
<!-- state-handoff:end current_task -->
