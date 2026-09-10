<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete earlier IS-A to MID H surface migration through validated intermediate and TS evidence.

## Current Evidence Snapshot

- 9748648: LSF DONE; ordinary valley06 relaxation completed in 79 steps; electronic and force criteria passed (0.0177274761 eV/A < 0.020).
- INT06 accepted as intact C2HO* + H* mapped migration endpoint; final TOTEN -388.50564344 eV under fe110_converged_toten_sigma0p20_v1.
- Schema9 registry completion applied: 12 inserted records and one workflow projection change; receipt in h_migration1357_valley06_relax_20260909/completed_review_20260910/registry_receipt.json.
- IS-A -> INT06 and INT06 -> MID are two path intervals awaiting TS evidence; image02 remains an unresolved first-interval ML minimum.
- The previously accepted MID -> FS O-H TS and 1.28582718 eV forward electronic barrier remain complete; do not repeat.
- No new NEB/Dimer/frequency/static/GPU calculation submitted; no Hessian, exhaustive symmetry equivalence or complete migration-barrier claim.
- INT06 -> MID GPU-first preparation corrected: five-frame MatRIS ML-NEB + exact-fixed-path AQCat25 request staged on MZ73; local and remote no-model preflights passed. One GPU, 4 CPUs, 40 GB, 6-hour limit, at most 400 ordinary ML-NEB steps. No GPU job submitted; previous VASP NEB inputs are fallback only.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Obtain exact-package GPU execution authority for request d0a3a7d657b362deb077ed6b181f76129ba63d4c64948700cbc1ca9a408eb85e; then bind the reviewed request, recheck applicable execution gate and duplicate-job state, and submit one MZ73 ordinary ML-NEB job. Review the returned complete path before choosing VASP refinement.

## Submission Boundary

GPU package preparation, staging and no-model preflight only. Production GPU runs and all new VASP calculations require exact-package user authority.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Independent valley relaxation and geometry reviewed; then define scientifically supported migration segments.

## Constraints

- Same H50 moves; preserve SIGMA0.20 and bottom18Fe fixed.
- Do not rerun MID-to-FS O-H work.

## Authoritative References

- docs/reviews/valley9748648_accepted_20260910.md
- docs/reviews/int06_mid_path_prepared_20260910.md
- docs/reviews/int06_mid_gpu_prepared_20260910.md
<!-- state-handoff:end current_task -->
