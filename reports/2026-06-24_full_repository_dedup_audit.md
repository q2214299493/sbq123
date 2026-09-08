# Full Repository Workflow Deduplication Audit

## Scope

- Entire tracked repository, including active protocols, modules, skills, scripts, calculation directories, imported user packages, migration evidence, reports, and archives.
- Initial inventory: 333 tracked files and 38 byte-identical file groups.
- Reviewed command families: startup/closeout, SSH/LSF submission, NEB precheck/post-processing, monitoring, DIMER, TS grading, registry, convergence, and INCAR tuning.

## Canonical Owners

| Behavior | Canonical owner |
|---|---|
| thread startup and task close | `AGENTS.md` |
| scheduler query/submission | `docs/01_METHOD_PROTOCOL.md` |
| stage order and boundaries | `docs/12_WORKFLOW_ARCHITECTURE.md` |
| NEB path/precheck/post-process | `modules/neb_workflow/README.md` |
| DIMER method and mode | `modules/dimer_ts_search/README.md` |
| TS A/B/C grade | `docs/10_TS_VALIDATION_PROTOCOL.md` |
| job/file/result provenance | `docs/11_DATA_PROVENANCE_PROTOCOL.md` |
| INCAR recommendation | installed `fe-vasp-incar-custodian` skill |

## Corrected Duplication

- Removed the startup read-loop and task-close checklist duplication from `docs/01_METHOD_PROTOCOL.md`.
- Removed repeated workflow-order lists from `modules/README.md`.
- Replaced repeated TS/database rules with links to the TS protocol.
- Reduced INCAR module content to project ownership; commands and output formats remain only in the skill.
- Replaced four job-ID monitor scripts and four calculation-specific precheck scripts with:
  - `scripts/neb_agent/check_neb_job.sh`
  - `scripts/neb_agent/precheck_neb_remote.sh`
- The generic precheck refuses to overwrite different inputs or any existing movie/log/table artifact.
- Removed the obsolete hard-coded auto-submit shell entry point.
- Removed one duplicate root path-builder copy; moved three superseded unique NEB scripts to `archive/legacy_neb_scripts/`.
- Removed stale integration notes from `tasks/current_task.md`.
- Removed imaginary-frequency thresholds from NEB configuration because TS numerical thresholds remain unapproved.
- Removed `ACCEPTED_TS` from the NEB decision schema; NEB may hand off `READY_FOR_VFA` but cannot accept a TS.
- Changed DIMER/VFA INCAR generation to `NEED_USER_CONFIRMATION` until the owning module approves the method.

## Retained Duplicates

After correction, the prospective tracked inventory is 327 files and 37 exact-hash groups:

- 28 calculation/imported-package snapshot groups
- 8 migration or curated-evidence provenance groups
- 1 current-utility plus calculation-snapshot group

These include endpoint POSCAR copies, run-specific INCAR/KPOINTS/LSF files, imported package mirrors, migration evidence, and a geometry utility copied into historical runs. Their paths are provenance, so they were not deleted or replaced by links.

Historical INCAR values such as `SIGMA=0.15` or `LDIPOL=.TRUE.` remain attached to their original failed/superseded runs and are not current defaults.

## Verification

- Active authoritative Markdown has no repeated identical instruction line of 35 or more characters.
- All root executable scripts are now indexed as current utilities; superseded NEB scripts are outside the root and labeled legacy.
- Both new shell utilities passed `bash -n` with Git Bash.
- `check_neb_job.sh` completed a read-only functional check against the local active eight-image package and reported all internal images plus the current geometry table.
- DIMER and VFA generation tests both returned `NEED_USER_CONFIRMATION`.
- The synchronized installed INCAR skill passed strict scanning with INFO-only missing-license metadata.
- No scientific calculation directory or structure/input snapshot was modified or deleted.
- Remote execution was not performed; server-side functional testing remains task-specific.
