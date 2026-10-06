<!-- state-handoff:start current_task -->
# Current Task

## Objective

Optimize the five exact Fe110 C2 adsorption identities with reviewed GPU candidates and a chemistry-preserving direct-VASP fallback.

## Current Evidence Snapshot

- GPU2139 returned12 validated predictions. Chemistry review excluded fragmented02_cfg1 and03_cfg0 output;01_cfg0 duplicates01_cfg2.
- Nine intact distinct GPU outputs plus intact pre-GPU03_cfg0 were submitted as10 ordinary adsorption relaxations, species counts2/1/1/3/3.
- LSF9839748-9839757 allPEND in the saved snapshot;32MPI ranks each. Electronic/ionic convergence not yet assessed.
- Production PBE/PAW-PBE,ENCUT400,Gamma5x5x1,SIGMA0.20,Fe45five-layer,fixedFe0-17 preserved; no artificial bond restraints.
- Registry received submission/job/input metadata only, no predicted energy or accepted adsorption result. Prior TS work remains deferred.
- 37 relevant tests pass;10 extended lifecycle tests have existing stdin mock incompatibility; no unrelated source repair.
- User requested supplementation. Five additional candidates01_extra1,02_extra1/2,03_extra1/2 built from exact local templates, not externally proven minima.
- All5exported initial geometries pass canonical chemistry/contacts/cell/fixed-layer review; clean-slab symmetry and H permutation checks exclude periodic/reflection/height-only duplicates.
- Nominal input counts would be3/3/3/3/3; the new5are not relaxed and may merge or fragment later. Existing10VASP jobs unchanged; no fresh scheduler observation in this step.
- Python syntax,Ruff,4bounded tests and5POSCAR reparse checks pass. NewGPU/VASP submissions remain unauthorized.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Review the five supplemental structures with the user; after separate authorization prepare/run a bounded AQCat25 batch and return results for chemistry/domain/duplicate review.

## Submission Boundary

Existing10VASP jobs unchanged. Five new initial structures await review; no new GPU/VASP execution or automatic resubmission authorized.

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
<!-- state-handoff:end current_task -->
