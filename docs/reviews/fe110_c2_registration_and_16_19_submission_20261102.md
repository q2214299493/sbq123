# Fe(110) final-state registration and16–19 submission

Client date2026-11-02, Asia/Shanghai. This completes the current request to
formally review eligible11–15 results, synchronize the adsorption workbook,
then run the previously requested GPU-before-DFT workflow for16–19.

## Registered and saved results

Eight evidence-complete independent states now have accepted compatible final
OUTCAR TOTEN records and saved workbook rows68–75:

| Source | Native job | Main row |
|---|---|---:|
|11_B|9927794|68|
|12_C|9927517|69|
|13_C|9927522|70|
|14_B|9927524|71|
|14_C|9927525|72|
|15_A|9927526|73|
|15_B|9927527|74|
|15_C|9927528|75|

The existing workbook is
`outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx`.
Final energies use`fe110_converged_toten_sigma0p20_v1`. E0 and adsorption
energies are explicitly unavailable; no missing reference energy, thermal
correction or literature energy was manufactured.

Two duplicate sources11_A/14_A remain linked to11_B/14_B. Four converged
sources11_C/12_A/12_B/13_B lack recoverable historical DONE evidence and stay
pending, with UNKNOWN scheduler state kept separate from numerical convergence.
13_A remains force-not-converged; it was not restarted. These seven identities
appear in the existing metadata-only pending sheet, rows24–30, not as accepted
numeric main-table rows. All15 originals therefore remain traceable.

15_B was reviewed as molecular eta2/top adsorption: both C atoms have the
same nearest Fe41 and C–C midpoint top-projection offset0.004471 A. Off-site
individual C projections were not mislabeled as exact long bridges.
12_A/12_C remain conservatively separate; their same-basin identity is unproved.

Canonical append-only registration, exact-plan review/apply and separate
registry-to-Excel promotion gates were used. Eight saved promotion receipts
match the exact result IDs and numeric values. Closure sets only these eight
workflows to`excel_promoted`. Independent bundled-Python/openpyxl readback
verifies all original67main rows,23pending rows, styles, dimensions, merges,
freeze panes and all eight new accepted rows/seven pending rows. Renders were
reviewed. SQLite quick_check and foreign keys pass. Native Excel interactive
behavior was not tested.

Evidence and original workbook backup:
`outputs/fe110_c2_registration_20261102_v1/`.
The verified final workbook SHA256 is
`b0b58108518d587ad423ba5270ff857af4b6d014dbd24062ebfce235188436c5`.

## Bounded GPU stage

The user separately approved sharedGPU0, at most600seconds and16GiB allocator
limit, without stopping resident processes. Exact resident PID/UID/start-time
allowlists, minimum-free-memory checks, physical GPU UUID, CPU/RAM bounds,
process ownership, source/checkpoint hashes and real CUDA tensors were checked.

One direct execution ran on MZ73 GPU0:

- Controller2588704, producer2588719; these are processes, not Slurm jobs.
- Producer span28.207023seconds; controller/producer exits0.
-12/12 reach the exploratory ML fmax0.10eV/A threshold;27/44/31,
  28/30/35,53/20/48 and37/35/7optimizer steps for16–19 A/B/C.
-10 ML endpoints retain the intended connectivity.16_B and18_A predict
  C2H3O+H after dehydrogenation. Those predictions are preserved; their
  unchanged reviewed original seeds were selected for the intact-target DFT
  tests, with no claim of GPU acceleration for those two starts.
-407trajectory frames were checked for source, coordinates, raw forces,
  fixed masks and final correspondence. All12 selected DFT poses are unique
  under the current conservative geometry screen.
-12work-to-GPU and12GPU-to-work schema-v2 handoffs pass. These seven/eight
  adsorbate-atom cases are outside the existing2–6atom calibration scope.
  They provide candidate pre-relaxation only, not calibrated rankings,
  quantitative uncertainty, stable-minimum proof or measured VASP speedup.

No training, checkpoint reselection or model promotion occurred. GPU results
returned through`work`; no direct GPU-to-VASP transfer or remote automatic
VASP submission was used.

## Twelve VASP submissions

All twelve reviewed inputs passed structure/atom-order/fixed-mask readback,
INCAR custodian validation, production preflight, live account/runtime/POTCAR
checks and current exact-hash SUBMIT_VASP execution gates.

| Number | A | B | C |
|---|---|---|---|
|16|9937804|9937805|9937806|
|17|9937807|9937808|9937809|
|18|9937810|9937811|9937812|
|19|9937813|9937814|9937815|

Backend`sunboquan-codex`, native LSF queue Gkn_normal, remote root
`~/sbq/Fe110/adsorption/c2_16_19_ft512_20261102_v1`.
Each uses32MPIranks,32/node, max300steps and the unchanged Fe45/PBE/400eV/
Gamma5x5x1/ALGO Fast/SIGMA0.20/EDIFFG-0.02 basis. The live128-slot account
contract passed; submission checkpoint shows16_A/B/C and17_A RUN, eight
others PEND. Queue state alone does not establish electronic or ionic progress.

Native exactly-once reservations and receipts were checked before and after
submission.12jobs and their inputs/POTCAR metadata plus the GPU provenance
parent were appended once;415metadata rows read back exactly, zero scientific
results were inserted for these new calculations. No pilot, retry, old-job
cancellation, continuation or reference calculation was submitted.

Local evidence:
`calculations/fe110_c2_adsorption_16_19_20261101/gpu_ft512_20261102_v1/`.
Important files are`ML_results_review.json`, `returned_handoffs_v2/`,
`dft300_v2/plan.json`, `dft_submission_v1/submission_summary.json`, the twelve
native submission records and`registration_verification.json`.

## Validation and recovery

96directly related tests passed in the canonical workspace. Scoped Python
compilation, Ruff and Node syntax checks pass. No full-repository suite or
scientific workflow was launched merely to validate code.

Preserved local failures and their bounded recoveries:

1. GPU packager omitted its handoff parent directory. Only the pre-request
   partial local package was resumed with byte checks; no remote/model retry.
2. The first Excel promotion succeeded, then its reporting adapter used
   `row_number` rather than canonical`excel_row_number`. Receipt and registry
   were inspected first; row68 was not inserted again. Remaining rows proceeded.
3. A return-handoff metadata payload used a display backend instead of schema
   enum`aqcat_gpu`. The invalid payload remains; correctedv2handoffs validate,
   without rerunning GPU. The native producer record remains unchanged and a
   hash-bound adapter names its actual direct process, never a fictitious job.
4. The adsorption preflight's exact-composition set lacked C2H4O/C2H6.
   Only these two supported compositions were added; unknown C2H5 still fails.
   The failed unsubmitted16_A input package remains under`dft300_v1/`.
   Fresh`dft300_v2/`inputs pass; no VASP job was retried and no physics changed.
5. An inherited diagnostic caption mentioned C3 for a C2 fragment. Actual C2
   fragment lists and DFT-selection annotations are authoritative. The shared
   helper now uses species-neutral wording; old bound evidence is preserved.

Task-owned adapters are under`archive/fe110_c2_registration_20261102/` and
`archive/fe110_c2_16_19_gpu_20261102/`. Shared runtime dispatch only adds this
exact twelve-case authorized scope. Previous task exceptions and deployed
packages remain unchanged. No global domain/ranking gate was relaxed.

Source-release verification uses an isolated sbq123-history worktree. Its
initial import check found an omitted existing dependency,
`scripts/adsorption/prepare_completion_registration.py`; the unchanged
previously published source from commit409a6cf9 was restored, not rewritten.
The selected27 release tests, syntax and scoped Ruff checks pass. Semantic
comparison confirms only the current twelve-case backend exception was added.
No database, workbook, model, POTCAR or raw calculation output is published.

The required end-of-task `repo-state sync --safe-only` was attempted once and
failed with `repository item changed after classification:
sbq_catalyst_agent_workflow.egg-info/PKG-INFO`. No retry or unrelated package
repair was performed. This repository projection issue does not invalidate
the saved scientific/Excel/LSF receipts; automatic state synchronization remains
unconfirmed.

Next executable scientific step: on-demand monitoring of these twelve VASP
jobs, then final chemistry/coadsorption and convergence review. Completed
eligible results must use the existing automatic registration/Excel gates;
unqualified cases retain truthful status. No recurring monitor was created.
