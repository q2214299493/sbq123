<!-- state-handoff:start current_task -->
# Current Task

## Objective

Monitor Dimer9833429 from ordinary NEB9808511 peak05 for IS-A to INT06 H migration.

## Current Evidence Snapshot

- CI9826728 cancelled through explicit user STOP_JOB authorization; scheduler EXIT confirmed; remote files retained.
- Ordinary NEB9808511 remains accepted as a technically converged parent:71 steps, maximum final NEB force0.049947 eV/A. Reuse its normalized final04/05/06, not failed CI final structures.
- Peak05 triad passes electronic, normal-termination, geometry, atom-order/fixed-mask and periodic mapping checks. Actual-coordinate mode review accepted; H50 amplitude0.98415, fixedFe0-17 zero.
- Dimer9833429 submitted once on sunboquan-codex/sbq123; schedulerPEND;32 total ranks,16 per node;ALGO Fast,SIGMA0.20,EDIFF1e-7,EDIFFG-0.02,IOPT2,NSW300.
- This refines local migration peak05; lower peaks01/09 are not proven eliminated. No TS acceptance, frequency, barrier or Grade-A result claimed.

## Lifecycle Status

- Phase: `active`

## One Executable Step

At the next requested checkpoint query LSF9833429 and Dimer OUTCAR/OSZICAR/DIMCAR; distinguish electronic convergence, force/torque/curvature, geometry and scientific validity.

## Submission Boundary

One Dimer authorized and submitted; no duplicate, restart, GPU or frequency calculation automatically authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Dimer technically converged and reviewed; later local frequency and compatible-energy registration require current gates.

## Constraints

- Preserve accepted INT06-MID and MID-FS segments.
- Preserve atom mapping, fixedFe0-17 and SIGMA0.20 compatibility branch.
- 32 ranks,16-per-node cap for this single Dimer;108 ranks belonged to nine-image NEB.

## Authoritative References

- archive/neb9808511_dimer_20261004/user_request.json
- archive/neb9808511_dimer_20261004/stop_receipt.json
- archive/neb9808511_dimer_20261004/scheduler_after.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004/dimer_handoff.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004/mode_review.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004/dimer_mode_validation.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004/submission_preflight.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004/execution_gate_decision.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004/submission_record.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004/scheduler_checkpoint_submission.json
<!-- state-handoff:end current_task -->
