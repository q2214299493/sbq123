<!-- state-handoff:start current_task -->
# Current Task

## Objective

Review the completed fifteen CUDA adsorption candidate structures and duplicates before a separately authorized VASP handoff.

## Current Evidence Snapshot

- CUDA direct v3 producer exit0/all15 completed; elapsed138.303s; parent121917 exited. No Slurm job ID.
- All15 model-device/UUID bindings, return manifests, remote/local output hashes and producer structure invariants pass; original CPU outputs preserved.
- All15 reach unchanged ML fmax0.10 within19-74steps;12 retain expected graph/H placement;06_A/06_B/09_B flagged for chemical review.
- Canonical completion records GPU workflow done with scheduler UNKNOWN/NONE; predictions remain outside accepted energy tables. No VASP, model promotion or VASP speedup claim.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Review all15 final predicted structures and surface-aware duplicates; specifically diagnose06_A/06_B hydrogen connectivity and09_B graph change before selecting any VASP candidates. Do not remove evidence-required motifs based only on ML.

## Submission Boundary

Already authorized exact GPU1 batch only; do not duplicate launch, change shared services/others jobs, submit VASP or accept predicted values as DFT.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Actual GPU execution remains bound to CUDA tensor/UUID, source checkpoint and immutable input hashes.
- All fifteen outputs and producer exit evidence are collected and reviewed for ML convergence, chemistry/geometry and duplicates; scientific acceptance stays separate.

## Constraints

- Keep prior CPU outputs and all source versions; no invented scheduler DONE or numeric job ID.
- A predicted optimizer pass is not a stable adsorption minimum or reportable energy; downstream VASP needs separate authorization.

## Authoritative References

- configs/execution_backends.yaml
- modules/adsorption_workflow/README.md
- modules/calculation_registry/README.md
- docs/reviews/fe110_c2_cuda_restart_20261013.md
<!-- state-handoff:end current_task -->
