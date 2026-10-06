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

## Lifecycle Status

- Phase: `active`

## One Executable Step

At the next authorized status check, inspect queue and compact electronic/ionic progress of9839748-9839757; after completion review target connectivity/sites/duplicates before result registration.

## Submission Boundary

This10-job adsorption batch explicitly authorized and submitted; no automatic resubmission, TS, frequency or gas-reference submission.

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
<!-- state-handoff:end current_task -->
