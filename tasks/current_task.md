<!-- state-handoff:start current_task -->
# Current Task

## Objective

Prepare a problem-targeted adsorption force-training comparison after validated role/sampling runtime integration,without inferring model quality from code tests.

## Current Evidence Snapshot

- 124local scoped tests passed,with compilation/Ruff and independent evidence checks. Legacy unweighted request/database behavior preserved.
- Real248train/60developmentASEDB roundtrip preserves all raw forces,atom order,fixedFe0-17,zero tags,role weights and sampling probability row alignment. Original phase1manifest SHA6deb86d4fcb2bfbde29f7d2d6faf3f2663afa2ac04c9d8a79659c876e6234330 unchanged.
- Opt-in RoleForceTrainer consumes per-atom weights,source/stage sampling metadata and grouped physical-unit development/replay metrics. V3 rejects old/default trainer or omitted role fields/runtime sources.
- MZ73 actualFairchem CPU test used3train/3validation synthetic fixtures:registry selection,dataset factory,shuffledSubset mapping,sampler,collater,normalized loss and physical metrics passed. No actual structures uploaded,no force model instantiated,no modelcheckpoint loaded or written,CUDA uninitialized.
- CPU FP16/BF16 regressions exposed a new-adapter mixed-dtype dot-product bug;fixed by at-leastFP32 loss arithmetic and retaining metadata precision. Failed fixture/API and regression evidence preserved;not a cause claim for old2185 scientific force errors.
- No GPU training,inference,newVASP,checkpoint promotion or acceleration claim. ActualGPU kernels/fullmodel optimizer behavior remain untested.

## Lifecycle Status

- Phase: `verification`

## One Executable Step

Prepare a reviewed runtime-v3 bounded training comparison package with frozen initialization,data/runtime hashes,grouped development selection,budget and actualCLI/PYTHONPATH preflight;do not execute GPU training without separate authority.

## Submission Boundary

CPU_ADAPTER_TESTING_COMPLETE_ONLY:noGPU training/inference,newVASP,oldjob mutation,checkpoint promotion or accepted scientific registration authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Role-weighted force objective and source/stage sampler are consumed by explicit actualFairchem adapter rather than unused configuration.
- Raw-label/weight database roundtrip,normalization,fixed gradients,mixed precision,resume and legacy regression tests pass.
- No-model CPU test evidence and remaining actualGPU/model-accuracy/speedup boundaries are recorded before a new training request.

## Constraints

- Default/deployed Fairchem and old packages remain unchanged;new adapter is explicit opt-in and no new submitted training package yet exists.
- Keep46newheldout and16observedheldout outside training and epoch selection;three actualML boundary labels are train candidates,not independent validation.
- Role values come from reviewed per-frame metadata,not copied atom IDs or universal2:1:1:2:1/3A rules. Fixed atoms receive zero loss and gradient.
- Weighted sampling is single-process and with replacement;an epoch has dataset-length draws,not guaranteed unique visits. C2H3still has test-only coverage.
- CPU AMP tensor tests do not establish GPU full-model AMP safety or any scientific force/geometry/acceleration improvement. O/H/replay metrics exist but training curves/retention decisions remain untested.

## Authoritative References

- configs/execution_backends.yaml
- docs/reviews/fe110_adsorption_role_runtime_tests_20261019.md
- scripts/adsorption/force_finetune.py
- scripts/adsorption/force_role_data.py
- scripts/adsorption/force_role_runtime.py
- scripts/adsorption/role_force_trainer.py
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_runtime_test_20261019_v1/verification_receipt.json
<!-- state-handoff:end current_task -->
