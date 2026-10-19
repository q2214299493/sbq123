<!-- state-handoff:start current_task -->
# Current Task

## Objective

Prepare an evidence-first adsorption training pool and problem-targeted carbon/localFe correction proposal before further training or acceleration claims.

## Current Evidence Snapshot

- Read-only collection of13closed VASP trajectories produced312eligible force frames;reused62prior reviewed frames and3actualML failure-boundary labels.No VASP rerun or GPU action.
- After3cross-split near-overlap exclusions and4same-job geometry/force redundancy exclusions,the pool contains248train,60development,46newtest and16quarantined observedheldout frames.Whole-job partitioning preserved.
- Original24frames exactly recovered in geometry/forces/OUTCAR/XDATCAR/raw-table hashes;23retained,one represented by a near-identical neighbor.Original16observedheldout membership and labels unchanged.
- All3before/after/final failedML labels are train candidates,not independent validation.07Cis not an accepted minimum;its24selected electronically converged frames are force-only diagnostic labels.
- Prepared proposed chemical-role weights and source/stage sampler probabilities;actualFairchem runtime integration remains required.No training or checkpoint promotion occurred.
- Compilation,Ruff and30scoped tests passed;canonical manifest and independent13260cross-split geometry comparisons passed.CSV370uniqueIDs matches manifest and train probabilities sum1.

## Lifecycle Status

- Phase: `verification`

## One Executable Step

Review phase1 pool and proposed carbon/localFe loss and source/stage sampler before separately implementing and testing their actualFairchem runtime integration;no GPU training is authorized.

## Submission Boundary

PHASE1_LOCAL_DATA_PREPARATION_ONLY:do not train,infer,promote,submit VASP,stop/resubmit useful jobs or register scientific adsorption results under this scope.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Existing VASP force labels are compatibility/source/coordinate/order/fixed-mask validated and complete.
- Whole-job splits and near-overlap checks preserve original16observedheldout and isolate newtest from train/development.
- Problem-targeted role/sampling proposals,QA evidence and training-not-executed boundaries are reviewable.

## Constraints

- Preserve original VASP data,old pool,failed read/preparation attempts and frozen model checkpoints.Raw force arrays and stored atom order are unchanged.
- No gradient or epoch/weight selection on heldout;three related failure labels are not heldout.Old16was previously observed,not a fresh blindtest.
- Newtest09C/10Awas previously candidate-screened.C2H3currently has test-only coverage;running10B/10Cexcluded.No universal adsorption or TS transfer claim.
- Proposed role weights2:1:1:2:1 and3A radius are trial settings,not calibrated physical gates.CurrentFairchem does not consume proposed_* fields.ActualVASP steps/time benefit remains unmeasured.
- MZ73is GPU backend and sunboquan-codexis VASP backend;work owns all review/authorization.

## Authoritative References

- configs/execution_backends.yaml
- docs/reviews/fe110_adsorption_pool_rebuild_20261019.md
- archive/fe110_adsorption_pool_rebuild_20261019/request_scope.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_pool_rebuild_20261019_v1/prepared_v2/training_manifest.json
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_pool_rebuild_20261019_v1/prepared_v2/training_adjustment_review.json
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_pool_rebuild_20261019_v1/prepared_v2/verification_receipt.json
<!-- state-handoff:end current_task -->
