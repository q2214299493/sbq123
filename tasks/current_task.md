<!-- state-handoff:start current_task -->
# Current Task

## Objective

Review the fourteen completed Fe110 adsorption01–05 structures, surface-aware duplicates and compatibility, and register only fully eligible results.

## Current Evidence Snapshot

- All14 source sets collected and SHA256-verified; all VASP normal termination, final SCF and movable-atom force conditions pass.
- 13 intended graphs/H placements preserved;03_cfg0_direct_vasp reclassifies to CH+CO fragments and is rejected for the original intact target.
- Five surface-aware duplicate sources; eight retained geometric representatives are not a global-minimum or distinct-basin proof.
- Canonical append-only registration and DB readback confirm5 accepted representatives,5 duplicates,1 rejected original target and3 needs_review.
- 02_extra2,04_cfg2,05_cfg1 have valid scientific output but lack required original scheduler DONE evidence; keep UNKNOWN and do not invent acceptance.
- 112 new source-file records,14 reviews,14 compatibility records,14 scheduler observations and10 result records; no duplicate jobs or calculations.
- No adsorption-energy reference tuple, thermal correction, Excel promotion, model promotion or new scientific submission. Prepared06–10 remain deferred.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Resolve the task-scoped acceptance decision for the three scheduler-evidence-pending representatives; recover original DONE evidence or obtain explicit user authority before preparing any policy exception.

## Submission Boundary

Review and registration only; do not submit, restart or alter any GPU/VASP calculation, waive scheduler requirements or promote a checkpoint.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Every original calculation has hash-bound final convergence, chemistry and compatibility review and duplicate disposition.
- Fully eligible representatives have canonical append-only accepted records and successful database readback; exclusions retain truthful status.
- Three missing-scheduler-evidence representatives remain explicitly pending until evidence or separate policy authority exists.

## Constraints

- Use the accepted Fe45 branch, true species order and bottom18 fixed; preserve original source bytes.
- Do not promote fragments as the original graph, duplicate energy rows, arbitrary rotated molecular matches, or inferred adsorption energies.
- Missing LSF history is UNKNOWN, not failure and not an invented DONE.
- 06–10 preparation and the fine-tuning candidate stay in backlog; this task grants no computation authority.

## Authoritative References

- modules/adsorption_workflow/README.md
- modules/calculation_registry/README.md
- configs/true_fe110_production.yaml
- docs/reviews/fe110_c2_01_05_completion_20261012.md
- calculations/fe110_five_c2_adsorption_20261006/final_review_20261012/registration_v2/post_apply_verification.json
- tasks/backlog.md
<!-- state-handoff:end current_task -->
