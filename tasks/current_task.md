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
- No Hessian, complete migration barrier or new VASP result established; the GPU1512 attempt produced no model output.
- GPU1512 submitted under explicit user authority, then Slurm FAILED with ExitCode=3:0 at startup. Allocated GPU0 had 7465 MiB free <12000 MiB; guard exited before model execution. No ML-NEB steps, predictions, automatic retry or VASP submission. Failed job/input/evidence records registered.
- GPU1 launches 1513/1514 failed before model execution on Python symlink and Slurm TMPDIR=/tmp checks; diagnostic1515 confirmed TMPDIR. Both corrections prepared/tested; latest1516 FAILED before model on GPU1 free-memory guard. At 16:12:54 GPU1 had 10641 MiB free <12000. All attempts preserved and registered; no model steps or active task job.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Recheck physical GPU1 free memory against the current 12000 MiB startup threshold, then verify the corrected full startup under Slurm before progressing the ML path. Preserve all failed attempts; no current model result exists.

## Submission Boundary

Repeated user instruction to submit GPU1 was acted on; startup attempts failed before model execution. No calculation is running, no model retry or VASP task is active.

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
- docs/reviews/int06_mid_gpu1512_startup_failure_20260910.md
- docs/reviews/int06_mid_gpu1_attempts_20260910.md
<!-- state-handoff:end current_task -->
