# Final Manual Commit Plan

Date: 2026-07-27

## Preconditions

- Begin with an empty index: `git diff --cached --quiet`.
- Execute one staging block from `FINAL_STAGING_PLAN.md`, review it, commit it,
  and only then proceed to the next block.
- Never substitute `git add -A`, `git add .`, a workspace-root glob, or an
  unreviewed interactive bulk add.
- The commands in the plan are recommendations only; they were not executed.

## Logical order

| Order | Group | Suggested commit message | Purpose | Minimum check before commit |
|---:|---|---|---|---|
| 1 | `security_and_boundaries` | `refactor(core): harden execution and persistence boundaries` | integrate the verified core/workflow source, bounded external commands, atomic writes, compatibility gates, formal configs, and their tests | Ruff; gate/external/atomic focused tests |
| 2 | `neb_path_quality` | `refactor(neb): centralize path-quality orchestration` | add the sole path-quality evaluator path, shared service, CLI/workflow/pilot adapters, configuration, tests, and Phase 2B evidence | path-quality focused tests |
| 3 | `ts_endpoint` | `fix(endpoint): reject invalid geometry and empty reaction IDs` | integrate endpoint boundaries plus the authorized contact/desorption/identity correction and tests | 45 endpoint focused tests |
| 4 | `blocked_migrations` | `fix(migrations): guard the optional endpoint extension` | version the review-only SQL plus exact-shape, transactional, empty-only rollback protection without real execution | temporary SQLite contract tests; never run SQL directly |
| 5 | `documentation_and_release_baseline` | `docs(release): record final verification and release baseline` | integrate audit history, architecture, compatibility reports, additive baseline chain, and manual integration instructions | final manifest verifier; full Ruff/pytest; clean staged-path scan |

The final-release manifest describes the tree after commit 5. It is therefore
expected not to validate at intermediate commits 1–4.

## Per-commit review

Before each manual commit:

```powershell
git diff --cached --name-status
git diff --cached --stat
git diff --cached --check
git diff --cached
```

The reviewer must confirm that the staged names exactly equal the corresponding
array in `FINAL_STAGING_PLAN.md`.

For the final documentation commit, apply the explicit immutable-baseline
whitespace exception documented in `FINAL_STAGING_PLAN.md`. The baseline hash
test must pass, and the scoped diff check must report no other problem.

## Final pre-commit verification

After staging group 5 and before its commit:

```powershell
python -m ruff check scripts modules tests
python -m pytest -q -ra
git diff --cached --check
```

Then run the manifest verifier and prohibited-path scan copied in
`FINAL_STAGING_PLAN.md`.

## Migration status

The migration assets remain review-only:

- `FORMAL_MIGRATION`
- `REVISED`
- `DIRECT SQL EXECUTION PROHIBITED`
- `REAL DATABASE EXECUTION REQUIRES EXPLICIT AUTHORIZATION`
- `NONEMPTY ROLLBACK PROHIBITED`

Committing the SQL text does not authorize executing it, connecting it to the
migration runner, changing the core registry schema version, or applying it to
`data/project_registry.sqlite3`.

## Actions not authorized

This plan does not authorize staging, committing, pushing, tagging, migration,
database writes, SSH, LSF, `bsub`, `bkill`, VASP, or NEB. Commit messages are
recommendations for the user's later manual action.
