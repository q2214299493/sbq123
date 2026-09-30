<!-- state-handoff:start current_task -->
# Current Task

## Objective

Monitor ordinary coarse NEB9806036 for the remaining IS-A9725473 -> INT06_9748648 H migration.

## Current Evidence Snapshot

- User approved an exception to the preferred total-core multiple: retain nine internal images and NPAR4; use 72 MPI ranks, eight ranks per image, and NP_PER_NODE16.
- Old LSF9802439 was PEND when the bound STOP_JOB executor ran; it is now EXIT. No VASP step was established for that job.
- Replacement LSF9806036 was submitted once on sunboquan-cdj1-temp. Latest scheduler checkpoint is PEND and canonical monitor shows images01-09 at zero ionic steps, with no energy or force yet.
- All eleven POSCARs, INCAR, KPOINTS, POTCAR.spec, path report/review, dist.dat, and movie.xyz are byte-identical to the old job; only NP and NP_PER_NODE changed in script.lsf, and the geometry evidence was rebound to new local paths.
- The geometry diagnosis, ordinary-NEB preflight, and current SUBMIT_VASP gate passed. No convergence, TS, barrier, or Grade-A result is claimed.

## Lifecycle Status

- Phase: `active`

## One Executable Step

At the next requested checkpoint, query LSF9806036 on sunboquan-cdj1-temp and use the canonical compact NEB monitor; distinguish queue, SCF, ionic force and path states.

## Submission Boundary

One replacement ordinary NEB submitted. Do not duplicate, restart, change resources, start CI/Dimer, or stop it without a fresh current gate and user authority.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- NEB9806036 is monitored with scheduler and per-image evidence; a completed/stopped path is reviewed before any authorized refinement.

## Constraints

- Keep accepted INT06-MID and MID-FS segments unchanged.
- Preserve atom order, fixed Fe0-17, nine internal images, NPAR4, and SIGMA0.20 compatibility.
- Under resource pressure prefer a 16- or 32-core per-node cap and a matching total-core multiple only where compatible with image/rank divisibility and quota; this nine-image job has the approved 72-core exception.
- GPU predictions cannot establish a TS or electronic barrier.

## Authoritative References

- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/resource_reallocation_20260930/stop_receipt.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/resource_reallocation_20260930/scheduler_after.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r3_72r_16pn_20260930/resource_reallocation_identity.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r3_72r_16pn_20260930/submission_record.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r3_72r_16pn_20260930/scheduler_checkpoint_submission.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r3_72r_16pn_20260930/execution_gate_decision.json
<!-- state-handoff:end current_task -->
