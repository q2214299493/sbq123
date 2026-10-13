<!-- state-handoff:start current_task -->
# Current Task

## Objective

Repair and verify actual GPU execution for the user-authorized fifteen adsorption candidates; preserve the independent CPU trial evidence.

## Current Evidence Snapshot

- Direct trial run ID direct-fe110-c2-0610-20261013-v2, PID114670, scheduler NONE/job ID null; exact launch records and registry receipts exist.
- Copied patched_calc omitted cpu=False; deployed OCPCalculator defaults cpu=True. LBFGS activity is CPU execution, not verified GPU acceleration.
- Explicit cpu=False and model tensor CUDA/UUID assertions prepared in v3 source; current scoped syntax/Ruff/25 device-backend-handoff tests pass. CUDA loading/inference not tested.
- Separate user question asks permission to stop only the CPU trial and its children, retain outputs, then freeze/preflight the corrected GPU1 package. No stop performed.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Obtain explicit authority to stop the active CPU trial, verify its PID/process group, then freeze and preflight a fresh CUDA-corrected v3 GPU1 request before launching. If it already ended, preserve its exit evidence and resolve the corrected rerun authority.

## Submission Boundary

Only fifteen original candidates and original checkpoint; no VASP, other user process, service restart, fake scheduler ID, model promotion or unapproved termination.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Actual requested GPU execution is demonstrated by CUDA model tensor binding, physical GPU UUID and live process evidence.
- All fifteen predicted outputs and producer exit records return for work-side chemical/geometry/duplicate review; never infer scientific acceptance from producer completion.

## Constraints

- Preserve v1 preflight failure, v2 CPU outputs and all immutable hashes.
- Do not relabel current CPU execution as GPU acceleration or extrapolate it to all historical GPU tasks.

## Authoritative References

- configs/execution_backends.yaml
- scripts/adsorption/direct_gpu_batch.py
- modules/adsorption_workflow/README.md
- docs/reviews/fe110_c2_direct_gpu_attempt_20261013.md
<!-- state-handoff:end current_task -->
