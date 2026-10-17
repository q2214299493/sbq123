<!-- state-handoff:start current_task -->
# Current Task

## Objective

Review the completed six-candidate MatRIS adsorption GPU trial before deciding on any further comparison; preserve the existing15 VASP calculations.

## Current Evidence Snapshot

- User explicitly authorized one direct GPU2 trial:06_C,07_B,07_C,08_A,09_A,10_A;80 steps each,fmax0.10,max1800s;no VASP/training/default promotion.
- Provider-baseline MatRIS SHA1e6a85b33db075ad1637eca7537084024a694b1340358911212d8a5c518c6601;all source seeds identical to the prior AQCat batch.
- Direct run PID2398967 completed exit0 in59.653618s;canonical receipts and all6 outputs preserved;actual CUDA GPU2 UUID verified.
- All6 schema/source/cell/order/fixed-layer checks pass;5 ML-force-converged and5 original graphs preserved.06_C stopped at80 steps,fmax0.275277 and predicted CO+C+H.
- MatRIS ML steps exceed matched AQCat steps on all6 seeds;downstream VASP force agreement and acceleration are not measured. No model promoted.
- All15 existing VASP jobs9848799-9848813 remain untouched and are carried in backlog for monitoring/final eligible-result registration;not freshly polled in this GPU-only turn.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Present the six predicted outcomes for user review; obtain separate authority before any new MatRIS→VASP comparison, further GPU run or training.

## Submission Boundary

Only the completed six-candidate GPU2 trial was authorized. No automatic retry,new VASP,training,model promotion,service modification or existing-job stop.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- All6 canonical outputs and exact source/model/device/geometry reviews are preserved without DFT acceptance claims.
- User has reviewed the trial and selected a next scoped action or closed this model trial without promotion.

## Constraints

- 06_C is a changed-chemistry,not-ML-converged prediction;do not label it as intact C-O-CH or as a final DFT state.
- Existing VASP results retain their own completion/chemistry/compatibility/registry workflow;GPU trial cannot replace it.

## Authoritative References

- configs/execution_backends.yaml
- modules/adsorption_workflow/README.md
- docs/reviews/fe110_matris_adsorption_trial_20261018.md
- calculations/fe110_c2_adsorption_06_10_20261012/matris_direct_v1/returned_review.json
<!-- state-handoff:end current_task -->
