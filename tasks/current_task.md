<!-- state-handoff:start current_task -->
# Current Task

## Objective

Review the frozencontrol independent-validation proposal before any new GPU execution;no default-model replacement or speedup claim.

## Current Evidence Snapshot

- User requested grouped-error review and independent-validation candidate selection.No new GPU inference/training/relaxation or VASP was authorized or run.
- Read-only CPU checkpoint checks confirm baseline/control/treatment hashes and architecture.Candidates omit epoch/step but contain val_metrics.Nativebest bytes match each export.
- Actual export roleMAE:control0.03978188027,treatment0.04030279919eV/A.Treatment improvesC0.97%,O18.43%,replay5.39%,but worsensH36.14%,nearFe9.30%,otherFe19.20%.Soft review warnings,not zero-tolerance rejection.
- Freezecontrol SHA256cfcac123cd56b866a1ea36cc780a3aee634f3aeec979bda4ae8bee2cc831e523 using development only.Single seed/twoepochs is not a statistical-superiority claim.
- Native checkpoint.pt is saved before validation;its best_val_metric lags epoch2.Do not substitute that stale value for actual exported val_metrics.
- Proposalbf2e4a7c745ae6569f69c70a262c8854566d8b6a123592ca123cbfc6dbfe0c92 freezes baseline/control46exact heldout structures,09_C/10_A23each;oldobserved16 excluded.92force predictions proposed,zero executed.Whole-job/equivalence/source-label integrity verified.
- Six directly related tests,compile and scoped Ruff pass.No scientific runtime changed;original proposal and generation source snapshot preserved.

## Lifecycle Status

- Phase: `verification`

## One Executable Step

Present the frozen46-frame force-only baseline/control validation proposal for separate scope/budget approval;only then prepare an executable GPU request/backend binding.No heldout-driven model reselection.

## Submission Boundary

PROPOSAL_ONLY_NOT_EXECUTABLE_NOT_AUTHORIZED:GPU evaluation,training,relaxation,VASP and production promotion remain unauthorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- The frozen candidate/proposal and separate compute budget receive explicit user authorization.
- An exact-hash executable validation package passes native/input/backend preflight before any model prediction.
- Independent results retain per-job/role/failure-tail review and do not substitute for geometry or a matched VASP acceleration benchmark.

## Constraints

- No test-driven candidate reselection or use of46heldout/16observed frames for fitting/epoch selection.
- 46frames represent two correlated trajectories,not46independent environments;mother jobs were screened and baseline pretraining overlap is unknown.
- C2H3 lacks training coverage;candidate energies remain untrained and TS-domain acceptance absent.
- Preserve old packages,checkpoints and source evidence;no automatic retries or production replacement.

## Authoritative References

- configs/execution_backends.yaml
- docs/reviews/fe110_adsorption_candidate_selection_20261020.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_candidate_review_20261020_v1/independent_validation_proposal.json
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_candidate_review_20261020_v1/validation_receipt.json
<!-- state-handoff:end current_task -->
