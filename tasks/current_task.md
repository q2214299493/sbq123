<!-- state-handoff:start current_task -->
# Current Task

## Objective

Optimize the five exact Fe110 C2 adsorption identities with reviewed GPU candidates and a chemistry-preserving direct-VASP fallback.

## Current Evidence Snapshot

- Existing10VASP adsorption jobs9839748-9839757 unchanged; last saved snapshotPEND, not re-queried in this GPU submission step.
- User explicitly authorized five supplemental structures01_extra1,02_extra1/2,03_extra1/2 for bounded AQCat25 pre-relaxation.
- Five initial structures pass canonical geometry/connectivity/symmetry-duplicate review; nominal input counts3/3/3/3/3 do not establish distinct stable final minima.
- Frozen package SHA256eba3524bc6a64800dd93a849824ea40adeb1fa887a37eda059fe64ccb47beda6; verified prior task-local runtime reused, no global method changes.
- MZ73 Slurm2142 scheduler=RUNNING observed2026-10-06T15:34:59.598662+00:00; oneGPU,4CPU,32GiB,120minutes,5sequential candidates,80steps each,fmax0.10eV/A.
- Only bottom18Fe fixed; no artificial bond/height/site forces. All adsorbate pairs monitored; final exact chemistry still requires canonical review in work.
- Python syntax,Ruff,4bounded tests,5handoff validations and remote no-model hash/ASE/shell preflight pass. No new VASP, fine-tuning or accepted-energy registration.

## Lifecycle Status

- Phase: `active`

## One Executable Step

After2142 finishes, collect producer receipts, result manifests and predicted structures; validate return hashes and review exact chemistry, sites, convergence and duplicates in work before requesting VASP.

## Submission Boundary

Five-candidate GPU batch2142 explicitly authorized and submitted. Existing10VASP jobs untouched. No automatic resubmission, fine-tuning or new VASP execution authorized.

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
<!-- state-handoff:end current_task -->
