# Condition Closure Report

## Conclusion

**PASS**

All three conditions in `VERIFICATION_REPORT.md` are closed with local,
reviewable evidence. No real SSH, LSF, VASP, or NEB action was performed.

## Condition status

| Condition | Status | Evidence |
|---|---|---|
| Isolate the verified refactor | Closed | `REFACTOR_CHANGESET.md` and three files under `artifacts/refactor_changeset/`; only A/B/C are review material. |
| Define unresolved-submission recovery | Closed | `SUBMISSION_RECOVERY.md`; retry/delete/guessing are forbidden while `submission_attempt.json` exists. |
| Protect legacy alpha-Fe bsub entry | Closed | Existing success and attempt markers checked; attempt written atomically before bsub; existing 300 s timeout reused; success marker written atomically; failures retain uncertainty. |

## Closure-specific modified files

- `scripts/convergence/common.py`: shared definition of the existing 300-second submission timeout; no scientific parameter changed.
- `scripts/convergence/setup_alpha_fe_bulk_smearing.py`: prevalidation, duplicate/unresolved guards, atomic attempt/success records, timeout, and failure handling.
- `scripts/neb_agent/submission.py`: same public timeout name retained; unresolved error now identifies refusal reason, marker path, and recovery document.
- `tests/test_alpha_fe_bulk_submission.py`: eight collected regression cases covering success, duplicate, unresolved, non-zero, timeout, unparseable output, cleanup, invalid inputs, and unchanged generated inputs.
- `tests/test_neb_submission.py`: recovery-message assertions.
- `tests/test_repository_contracts.py`: narrowly permits only the required
  `artifacts/refactor_changeset` directory and its three specified files.
- `SUBMISSION_RECOVERY.md`, `CHANGESET_MANIFEST.md`, `UNTRACKED_FILE_INVENTORY.md`, and `REFACTOR_CHANGESET.md`: review and recovery evidence.

## Worktree isolation

- Frozen commands executed: `git status --short`, `git diff --name-status`,
  `git diff --stat`, and `git ls-files --others --exclude-standard`.
- Frozen state: 63 tracked modified files, 3254 insertions, 1073 deletions,
  and 513 untracked files before closure outputs.
- Excluded tracked paths: 57; one mixed-provenance test path contributes only
  its explicit artifact-directory contract hunks to the isolated patch.
- Excluded unrelated/unknown untracked non-runtime paths: 23.
- Excluded calculation/runtime/generated files: 474.
- Inventory classifications: 224 calculation inputs, 234 generated artifacts,
  16 runtime-state files, 15 source files, 11 tests, 8 documents, 3 configs,
  and 2 unknown SQL migration files.
- Sensitive scan reported no matched risk type; this is a bounded heuristic,
  not proof that every file is non-sensitive.

## Alpha-Fe submission behavior

- Every case is prevalidated for `run.lsf` before any submit call.
- Existing `submitted.jobid` causes a no-submit skip.
- Existing `submission_attempt.json` refuses retry before subprocess execution.
- A same-directory atomic attempt marker is complete before `bsub` starts.
- `subprocess.run` uses `EXTERNAL_COMMAND_TIMEOUT_SECONDS == 300`, shared with
  and still exported by `scripts.neb_agent.submission`.
- Non-zero exit, timeout, or unparseable output creates no success marker and
  retains the attempt marker for manual recovery.
- A parsed job ID writes the original `submitted.jobid` text format atomically,
  then removes the attempt marker.
- No retry loop or automatic recovery was added.
- INCAR, KPOINTS, POSCAR, POTCAR, LSF copy behavior, case matrix, and scientific
  values were not changed; the regression test checks generated content.

## Recovery rule

`submission_attempt.json` means remote submission started but local confirmation
is absent. Read-only scheduler and remote-path evidence may recover an existing
job. A unique match permits a human-reviewed success record; ambiguity remains
`UNKNOWN`/`PENDING_REVIEW`. Neither automation nor an operator may treat timeout
as failure and immediately resubmit.

## Validation

| Command | Exit | Result |
|---|---:|---|
| `python -m ruff check scripts modules tests` | 0 | All checks passed. |
| `python -m pytest -q -ra` | 0 | 225/225 collected tests passed. |
| `git diff --check` | 0 | No whitespace errors; Git emitted only existing LF/CRLF conversion warnings. |
| `python -m scripts.ts_strategy_engine.cli --help` | 0 | Help displayed. |
| `python -m scripts.adsmind_lite.plan_adsorption_candidates --help` | 0 | Help displayed. |
| `python -m scripts.neb_agent.submission --help` | 0 | Help displayed. |
| `python -m scripts.neb_agent.remote_monitor --help` | 0 | Help displayed. |
| `python scripts/convergence/setup_alpha_fe_bulk_smearing.py --help` | 0 | Legacy direct CLI remains startable. |
| skip/xfail source scan | 0 matches | No skipped or expected-failure tests found. |

The tests replace subprocess calls with local fakes. This session did not invoke
`ssh`, `bjobs`, `bsub`, `bkill`, VASP, or a NEB calculation.

## Compatibility and scope checks

- No CLI option syntax changed.
- No configuration file, configuration Schema, database, migration, serialized
  scientific result, task directory, or historical result was edited in this
  closure stage.
- `submitted.jobid` success content retains its original job-ID-plus-output format.
- No scientific, physical, or chemical decision rule changed.
- The submission timeout value was not changed.
- No staging, commit, push, reset, clean, stash, checkout, deletion, or real
  external submission was performed.

## Remaining risks

- Recovery against a real LSF history was intentionally not exercised; a human
  must still resolve any real unresolved marker using site-specific scheduler evidence.
- The worktree remains mixed. Two unknown SQL migration files and other excluded
  source/config/test files still require separate provenance review.
- Atomic last-writer-wins file replacement does not serialize competing controllers;
  the limitation documented in `VERIFICATION_REPORT.md` remains.

## Next stage

Review the isolated A/B/C manifest and patch before any selective staging. Do not
use `git add -A`, and keep all D/E/F paths outside a future commit.
