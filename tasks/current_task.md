<!-- state-handoff:start current_task -->
# Current Task

## Objective

Submit the reviewed GPU1802 complete IS-A9725473 -> INT06_9748648 path as one ordinary VASP coarse NEB.

## Current Evidence Snapshot

- User authorized review then coarse NEB; full11-image GPU1802 path reviewed numerically and in top/side/profile views.
- H50 changes neighboring Fe coordination continuously; C2HO/originalCH remain intact, no new OH/CH bond. Three ML peaks remain predictions, not accepted TS/intermediates.
- Exact GPU snapshots copied without interpolation; locked PBE/ENCUT400/Gamma5x5x1/SIGMA0.20/Fe2.2 branch, Fast/EDIFF1e-5/EDIFFG-0.05/NSW300/no-climb/no-restraints.
- Nine interiors require rank/image/NPAR divisibility;108ranks=9x12,NPAR4. No pilot added. Geometry/VTST movie11frames/input custodian and canonical preflight pass; current gate lists SUBMIT_VASP.
- Renewed2026-09-26 user submission instruction: fresh SSH precheck exit255 Connection closed; bounded diagnostic TCP/KEX/hostkey passed then publickey reply timed out. Server-side cause not established; no remote command ran.
- Canonical submission state NOT_RESERVED: no executor reservation, upload,bsub or jobID. Submission authority remains available for this exact package, not consumed.

## Lifecycle Status

- Phase: `blocked`

## One Executable Step

Confirm sunboquan-codex can authenticate with the configured agent key; after connectivity is restored, revalidate the unchanged gate and submit this exact authorized NEB once.

## Submission Boundary

User already authorized one reviewed coarse NEB. No pilot, duplicate submission, automatic retry, CI,Dimer,training or changes to accepted intervals.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- One actual ordinary NEB submission receipt and scheduler checkpoint are recorded, or a bounded remote precheck failure is truthfully retained without claiming submission.

## Constraints

- Keep accepted INT06-MID and MID-FS segments unchanged.
- Preserve request/checkpoint hashes, atom order, fixed Fe0-17 and SIGMA0.20 compatibility.
- GPU predictions cannot establish a TS or electronic barrier.

## Authoritative References

- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/path_review.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/work_review_evidence.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/execution_gate_decision.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/submission_preflight.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/user_execution_request.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/remote_submission_precheck_retry1.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_20260926/ssh_diagnostic_retry1.json
<!-- state-handoff:end current_task -->
