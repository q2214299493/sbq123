<!-- state-handoff:start current_task -->
# Current Task

## Objective

Optimize the reviewed IS-A9725473 to INT06_9748648 H surface migration with MatRIS and AQCat25 audit before VASP coarse NEB.

## Current Evidence Snapshot

- GPU1802 producer exited0 at2026-09-26T07:07:45Z; live Slurm record purged, terminal scheduler status unavailable.
- Ordinary MatRIS ML-NEB converged in19 steps, maximum NEB force0.081585 eV/A below0.10; complete11-image AQCat25 exact-path audit returned.
- Request6011d0a9/checkpoints/runner and all returned structure hashes verified; geometry recomputed PASS, max adjacent RMSD0.080181 A, movie11frames matches snapshots.
- Predicted MatRIS local peaks01/05/09, global maximum05; do not infer three real TS from an ML profile.
- No ML-CI, restraints, new training or VASP submission; returned path remains needs_work_review.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Review the complete multi-peak ML path and H50 site changes, then prepare the appropriate compatible VASP coarse-NEB handoff; do not submit without authorization.

## Submission Boundary

One retry was explicitly authorized and submitted. No automatic additional GPU rerun, fine-tuning or VASP submission.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- GPU1802 produces reviewed complete-path evidence and audit, or a bounded failure with its first/last valid structures preserved.

## Constraints

- Keep accepted INT06-MID and MID-FS segments unchanged.
- Preserve request/checkpoint hashes, atom order, fixed Fe0-17 and SIGMA0.20 compatibility.
- GPU predictions cannot establish a TS or electronic barrier.

## Authoritative References

- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_is_a_int06_path_20260926/gpu_execution_20260926/gpu1802_return_checks.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_is_a_int06_path_20260926/gpu_execution_20260926/output/run2/dual_model_gpu_ml_neb_path_manifest.candidate.json
<!-- state-handoff:end current_task -->
