<!-- state-handoff:start current_task -->
# Current Task

## Objective

Execute the authorized bounded adsorption training comparison after resolving verified runtime blockers within explicit authority.

## Current Evidence Snapshot

- User“运行” authorized comparison f5db5cb7b1e98d6153bba8bbc41a0d0697fd29c79162a4ef0298a91969660987 and both exact arm requests.Separate immutable authorization files created;frozen package/artifacts unchanged.
- MZ73 live2026-10-19T14:32:29Z:slurmctld/slurmd failed;sinfo exit1 controller unreachable;squeue12second timeout.Scheduler state unavailable,not proof of an empty queue.
- GPU1 RTX4090 has24066MiB free,0percent utilization at the snapshot;not reserved.Baseline checkpoint hash matches e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50.
- Declared /home/sbq/sbq resolves to /home/ubuntu/hdd/sbq/sbq;frozen helper requires the alias resolve to itself and rejects it.Target package absent.No upload,sbatch attempt,remote file write,training or inference.
- 143scoped tests pass plus compilation/Ruff.Explicit UTF8 fixed a local authorization-read failure before SSH;authorization was not recreated and no compute retry occurred.

## Lifecycle Status

- Phase: `blocked`

## One Executable Step

Obtain explicit scope for a new bounded GPU1 direct-execution package with reviewed canonical-directory handling,or administrator-restoredSlurm plus corrected-wrapper review;do not submit unchanged or reuse old direct exceptions.

## Submission Boundary

EXACT_ORIGINAL_SLURM_PACKAGE_AUTHORIZED_BUT_PRECHECK_BLOCKED:alternative direct execution,service restart,other users'GPU/process changes,newVASP,extra budget,retries and model promotion are not authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Authorized deployment/runtime and realGPU preflight pass with fresh exact hashes and correct boundary checks.
- Both arms execute sequentially within2epochs/496steps/30min each,total60GPUminutes,and return truthful producer/scheduler evidence.
- Grouped development results and frozen candidate artifacts return to work without heldout-driven epoch selection or automatic promotion.

## Constraints

- Preserve original pool,model/data/splits and all failed/partial evidence.No automatic resubmission or budget expansion.
- Keep46newheldout and16observedheldout outside training/epoch selection.NoVASP or model promotion authority.
- Do not emulate SLURM_JOB_ID or treat previous direct-GPU exceptions as authority for this comparison.
- Canonical path alias handling must be reviewed in a fresh runtime binding,not patched into the immutable original package.
- Code tests/free GPU memory do not establish full-model CUDA/AMP safety,scientific accuracy or actual acceleration.

## Authoritative References

- configs/execution_backends.yaml
- docs/reviews/fe110_adsorption_training_execution_precheck_20261019.md
- archive/fe110_adsorption_training_comparison_20261019/authorization_run_20261019.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_comparison_20261019_v1/comparison_request.json
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_execution_20261019_v1/verification_receipt.json
<!-- state-handoff:end current_task -->
