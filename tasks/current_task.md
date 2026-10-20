<!-- state-handoff:start current_task -->
# Current Task

## Objective

Prepare a matched three-pair VASP steps/time benchmark without changing the production model or submitting calculations.

## Current Evidence Snapshot

- Six reviewed seed-origin final POSCARs:06_C/09_C/10_A x original AQCat25/frozen uniform-control;no minimum-drift starts.
- Canonical routine-production builder,32ranks/job,32/node,ALGO Fast,SIGMA0.20,EDIFFG-0.02,NSW300;within-pair method/resource files byte-identical.
- 6/6unified adsorption preflights pass;source/return/POSCAR hashes,cell/order/fixedFe0-17 and final graph checked;22related tests pass.
- 06_C transient C-O elongation/site difference and09_C mixed geometry warning retained;not automatic same-basin acceptance.
- All inputs local only,no job IDs,no upload,newVASP0,newGPU0;POTCAR still needs fresh remote verification.
- Historical131/101/114steps are not exact matched controls;VASP savings unmeasured.No checkpoint promotion.

## Lifecycle Status

- Phase: `verification`

## One Executable Step

Obtain separate explicit authority for the exact six prepared VASP inputs before generating a current submission gate and checking remote POTCAR/duplicates.

## Submission Boundary

PREPARED_LOCAL_ONLY:execution_authorized=false;ALLOWED_ACTIONS=[];no upload or submission authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Explicit exact-six-job submission authorization,current hash-bound gate and live remote input/POTCAR checks exist before execution.
- Each run is reviewed for termination,electronic/force convergence,chemical identity and final adsorption basin.
- Only compatible same-minimum pairs compare ionic/SCF work,time,CPU/GPU and declared shared costs before a speedup claim.

## Constraints

- Freeze the candidate;no geometry-test-driven checkpoint/epoch reselection.
- 06_C is in-domain training-source diagnostic;09_C/10_A are observed after force validation,not fresh blind selection.
- Treat06_C transient elongation and09_C mixed results as warnings,not arbitrary hard rejection or blanket success.
- Retain other11-15 structure-preparation files/event in backlog;no actions on that branch.
- No automaticpilot/retry or model reselection;no unrelated11-15task changes.
- Six simultaneous jobs would require192ranks;concurrency and real runtime remain unapproved/unmeasured.

## Authoritative References

- configs/true_fe110_production.yaml
- configs/execution_backends.yaml
- docs/reviews/fe110_adsorption_control_paired_vasp3_20261020.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/batch_manifest.json
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/preparation_receipt_v2.json
<!-- state-handoff:end current_task -->
