<!-- state-handoff:start current_task -->
# Current Task

## Objective

Optimize the five exact Fe110 C2 adsorption identities with reviewed GPU candidates and a chemistry-preserving direct-VASP fallback.

## Current Evidence Snapshot

- All5GPU2142producer exit records report0 and returned hashes/schema/checkpoint/source identities validate; no durable Slurm terminal state claimed.
- All5reach MLfmax0.10eV/A, but03_extra2breaks CC1.5349->2.9355A intoCH+CO; failed input/output preserved, not accepted as targetCHCO.
- 01_extra1,02_extra2,03_extra1 are intact and distinct from sampled previousGPU/VASP geometries; secondary CH2-C45/O47 off-symmetry site warnings retained, not final-site acceptance.
- 02_extra1RMSD0.18567A to the sampled live02_cfg2VASP structure; hold as possible duplicate, not proven same final minimum and no source deletion.
- Duplicate review uses36clean-slab top-side-preserving symmetries,xyPBC,Hpermutations,actual relaxed height; never compare ML and DFT absolute energies.
- One new03_extra2_repair_v1 uses intact exactCARE template,centralC46shortbridge,flat chain alongFe rows,C46-Fe2.20A; canonical geometry passes without warnings,minimum seed-motifRMSD0.40653A.
- Repair is unrelaxed; no bonds forced, no model fine-tuning and no DFT protocol change. Original45Fe slab and fixedFe0-17 preserved.
- Previous repair review remains historical unrelaxed input evidence; original failed seed/results unchanged.
- User continuation authorized only03_extra2_repair_v1 bounded GPUpre-relaxation; newmanifestdd7c2522cdda517efbfe4f659ab26d379cbfede99ad646582b2b9bde06b572f7.
- Localschema/input/hashchecks,Pythoncompile,Ruff and5focusedtestsPASS; MZ73remote no-modelpreflightPASS; checkpoint unchanged.
- GPUjob2176schedulerRUNNING at2026-10-07T16:00:28.242106+00:00; oneGPU,4CPU,32GiB,30min,80LBFGSsteps,MLfmax0.10eV/A.
- OnlyFe0-17fixed; no internal-bond/site/heightrestraints. Optimizer convergence cannot establish intactCHCO; returnedchemistry/site/duplicate/domainreviewrequired.
- Existing10VASPjobs and otherGPU candidates untouched; noVASPsubmission,modeltraining,acceptedenergyregistrationorautomaticresubmission.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Check GPU2176 at the next requested checkpoint; on exit collect hash-bound producer/result/structure artifacts and review intact CHCO connectivity, adsorption geometry and duplicates before any VASP handoff.

## Submission Boundary

User authorized the single bounded repaired-seed GPUjob2176 only. No further GPU/VASP submission, automatic resubmission, stops or fine-tuning.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Completed VASP candidates have convergence, exact chemical identity, site and duplicate reviews before accepted result/energy promotion.

## Constraints

- Use true Fe110 Fe45 five-layer branch, fixedFe0-17 and SIGMA0.20 production method.
- Do not substitute acetylene for CCH2 or mix the three C2HO graphs.
- Candidate counts follow distinct supported motifs; no blind three-site padding or ML global-minimum claims.
- AQCat25 is adsorption pre-relaxation primary; results return through work before VASP.

## Authoritative References

- archive/fe110_five_c2_adsorption_20261006/REVIEW.md
- archive/fe110_five_c2_adsorption_20261006/request_and_retrieval.json
- calculations/fe110_five_c2_adsorption_20261006/candidate_review.json
- archive/fe110_five_c2_adsorption_20261006/literature_review.json
- calculations/fe110_five_c2_adsorption_20261006/gpu_submission_evidence_2139.json
- calculations/fe110_five_c2_adsorption_20261006/gpu_batch_v4/batch_manifest.json
- calculations/fe110_five_c2_adsorption_20261006/gpu_return_review.json
- calculations/fe110_five_c2_adsorption_20261006/vasp_batch_v1/batch_manifest.json
- calculations/fe110_five_c2_adsorption_20261006/vasp_batch_v1/submission_summary.json
- calculations/fe110_five_c2_adsorption_20261006/vasp_batch_v1/registry_receipt.json
- archive/fe110_five_c2_adsorption_20261006/SUPPLEMENT_REVIEW.md
- calculations/fe110_five_c2_adsorption_20261006/supplement_v1/candidate_review.json
- calculations/fe110_five_c2_adsorption_20261006/supplement_v1/structure_review.png
- archive/fe110_five_c2_adsorption_20261006/SUPPLEMENT_GPU_SUBMISSION.md
- calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_v1/batch_manifest.json
- calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_submission_v1/submission_summary.json
- calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_review_v1/review.json
- calculations/fe110_five_c2_adsorption_20261006/supplement_repair_v1/repair_review.json
- docs/reviews/fe110_gpu2142_adsorption_review_20261007.md
- calculations/fe110_five_c2_adsorption_20261006/gpu_repair_v1/batch_manifest.json
- calculations/fe110_five_c2_adsorption_20261006/gpu_repair_v1/reviewed_plan.json
- calculations/fe110_five_c2_adsorption_20261006/gpu_repair_submission_v1/preflight_binding.json
- calculations/fe110_five_c2_adsorption_20261006/gpu_repair_submission_v1/submission_summary.json
- calculations/fe110_five_c2_adsorption_20261006/gpu_repair_submission_v1/submit.txt
- calculations/fe110_five_c2_adsorption_20261006/gpu_repair_submission_v1/scheduler_2176.txt
<!-- state-handoff:end current_task -->
