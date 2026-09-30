<!-- state-handoff:start current_task -->
# Current Task

## Objective

Monitor ordinary coarse NEB9808511 for the remaining IS-A9725473 -> INT06_9748648 H migration.

## Current Evidence Snapshot

- User changed the future VASP default connection to nsgkn_chengdj3@10.68.0.103:22 (sunboquan-codex / sbq123).
- Old NEB9806036 was PEND when the current STOP_JOB executor stopped it; raw scheduler evidence confirms EXIT. Its old temporary SSH connection was removed; calculation files and other jobs were retained.
- Replacement NEB9808511 was submitted once with 108 ranks, 12 ranks per internal image, NPAR4 and NP_PER_NODE16. Its saved scheduler checkpoint is PEND.
- All eleven POSCARs, INCAR, KPOINTS, POTCAR.spec, contract and reviewed dist/movie/path evidence are byte-identical to the source package. The geometry parser and execution evidence were regenerated against the replacement directory.
- Geometry diagnosis, ordinary-NEB preflight and current SUBMIT_VASP gate passed. No convergence, TS, barrier or Grade-A result is claimed.

## Lifecycle Status

- Phase: `active`

## One Executable Step

At the next requested checkpoint query LSF9808511 through sunboquan-codex and run the canonical compact NEB monitor for ~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930; separate scheduler, electronic, force and geometry states.

## Submission Boundary

One replacement ordinary NEB submitted under explicit user authority. No duplicate, restart, resource change, CI/Dimer or stop without a current gate and user authority.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- NEB9808511 is monitored with scheduler and per-image evidence; a completed/stopped path is reviewed before any authorized refinement.

## Constraints

- Keep accepted INT06-MID and MID-FS segments unchanged.
- Preserve atom order, fixed Fe0-17, nine internal images, NPAR4 and SIGMA0.20 compatibility.
- User explicitly requested 108 total ranks for this replacement; under resource pressure retain a 16- or 32-rank per-node cap subject to image/rank divisibility and quota.
- GPU predictions cannot establish a TS or electronic barrier.

## Authoritative References

- archive/vasp_server_switch_20260930/user_request.json
- archive/vasp_server_switch_20260930/stop_receipt.json
- archive/vasp_server_switch_20260930/scheduler_after.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930/server_switch_identity.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930/submission_preflight.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930/execution_gate_decision.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930/submission_record.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930/scheduler_checkpoint_submission.json
<!-- state-handoff:end current_task -->
