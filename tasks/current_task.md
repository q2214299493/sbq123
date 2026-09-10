<!-- state-handoff:start current_task -->
# Current Task

## Objective

Complete earlier IS-A to MID H surface migration through validated intermediate and TS evidence.

## Current Evidence Snapshot

- INT06 VASP9748648 accepted as intact mapped C2HO* + H* endpoint: 79 steps, fmax0.0177274761 eV/A, final TOTEN -388.50564344 eV under fe110_converged_toten_sigma0p20_v1.
- IS-A -> INT06 and INT06 -> MID remain separate intervals awaiting validated TS evidence; earlier full-path image02 is an unresolved first-interval ML minimum.
- Accepted MID -> FS O-H TS and 1.28582718 eV forward electronic barrier remain complete; do not repeat.
- GPU1517 on physical GPU0: producer exited success0 at2026-09-10T08:29:50Z; ordinary ML-NEB converged after12steps, projected fmax0.066641 eV/A. No ML-CI. Queue empty, scheduler terminal UNKNOWN because historical accounting unavailable.
- Complete five-frame candidate reviewed in work: source/atom/cell/endpoint/fixed18Fe checks, exact MIC geometry, dist.pl, nebmovie.pl1 and visual inspection passed. H50 remains on surface; C2HO intact.
- MatRIS and AQCat25 both peak at02: respective predicted relative heights0.115633 and0.265541 eV. Model disagreement is not VASP error calibration; sparse path does not establish unique MEP or TS.
- Candidate accepted_for_force_diagnosis_only; dimer_parent_accepted=false. Exact optimized01/02/03 lack compatible VASP energies/forces. Execution gate NEEDS_SUBMISSION_PREFLIGHT, ALLOWED_ACTIONS=[]. No new calculation submitted.
- Completion/review registry batch applied:43 inserts and one workflow change running -> needs_review; scheduler UNKNOWN kept separate from producer convergence. Prior failed GPU attempts remain retained.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Prepare compatible VASP static energy/force diagnosis for exact GPU1517 final images01/02/03; review inputs/resources and execution gate before any submission, then assess Dimer eligibility.

## Submission Boundary

GPU1517 producer has completed. This review authorizes no new GPU/VASP submission; prepare reviewable VASP diagnosis inputs before seeking submission authority.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Independent valley relaxation and geometry reviewed; then define scientifically supported migration segments.

## Constraints

- Same H50 moves; preserve SIGMA0.20 and bottom18Fe fixed.
- Do not rerun MID-to-FS O-H work.

## Authoritative References

- docs/reviews/valley9748648_accepted_20260910.md
- docs/reviews/oh_ts_accepted_barrier_20260910.md
- docs/reviews/int06_mid_gpu1517_path_review_20260910.md
<!-- state-handoff:end current_task -->
