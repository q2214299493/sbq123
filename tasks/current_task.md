<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete earlier IS-A to MID H surface migration through validated intermediate and TS evidence.

## Current Evidence Snapshot

- INT06 VASP9748648 accepted as mapped C2HO*+H* endpoint; final TOTEN -388.50564344eV, fmax0.0177274761eV/A.
- GPU1517 complete five-frame path reviewed: H50 surface migration, C2HO intact, fixed18Fe and endpoint identity preserved; both models select02. ML values remain predicted candidates.
- User approved direct reviewed-GPU-to-Dimer entry on2026-09-10. New gpu_ml_neb_reviewed_path removes mandatory VASP triad/force agreement for candidate entry only; geometry/source/periodic/chemical/MODECAR and execution gates remain required.
- Dimer9749920 submitted through canonical gate on sunboquan-codex,80cores,Gkn_normal. Checkpoint2026-09-10T11:49:52Z LSF PEND; electronic/ionic progress not yet established.
- MODECAR from exact01/03 neighbors: H50 norm fraction0.97782757, fixed18Fe zero; numeric and visual review passed. Input and authorization gates passed;29 registry records inserted.
- Dimer convergence and frequency validation remain required before accepting TS; no migration barrier established. IS-A->INT06 remains unresolved; do not infer exactly two TS.
- Previously accepted MID->FS O-H TS and1.28582718eV forward electronic barrier remain complete; do not repeat.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Monitor VASP Dimer9749920 at sunboquan-codex:~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_dimer_gpu1517_20260910; inspect convergence and mode before frequency handoff.

## Submission Boundary

One Dimer9749920 submitted under explicit user authority; no automatic retry, additional submission or TS acceptance.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Independent valley relaxation and geometry reviewed; then define scientifically supported migration segments.

## Constraints

- Same H50 moves; preserve SIGMA0.20 and bottom18Fe fixed.
- Do not rerun MID-to-FS O-H work.

## Authoritative References

- docs/reviews/gpu1517_direct_dimer9749920_20260910.md
- docs/reviews/valley9748648_accepted_20260910.md
- docs/reviews/oh_ts_accepted_barrier_20260910.md
<!-- state-handoff:end current_task -->
