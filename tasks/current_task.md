<!-- state-handoff:start current_task -->
# Current Task

## Objective

Improve adsorption acceleration using verified force and geometry evidence without promoting an unreliable raw-seed optimizer.

## Current Evidence Snapshot

- User-authorized24-frame force-only GPU1 batch completed;PID2580552 actual cuda:0;producer exit0 after8.59s;nine returned files hash-verified;no relaxation/training/VASP/model change.
- Existing24DFT frames:adsorbate force-vectorRMSE0.225356→0.123129eV/A(-45.36%);all24 individual frame RMSEs improve;Fe/C/O/H pooled groups improve.
- 06_C8-frameRMSE0.199685→0.090909;early steps1/2/5 0.216999→0.121481;intermediate33/66/98 0.194078→0.083371;last130/131 0.179902→0.022261eV/A.
- The24 frames remain untrained but were previously screened,not pristine independent heldout. Previous16heldout validation remains outside fitting and epoch selection.
- Prior06_C raw-seed prediction loses target motif toCO+C+H despite improved forces on successfulDFT trajectory. Actual failedML-boundary DFT forces remain unmeasured;model error versus basin selection is unresolved.
- No measured VASP step/time speedup,no global model promotion,no active GPU run from this diagnostic;82 scoped tests and old-package compatibility verification passed.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Select pre/post motif-loss06_C structures from its already savedML trajectory and prepare a bounded compatible same-structure VASP force-label comparison for review,before deciding another fine-tune.

## Submission Boundary

The one authorized24-frame force-only GPU batch is finished. No further GPU optimization,training,VASP or default-model promotion is authorized;future expensive execution requires separate authority.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Completed frozen-checkpoint force/geometry diagnostics and06_C failure evidence are preserved without a general acceleration claim.
- ActualML failure-boundary DFT force errors are reviewed before selecting targeted adaptation versus a basin/path strategy.
- Any adopted acceleration is checked against compatible matched VASP steps/time and reviewed final chemistry.

## Constraints

- Do not use observed16heldout structures for gradients or retrospective epoch selection;new24 frames remain untrained.
- Force RMSE improvement on successfulDFT trajectories does not establish failedML endpoint stability or prove the cause of motif loss.
- Preserve existing checkpoints,VASP parameters,other jobs and backend roles;no silent model adoption or automatic expensive retry.

## Authoritative References

- configs/execution_backends.yaml
- modules/adsorption_workflow/README.md
- docs/reviews/fe110_adsorption_force24_2185_20261018.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_force24_2185_20261018_v1/force_comparison_review.json
<!-- state-handoff:end current_task -->
