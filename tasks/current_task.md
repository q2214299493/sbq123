<!-- state-handoff:start current_task -->
# Current Task

## Objective

Review Fe110 adsorption motifs for C2H, CCH2 and three C2HO hydrogen-placement isomers; prepare bounded AQCat25 pre-relaxation candidates.

## Current Evidence Snapshot

- User explicitly authorized GPU pre-relaxation only; no VASP submitted.
- 12 selected local CARE seeds (species counts3/2/1/3/3) pass initial geometry and hash-bound schema/ASE preflight; three excluded raw seeds retained.
- MZ73 Slurm2139 scheduler=RUNNING; one GPU,4CPU,32GiB,120minute limit; maximum80 LBFGS steps per candidate at0.10eV/A.
- Failed bootstrap2136/2137/2138 did not produce adsorption results. Task-local runtime handles verified root symlink and pins cache/temp paths; no global scientific method change.
- Final geometry/chemistry and duplicate review remain pending. Predictions are not reportable adsorption energies. Prior Dimer9833429 review remains deferred.

## Lifecycle Status

- Phase: `active`

## One Executable Step

After2139 finishes, collect all producer receipts, return manifests and predicted structures; validate in work and review final chemistry/sites/duplicates before requesting VASP.

## Submission Boundary

GPU12 batch explicitly authorized and submitted. No automatic continuation/resubmission or VASP handoff.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Exact identities, literature limits, candidate geometry and duplicate issues are reviewable before GPU/VASP submission.

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
<!-- state-handoff:end current_task -->
