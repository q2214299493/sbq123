<!-- state-handoff:start current_task -->
# Current Task

## Objective

Finish three authorized adsorption registrations and submit the reviewed fifteen 06–10 GPU pre-relaxations after scheduler recovery.

## Current Evidence Snapshot

- Registry readback:8 accepted,5 duplicate,1 rejected; three new accepted representatives retain scheduler UNKNOWN under explicit user authority.
- Fifteen frozen candidates uploaded; original AQCat25 checkpoint, no new restraints, no model promotion; local/remote no-model preflight passed.
- MZ73 slurmctld/slurmd failed; controller process absent; queue query failed and sbatch test-only timed out. No real sbatch or GPU job ID.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Obtain administrator restoration of MZ73 Slurm, then recheck live scheduler, immutable package and absence of prior outputs/submission before submitting the authorized frozen fifteen-candidate GPU batch.

## Submission Boundary

User-authorized exact GPU batch only; no VASP, checkpoint promotion, service restart, direct launch, unrelated job changes or repeated submission.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Three named results are accepted through canonical append-only registration with truthful UNKNOWN scheduler status and database readback.
- Fifteen authorized GPU candidates have passing frozen-input preflight and a confirmed scheduler submission receipt; never infer success from upload.

## Constraints

- Preserve scientific source bytes and default scheduler_DONE policy outside three reviewed exceptions.
- GPU predictions are candidates only; return to work for chemical and duplicate review before any VASP handoff.

## Authoritative References

- modules/adsorption_workflow/README.md
- modules/calculation_registry/README.md
- configs/execution_backends.yaml
- docs/reviews/fe110_c2_registration_gpu_20261013.md
<!-- state-handoff:end current_task -->
