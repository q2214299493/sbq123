<!-- state-handoff:start current_task -->
# Current Task

## Objective

Submit the reviewed GPU1802 complete IS-A9725473 -> INT06_9748648 path as one ordinary VASP coarse NEB.

## Current Evidence Snapshot

- User authorized temporary 10.68.0.103:22/nsgkx_cdj1 account for this existing coarse NEB only; separate alias sunboquan-cdj1-temp. Default backend unchanged.
- Login ycn03/LSF/VTST executable and Intel environment verified. Fe/C/O/H POTCAR assembled remotely from existing licensed datasets, exact original SHA256 e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85.
- Scientific/input bundle unchanged:108 ranks,9 interiors,NPAR4,Fast,EDIFF1e-5,EDIFFG-0.05,NSW300,SIGMA0.20,no pilot or restraints. New target-bound gate lists SUBMIT_VASP.
- Resolved legitimate mapped HOME path by canonical comparison while retaining symlink guards;51 related backend/submission/gate tests passed.
- Canonical executor created local/remote reservation, then SCP failed: Received message too long 220204320 because login banner contaminated transfer. bsub stage not reached; no new job ID obtained.
- Canonical status UNKNOWN_NEEDS_RECONCILIATION retained; read-only reservation/directory/scheduler evidence saved. Never remove marker or automatically retry.

## Lifecycle Status

- Phase: `blocked`

## One Executable Step

Review read-only upload-failure recovery evidence with the operator; obtain explicit confirmation of no matching job and authority for a new submission, then repair banner-safe transport without altering scientific inputs.

## Submission Boundary

No new submission or deletion of reservations until explicit human recovery confirmation. Keep default sunboquan-codex and accepted other reaction intervals unchanged.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- One actual ordinary NEB submission receipt and scheduler checkpoint are recorded, or a bounded remote precheck failure is truthfully retained without claiming submission.

## Constraints

- Keep accepted INT06-MID and MID-FS segments unchanged.
- Preserve request/checkpoint hashes, atom order, fixed Fe0-17 and SIGMA0.20 compatibility.
- GPU predictions cannot establish a TS or electronic barrier.

## Authoritative References

- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/temporary_backend_precheck_retry1_20260927.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/temporary_execution_gate_decision_20260927.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/user_temporary_backend_request_20260927.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/submission_attempt.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/submission_record.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/temporary_upload_failure_reconciliation_20260927.json
<!-- state-handoff:end current_task -->
