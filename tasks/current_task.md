<!-- state-handoff:start current_task -->
# Current Task

## Objective

Monitor ordinary coarse NEB9802439 for the remaining IS-A9725473 -> INT06_9748648 H migration.

## Current Evidence Snapshot

- User continued after upload-failure recovery review; prior unresolved local/remote reservation remains immutable, separate new attempt directory used.
- New SSH tar stdin transfer avoids login-banner SCP framing failure. Remote canonical executor verified all input hashes and exact original Fe/C/O/H POTCAR before bsub.
- Actual LSF receipt:9802439 on sunboquan-cdj1-temp (10.68.0.103/nsgkx_cdj1), Gkn_normal. Latest hash-bound scheduler checkpoint PEND; VASP progress not yet established.
- Canonical initial compact monitor: images01-09 have0 ionic steps and no energy/force values. Missing output is not electronic convergence or TS evidence.
- Scientific files byte-identical:11 structures/9 interiors,108ranks/NPAR4,Fast,EDIFF1e-5,EDIFFG-0.05,NSW300,SIGMA0.20,no climb,pilot or restraints. New bundle hash differs only because geometry evidence binds new source paths.
- New workdir:calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928; same basename under ~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/.
- 54 backend/submission/execution-gate tests and88 scheduler evidence/mutation-boundary tests passed; targeted compilation/Ruff passed. No convergence/barrier/Grade-A claim.

## Lifecycle Status

- Phase: `active`

## One Executable Step

At the next requested checkpoint, query LSF9802439 on sunboquan-cdj1-temp and use the canonical compact NEB monitor; distinguish queue, SCF, ionic force and path states.

## Submission Boundary

One ordinary NEB submitted. No duplicate/retry, pilot, CI,Dimer, stop or parameter change without a fresh current gate and user authority; preserve old failure markers.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- NEB9802439 is monitored with scheduler and per-image evidence; a completed/stopped path is reviewed before any authorized refinement.

## Constraints

- Keep accepted INT06-MID and MID-FS segments unchanged.
- Preserve request/checkpoint hashes, atom order, fixed Fe0-17 and SIGMA0.20 compatibility.
- GPU predictions cannot establish a TS or electronic barrier.

## Authoritative References

- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/submission_record.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/submission_attempt.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/scheduler_checkpoint_submission.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/execution_gate_decision.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/submission_preflight.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/submission_recovery_review.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/user_execution_request.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928/scientific_input_identity.json
<!-- state-handoff:end current_task -->
