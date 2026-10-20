<!-- state-handoff:start current_task -->
# Current Task

## Objective

Review completed paired geometry comparison and prepare a matched VASP steps/time benchmark for separate authorization;no default model promotion.

## Current Evidence Snapshot

- One authorized GPU1 batch:3cases x2models x2origins=12short optimizations,26.54s,producer exit0;no training or VASP.
- Exact raw seeds and converged DFT references06_C/09_C/10_A,Fe0-17fixed;seed80steps/MLfmax0.10,minimum20steps/MLfmax0.02.
- Seed adsorptionRMSD baseline->control:06_C0.865754->0.435064,09_C0.310857->0.330731,10_A0.297582->0.188551A.Mixed,not blanket improvement.
- Candidate minimum drift06_C~0A/0steps,09_C0.091542A/20steps/fmax0.046635 not converged,10_A0.000886A/2steps.
- All12 final graphs preserved.389trajectory frames fixed atoms unchanged,max adjacent displacement0.20A;06_C both models transient C46-O47~1.85-1.87A then recover.
- JSON list/tuple graph-flag bug corrected in v2local analysis;original report/source retained and no GPU rerun.82related tests pass.
- Historical DFT started at older ML outputs,not exact current raw seeds;old131/101/114steps do not prove matched speedup.No default replacement.

## Lifecycle Status

- Phase: `verification`

## One Executable Step

Prepare/review three baseline/control paired VASP relaxation inputs at the unchanged production branch;only submit with separate explicit authority.

## Submission Boundary

GPU_GEOMETRY_COMPARISON_COMPLETE_ONLY:no new VASP,training,relaxation rerun or checkpoint promotion authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Geometry/source/trajectory warnings are retained in the review.
- Matched VASP scope/resources/cost receive separate authorization before execution.
- Compatible final states,ionic steps,SCF work and total cost are compared before an acceleration claim.

## Constraints

- Freeze the candidate;no geometry-test-driven checkpoint/epoch reselection.
- 06_C is in-domain training-source diagnostic;09_C/10_A are observed after force validation,not fresh blind selection.
- Treat06_C transient elongation and09_C mixed results as warnings,not arbitrary hard rejection or blanket success.
- Retain other11-15 structure-preparation files/event in backlog;no actions on that branch.

## Authoritative References

- configs/execution_backends.yaml
- docs/reviews/fe110_adsorption_control_geometry3_20261020.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_geometry3_20261020_v1/geometry_comparison_review_v2.json
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_geometry3_20261020_v1/validation_receipt.json
<!-- state-handoff:end current_task -->
