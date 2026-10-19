<!-- state-handoff:start current_task -->
# Current Task

## Objective

Review bounded adsorption force-training comparison;execute GPU only after separate exact-hash user authorization.

## Current Evidence Snapshot

- Prepared comparison SHA f5db5cb7b1e98d6153bba8bbc41a0d0697fd29c79162a4ef0298a91969660987:control dbad960b964805277333d21bce0a1669e38085c9ab742f5ed53a88a9a5b2d026;treatment 8b740e698d2bac32bb9f918012372a1aaf4e410d9bfef61397bb55ce95ab69ca.
- Both arms freeze originalAQCat25 e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50,identical248train/60development structures/forces,and common role-aware development epoch selection.Control train weights/probabilities only are derived;original pool and treatment manifest bytes unchanged.
- Each arm max2epochs/496optimizersteps/30minutes,oneGPU/4CPU/32GB,seed42,lr1e-5;sequential proposed total60GPUminutes.No automatic retries or promotion.
- 137scoped tests passed plus compile/Ruff/Bash and independent package hash/label/design checks.NativeMZ73 CLI/config/registry passed using RAM modules;no actual labels uploaded,model loaded,CUDA initialized or remote files written.
- Actual native eval_every is optimizer-step cadence;new arms validate/checkpoint once per248step epoch,instead of inherited per-step validation.No actual training or accuracy/speedup result exists.

## Lifecycle Status

- Phase: `verification`

## One Executable Step

Obtain user review of the two-arm initialization/design/budget,then separate exact-arm-hash deployment/GPU authorization;do not infer execution authority from prepared-package checks.

## Submission Boundary

PREPARED_FOR_REVIEW_ONLY:no GPU training/inference,private dataset upload,new VASP,oldjob mutation,model promotion or scientific registration authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Two arms bind identical physical labels/splits/initialization with only reviewed training-weight and sampling differences.
- Bounded budget,actual CLI and namespace packaging,raw DB/role alignment and scoped regressions are checked.
- Exact request hashes,no-model evidence and remaining GPU/scientific boundaries are provided for user review.

## Constraints

- Default/deployed Fairchem and old packages remain unchanged;runtimev3 is explicit opt-in.
- Keep46newheldout and16observedheldout outside gradients/epoch choice;integrity reads only,noheldoutDB or model loader.C2H3has test-only coverage.
- Common original initialization is a proposal rather than proved better than2185;combined weighting+sampling comparison cannot isolate each component.
- Single seed/twoepochs is a bounded experiment,not proof of training convergence or acceleration.O/H/replay regressions are review warnings;no zero-tolerance promotion gate.
- On-disk deployment/PYTHONPATH,baseline checkpoint,current scheduler/GPU and full-model AMP/optimizer preflight remain required after authority.Old direct-execution exceptions cannot authorize this package.

## Authoritative References

- configs/execution_backends.yaml
- docs/reviews/fe110_adsorption_training_comparison_20261019.md
- scripts/adsorption/force_training_preflight.py
- scripts/adsorption/role_training_job.sh
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_comparison_20261019_v1/comparison_request.json
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_comparison_20261019_v1/verification_receipt.json
<!-- state-handoff:end current_task -->
