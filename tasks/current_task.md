<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete the adsorption training comparison after fresh corrected-runtime binding and renewed GPU authority;do not infer success from CPU tests.

## Current Evidence Snapshot

- User“跑” authorized GPU1 direct mode with unchanged2epoch/496step/30min-per-arm,total60min,no-retry scope.Backend policy adds only this exception.Direct request b0cc4cf03ee9e2fd52fa0c7deb86f204e771b15263be8001af703f29af7d6203 preserves all original bound arm artifacts.
- Both on-disk/nativeCPU preflights pass with supplementary hash-bound coordinate-decoding allowance1e-12A;observed cross-platform difference1.776e-15A.All cell/PBC/rawforces and source hashes remain exact.No geometry optimization or data change.
- Actual direct controllerPID2888886/controlPID2888895 ran2026-10-20 00:22:34–00:22:52CST;actual model parameters CUDAcuda:0 on physicalGPU1 UUID450609b3.Producers exited1 before a completed epoch;no candidate,treatment or automatic retry.
- Native error lists9unused tensors374–382;CPU mapping confirms all are output_heads.energy.*.New force-only role loss omitted their graph dependency;native one-rank DDP rejects the next forward.This is adapter integration failure,not evidence of model accuracy.
- Source fix adds exactly-zero energy-output graph dependency without energy fitting.NativeCPU toyDDP reproduces old failure after1step and passes2fixed steps with identical force loss/gradients;corrected roleSHAaf3019d8755bb3a91bf2c97dae5c491f60dc8d90bb4792773cb1fb6cb2e4a90e.Not deployed/retried for AQCat25GPU.
- 174scoped regressions plus compilation/Ruff pass;11original producer/diagnostic/log files returned byte-exact with remote SHA verification.Source/failed runtime and logs preserved.No model promotion,heldout model evaluation,newVASP or speedup claim.

## Lifecycle Status

- Phase: `blocked`

## One Executable Step

Bind the corrected role runtime into fresh reviewed arm/direct requests and obtain renewed GPU execution authority;then verify consecutive native forward/backward steps within the same bounded training process.No old-package hot patch or automatic retry.

## Submission Boundary

DIRECT_V1_AUTHORITY_CONSUMED_BY_FAILED_FIRST_ATTEMPT:correctedGPU relaunch,newVASP,model promotion,extra budget and automatic retries are not authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Fresh corrected-runtime/source and data bindings pass actual native preflight and explicit authority checks.
- Both bounded arms complete actualCUDA forward/backward training and return producer/checkpoint evidence without heldout epoch selection.
- Grouped development review truthfully distinguishes candidate quality from independent validation and measured VASP acceleration.

## Constraints

- Preserve all old frozen packages,source data and failure evidence;do not overwrite or reuse old launch markers.
- Keep46newheldout and16observedheldout out of gradients/epoch selection;no independent validation claimed for training failure structures.
- The zero energy graph dependency is a DDP execution fix,not an energy-loss/DFT/geometry/weighting change.
- CPU toyDDP success does not establish corrected full-model GPU/AMP behavior or scientific acceleration.
- No automatic retry;new corrected compute requires fresh request hash authorization.

## Authoritative References

- configs/execution_backends.yaml
- docs/reviews/fe110_adsorption_direct_training_20261020.md
- archive/fe110_adsorption_direct_training_20261020/scope.md
- scripts/adsorption/role_force_trainer.py
- scripts/adsorption/direct_force_training.py
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_direct_20261020_v1/verification_receipt.json
<!-- state-handoff:end current_task -->
