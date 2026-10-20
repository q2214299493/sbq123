<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete the authorized three-pair VASP relaxation benchmark and compare compatible same-minimum cost,without model promotion.

## Current Evidence Snapshot

- User explicitly authorized exact six prepared jobs;all source/bundle hashes and remote POTCAR family/order/SHA passed;canonical SUBMIT_VASP gates and executor used.
- 06_C baseline9910781/control9910783 RUN;09_C baseline9910785/control9910787 PEND;10_A baseline9910789/control9910791 PEND at2026-10-20T07:13:59Z.
- Each32MPIranks,32/node,NSW300,unchangedproductionALGO Fast/SIGMA0.20/EDIFFG-0.02;existing128rankaccountquota respected.No pilot or old-job cancellation.
- Six immutable submission receipts and scheduler raw/hash evidence;registry96newjob/input rows(6calculations+6jobs+6history+78files),zero scientific results.
- Scheduler schema gained adsorption_relaxation metadata only;first reporting error did not affect submissions,no resubmit.122related regressions pass.
- No electronic/ionic convergence,final basin,elapsedcost or measuredspeedup assessed;no newGPU/training/modelpromotion.

## Lifecycle Status

- Phase: `active`

## One Executable Step

At the next requested checkpoint inspect these six live scheduler/calculation sources;compare convergence and compatible final minima before performance accounting.

## Submission Boundary

Exact six submissions consumed.No automaticretry,newVASP,newGPU,parameter/geometrychange,training or modelpromotion authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Each of six jobs has terminal scheduler evidence and separately reviewed electronic/force/geometry status.
- Compatible same-minimum pairs compare ionicsteps,totalSCFwork,elapsedtime,CPUcorehours and GPU/sharedcost;different minima or failures are not speedup ratios.
- Qualified converged adsorption results are registered through owning scientific gates;unqualified cases retain truthful status.

## Constraints

- Freeze both checkpoints and all six submitted inputs;no result-driven checkpoint/epoch reselection.
- 06_C training-source/site-difference/transientelongation and09_Cmixedgeometry warnings remain;no blanket success.
- Old131/101/114-step jobs are not exact matched controls;no speedup claim before final scientific review.
- Do not affect other running jobs or11-15preparation;do not bypass accountquota or auto-retry.
- Routine checks remain on demand;no recurring monitor was created.

## Authoritative References

- configs/execution_backends.yaml
- configs/true_fe110_production.yaml
- docs/reviews/fe110_adsorption_control_paired_vasp3_submission_20261020.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/submission_summary.json
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/submission_registry_receipt.json
<!-- state-handoff:end current_task -->
