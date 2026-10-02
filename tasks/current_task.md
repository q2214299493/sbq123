<!-- state-handoff:start current_task -->
# Current Task

## Objective

Monitor CI-NEB9826728 for IS-A9725473 -> INT06_9748648 H migration.

## Current Evidence Snapshot

- Parent ordinary NEB9808511 is DONE; all nine internal images completed normally with final electronic convergence, 71 steps and maximum final NEB force0.049947 eV/A.
- Final structures were recovered with OUTCAR/OSZICAR/XDATCAR. Integer lattice translations only remove Fe periodic branch wrapping; atom order, fixedFe0-17 and physical structures are retained. Normalized geometry PASS; maximum adjacent atom displacement0.401628 A.
- Actual TOTEN maximum is image05. Lower peaks01 and09 remain diagnostic migration features; this refinement does not claim a single elementary TS for the whole multi-peak path.
- VTST dist.pl and nebmovie.pl0 completed; numeric and actual-coordinate visual review accepted. CI preflight and current hash-bound ENABLE_CI_NEB execution authorization pass.
- CI-NEB9826728 submitted once on sunboquan-codex/sbq123, statusPEND; nine internal images,108 MPI ranks,12 per image,NPAR4,per-node cap16; LCLIMB true,IOPT1,EDIFFG -0.02,ALGO Fast,SIGMA0.20,NSW300.
- No final TS, virtual frequency, electronic barrier or Grade-A acceptance is claimed for this migration segment yet.

## Lifecycle Status

- Phase: `active`

## One Executable Step

At the next requested checkpoint query LSF9826728 and the canonical compact NEB monitor for ~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_is_a_int06_ci9808511_sbq123_108r_20261002; distinguish queue state, electronic convergence, CI/NEB forces, geometry and scientific validity.

## Submission Boundary

One CI refinement authorized and submitted. No duplicate, restart, new GPU, Dimer or frequency submission without current evidence and user authority.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- CI path is technically converged and reviewed; later frequency validation and compatible-energy registration require their own gates.

## Constraints

- Preserve accepted INT06-MID and MID-FS segments.
- Preserve atom mapping, fixedFe0-17 and SIGMA0.20 compatibility branch.
- 108 total ranks retained with16-per-node cap and12 per internal image.
- CI climbs the currently highest internal image dynamically; initial maximum05 does not lock image05 forever.

## Authoritative References

- archive/ci_neb9808511_20261002/user_request.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_ci9808511_sbq123_108r_20261002/parent_scheduler_evidence.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930/normalized_final_path_20261002/normalization_receipt.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_ci9808511_sbq123_108r_20261002/completed_parent_analysis.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_ci9808511_sbq123_108r_20261002/path_review.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_ci9808511_sbq123_108r_20261002/submission_preflight.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_ci9808511_sbq123_108r_20261002/execution_gate_decision.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_ci9808511_sbq123_108r_20261002/submission_record.json
- calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_ci9808511_sbq123_108r_20261002/scheduler_checkpoint_submission.json
<!-- state-handoff:end current_task -->
