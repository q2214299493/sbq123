<!-- state-handoff:start current_task -->
# Current Task

## Objective

Use completed frozen2185 validation evidence to improve adsorption acceleration without promoting a chemically unreliable raw-seed optimizer.

## Current Evidence Snapshot

- User authorized validation;only one GPU1 direct run v2 executed;actual model PID2578442 on cuda:0;producer exit0 after22.34s;59 returned files hash-verified.
- Frozen16 frames from2whole heldout jobs:adsorbate force vectorRMSE0.234745→0.106876eV/A(-54.5%);all reported Fe/C/O/H groups improve;no training or epoch selection.
- Same-seed adsorbate RMSD to the same existing DFT reference:06_C0.866→1.694A with CO+C+H prediction;07_B1.623→1.595A;08_A0.956→0.611A. Geometry is mixed,not general acceleration success.
- Minimum-start drift is small underML fmax0.10,but candidate06_C/07_B stop at0steps;do not interpret this as equality of DFT and ML stationary points.
- Failure case saved:06_C target motif lost;DFT error at the failed ML geometry remains unmeasured;model error versus basin selection is unresolved.
- Existing24 compatible DFT frames remain untrained. Local next-force-comparison plan only;no new VASP or automatic training,default-model change,or retry.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Prepare a bounded exact-structure baseline/candidate force comparison on the existing24DFT frames,prioritizing06_C off-equilibrium;obtain new GPU authorization before execution,then decide whether fine-tuning is justified.

## Submission Boundary

The authorized16heldout/3geometry GPU validation has finished. No further GPU/VASP/training/promotion is authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Completed frozen validation force/geometry evidence and the06_C failure case are preserved without an acceleration/global-stability claim.
- New-domain exact-structure errors are reviewed before selecting a targeted adaptation or alternative pre-relaxation strategy.
- Any adopted acceleration is ultimately checked against compatible matched VASP steps/time and reviewed final chemistry.

## Constraints

- Do not use the observed16heldout frames for gradients or retrospective epoch choice.
- LowML force alone does not preserve an adsorption motif;06_C failed-target prediction cannot replace its intactDFT reference.
- Do not change VASP parameters,other jobs,backend roles or existing checkpoints. MatRIS remains an optional audit model.

## Authoritative References

- configs/execution_backends.yaml
- modules/adsorption_workflow/README.md
- docs/reviews/fe110_adsorption_validation_2185_20261018.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_validation_2185_20261018_v2/validation_review.json
<!-- state-handoff:end current_task -->
