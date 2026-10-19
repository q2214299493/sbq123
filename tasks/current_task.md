<!-- state-handoff:start current_task -->
# Current Task

## Objective

Review the completed corrected adsorption training comparison;retain development versus heldout and measured-acceleration boundaries.

## Current Evidence Snapshot

- User“修复好再跑一次” explicitly authorized one new corrected attempt.New v2 hashes preserve original physical labels,splits,recipes and base checkpoint;v1 failure untouched.
- Both actual MZ73 CPU/native CLI/checkpoint preflights and180scoped regressions pass.Only coordinate decoding uses1e-12A tolerance;raw forces/cell/PBC/roles and source hashes exact.
- Both control and treatment ran on physicalGPU1 UUID450609b3;each completed2epochs/496native iterations and exited0.Each same-process startup receipt proves two real optimizer updates and exact-zero energy-head gradients.
- The DDP integration failure is repaired in actual full-model GPU training.Not evidence of model transferability or actual VASP speedup.
- Native development metrics are available in verification_receipt.json;they are rounded training-selection metrics,not independent heldout results.46newheldout and16observedheldout remain excluded.
- Both candidate checkpoints remain unpromoted;no newVASP,extra GPU inference,automatic retry or production replacement authorized.

## Lifecycle Status

- Phase: `verification`

## One Executable Step

Review grouped development/retention results,then prepare an exact-hash independent validation proposal for the chosen frozen candidate without running it yet.

## Submission Boundary

ONE_CORRECTED_RETRY_COMPLETED:compute authority consumed.No further training,heldout GPU evaluation,promotion or VASP without its own scope and authorization.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Returned producer evidence and same-process native CUDA checks establish both bounded training runs completed.
- Grouped development comparison distinguishes combined recipe effects from independent validation.
- A chosen frozen candidate has a reviewable independent-validation proposal;no acceleration claim without a matched VASP benchmark.

## Constraints

- Preserve v1 failures and v2 immutable package/checkpoints;no old-package hot patch.
- 46newheldout and16observedheldout are excluded from training and epoch selection;no unseen-domain or C2H3 training claim.
- Energy output is untrained;force-only candidate energies cannot enter scientific tables.
- No automatic retry,production promotion or measured VASP acceleration claim.

## Authoritative References

- configs/execution_backends.yaml
- docs/reviews/fe110_adsorption_training_retry_20261020.md
- archive/fe110_adsorption_training_retry_20261020/scope.md
- scripts/adsorption/direct_training_arm.py
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_direct_20261020_v2/verification_receipt.json
<!-- state-handoff:end current_task -->
