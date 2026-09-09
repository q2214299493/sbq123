# B4 Registry and State Management Completion Report

Scope: B4 only, based on public B3 commit 9f4332f082d4e286ce43c5a137a62ac1e30fa441.
No B5, production database migration/write, calculation output edit or real job.

## Status

- B4-01 PASS: atomic complete-mutation validation, transaction/event/receipt commit, rollback/failure record and exact retry handling implemented.
- B4-02 PASS: immutable plan hashes, database identity/snapshot, reviewer and scope checks; no apply-time regeneration. State proposals recheck owner-derived actions and review requirements.
- B4-03 PASS: immutable compatibility revisions and original calculation bindings; no historical overwrites.
- B4-04 PASS: authoritative recorded job/workflow transitions in state_manager, with explicit persisted failed-job recovery.
- B4-05 PASS: immutable semantic registry events, status histories, derived job-current-state view, and persistent state application attempts.
- B4-06 PASS: B3 evidence consumed directly; candidates require evidence, accepted results require bound reviewed scientific validation, predictions excluded and publication remains separate.
- B4-07 PASS: explicit schema 9 migration in one transaction, complete validation, guarded rollback, no startup migration.
- B4-08 PASS: persistence, evidence, scientific validation and state transition ownership remain separate.

## Transactions, state and history

The public registry API delegates to one batch mutation owner. Planning runs actual
SQL and existing validation against an in-memory snapshot, so cross-row foreign keys,
constraints, duplicates and transitions are checked before any database mutation.
Under BEGIN IMMEDIATE, apply rechecks the exact plan and current snapshot, then writes
all rows, semantic events and the immutable receipt in one commit. Failure rolls back
and persists a separate failure event. Identical successful retries are no-ops;
a different plan cannot reuse the batch ID. Fingerprints include committed and WAL
state as seen by the current SQLite transaction; only failed-attempt events are
excluded so a rolled-back operation may be retried without silently replanning.

Job observations retain scheduler and scientific status separately. DONE cannot
return to RUNNING. FAILED-to-DONE requires an identified, timestamped, attributed
recovery event. Workflow changes retain expected-prior-state checks and append history.
Source/review events stay immutable; current views are derived projections.

State applications validate full plan hashes, authoritative event/actions/policy,
review requirement and current target hashes. Exclusive reservations and immutable
attempt receipts block duplicate/concurrent application. Ordinary exceptions, including
success-receipt failure, roll back all touched files. A killed process leaves an explicit
UNKNOWN_NEEDS_RECONCILIATION record and is never automatically retried. Archive/move
rollback responsibilities are recorded before potentially partial copy operations.

Excel promotion now binds the database snapshot and rechecks it under a write lock.
The existing writer still renders into staging. Ordinary commit failure restores the
workbook and removes only the matching task receipt; interrupted attempts retain an
explicit reconciliation record. No real workbook was opened or changed by this task.

## Compatibility revisions and migration

Schema 9 adds compatibility revisions, immutable calculation-to-revision bindings,
registry events/apply receipts, job recovery records and a job-current-state view.
Old compatibility rows are retained byte-for-byte as scientific data; new compatibility
creates a new version/new calculation. UPDATE, DELETE and conflicting INSERT OR REPLACE
are rejected for historical scientific/evidence/event records. Guard presence is part
of schema validation, not merely the schema version number.

All explicit historical upgrades and final integrity/foreign-key validation share one
transaction. The additive v9 rollback refuses loss of post-migration governance history
or new compatibility versions. After operational use a reviewed backup/recovery plan is
required. `open_registry(..., migrate=True)` is retained as a legacy call shape but does
not run migrations. No production schema or data has been changed.

## Acceptance and ownership

Evidence lifecycle and ML governance source are unchanged. The registry consumes B3's
assess_evidence/require_transferable and existing VASP validation/parser owners. It does
not introduce scientific thresholds. Accepted generic relaxation results bind the actual
final TOTEN, unit/convention, reviewed claim, compatibility and current source hashes.
Other scientific result kinds must use their existing owning workflows; a metadata PASS
is insufficient. New candidates need evidence. Complete provenance is retained in the
immutable batch event. Predictions cannot become accepted local calculated results.

Removed duplication: SQL moved out of registry_write CLI into the single existing-path
mutation owner; planning and application share its executor. The compatibility upsert
was removed and the public TS API delegates to the revision owner. Numeric/text/digest
validation reuses existing owners; no parallel executor or state manager was introduced.

## Compatibility impact

Valid B1/B2 scientific/execution algorithms and B3 evidence/ML validators are unchanged.
Legacy bare batch-hash apply calls now require a saved plan and explicit approval; all
maintained CLI consumers were updated. Cached state proposals need the new full hash.
Undocumented transitions, unreviewed accepted-result labels and compatibility overwrites
are intentionally rejected. Generic accepted-result ingestion currently supports the
reviewed final-TOTEN relaxation adapter; other accepted result kinds need their owning
workflow, not an invented generic scientific PASS. Production deployment needs an
explicit reviewed schema upgrade. No legacy data is automatically promoted or migrated.

Existing scientific test assertions were preserved. Temporary legacy/corruption fixtures
use a test-only context that suspends then restores immutability guards while constructing
the intended data; this helper refuses paths outside system temporary directories.
Production guard tests use ordinary SQLite connections and cannot use that helper.
Legacy endpoint test fixtures now explicitly initialize the actual versioned registry;
all original scientific assertions are retained. Only the corruption-fixture hunk in
test_ts_strategy_learning.py belongs to B4; pre-existing user changes are excluded.

## Exact changed files

- `modules/calculation_registry/schema.sql`
- `scripts/adsorption/finalize_step12a_gas_references.py`
- `scripts/adsorption/register_step12a_gas_reference_submission.py`
- `scripts/adsorption/register_step12a_oh_restart.py`
- `scripts/init_registry.py`
- `scripts/registry_excel_promotion.py`
- `scripts/registry_schema.py`
- `scripts/registry_write.py`
- `scripts/state_manager/proposals.py`
- `scripts/state_manager/store.py`
- `scripts/ts_strategy_engine/evidence.py`
- `scripts/ts_strategy_engine/registry.py`
- `tests/test_b21_scientific_acceptance.py`
- `tests/test_registry_excel_promotion.py`
- `tests/test_registry_schema.py`
- `tests/test_registry_write.py`
- `tests/test_ts_strategy_engine.py`
- `scripts/registry_mutations.py`
- `scripts/registry_transactions.py`
- `scripts/registry_compatibility.py`
- `scripts/registry_acceptance.py`
- `scripts/state_manager/job_lifecycle.py`
- `scripts/state_manager/application_log.py`
- `tests/test_b4_registry_governance.py`
- `tests/test_b4_state_governance.py`
- `tests/registry_fixture_mutation.py`
- `modules/calculation_registry/migrations/009_registry_governance.sql`
- `modules/calculation_registry/migrations/009_registry_governance_rollback.sql`
- `modules/calculation_registry/README.md`
- `modules/state_handoff/README.md`
- `scripts/README.md`
- `reports/refactor_audit/B4_completion_report.md`
- `tests/test_structure_purpose_manager.py`
- `tests/test_ts_endpoint_contracts.py`
- `tests/test_ts_strategy_learning.py`

## Validation

Final validation used the complete B3-based publication snapshot on Windows / Python 3.13.9.
All 35 publication files were checked against task-owned source changes, with the
single partial learning-test hunk isolated from unrelated user edits.

```text
python -m ruff check scripts modules tests
python -m pytest -o addopts= -q
```

Ruff: **All checks passed**, exit 0.
Full pytest: **1008 passed, 0 failed, 0 skipped in 360.34s (0:06:00)**, exit 0.

Focused command:

```text
python -m pytest -o addopts= -q tests/test_b4_registry_governance.py tests/test_b4_state_governance.py tests/test_registry_schema.py tests/test_registry_write.py tests/test_state_manager.py tests/test_ts_strategy_engine.py tests/test_registry_excel_promotion.py tests/test_b21_scientific_acceptance.py tests/test_structure_purpose_manager.py tests/test_ts_endpoint_contracts.py tests/test_ts_strategy_learning.py
```

Focused result: **268 passed, 0 failed, 0 skipped in 53.81s**, exit 0.
The two new B4 regression files contain **47 passing cases**, including actual
mid-transaction failure, concurrent/duplicate apply, mutated approvals/snapshots,
reviewed VASP acceptance, immutable REPLACE protection, recovery events, migration
rollback, state receipt/rollback failures and Excel commit failure recovery.

The earlier full snapshot returned 986 passed / 15 failed. Those failures exposed
legacy minimal-schema fixtures and deliberately corrupted immutable history; their
setup was corrected while preserving all existing scientific assertions. Only the
final results above establish completion. Scoped git diff --check passed. AST
comparisons confirmed unchanged existing scientific/endpoint/Excel assertions and
unchanged TS scientific function bodies (the compatibility facade is the exception).
No scientific threshold, VASP/NEB/DIMER/TS validator, execution authorization, B3
lifecycle/ML validator, GPU wrapper, model weight or calculation output was changed.

`repo-state audit --phase start`: exit 0, zero errors, six pre-existing warnings.
Read-only end-sync preflight found no applicable proposals before the existing
`repository item changed after classification: sbq_catalyst_agent_workflow.egg-info/PKG-INFO`
error. The required `python -m scripts.state_manager.cli sync --safe-only` was then
executed and exited 1 with that same error, before applying managed projections.
No historical event was edited or production state repaired to bypass the blocker.

Normalized publication snapshot SHA-256 (34 task-owned files excluding this report;
CRLF normalized to LF, sorted compact JSON mapping file names to SHA-256 values):
`34ce400bc8a44e6fd49f539195e7e51cd8e98862b9fc398f9fca1acd7160d95b`.


## Remaining uncertainties

No production database, real model/GPU/VASP run, scheduler, SSH or live workbook was
used. Migration was exercised only on temporary fixtures; production backup/size/legacy
schema review remains a rollout step. Reviewer identifiers are traceability fields, not
cryptographic authentication. Host/storage failure cannot make SQLite and multiple
filesystem files one hardware-atomic resource; unknown state/promotion attempts require
manual reconciliation. Privileged actors capable of dropping SQLite guards or rewriting
local files are outside the in-process authorization boundary. No B5 work or merge.

## B4.1 final registry contract closure (2026-09-09)

Scope: the two remaining public input contracts only, based on published B4
`e4465aa9e1521a3b9ec3dabba40badb5f17d772a`, on
`q2214299493/sbq123`, branch `codex/b4-registry-state-management`.

Both closure items PASS:

- `validate_registry_batch` normalizes an omitted `rows` field to `{}` in a
  returned copy, without modifying the caller's document. Explicit and omitted
  empty rows therefore have identical validated content, batch/plan hashes and
  approval semantics. Existing provenance validation and the single planner/apply
  path consume this canonical document. Non-object batches and malformed rows
  raise intentional `ValueError` errors; rows remain optional.
- Both compatibility registration entry points reuse
  `scripts.provenance_fields.timestamp` for `reviewed_at`. Missing, malformed,
  date-only and timezone-naive review times fail before database writes. UTC and
  explicit-offset timestamps pass. Compatibility identity still hashes only the
  compatibility content; repeated registration preserves original review records.

Exact B4.1 changed files:

- `scripts/registry_mutations.py`
- `scripts/registry_compatibility.py`
- `tests/test_registry_write.py`
- `tests/test_b4_registry_governance.py`
- `tests/test_ts_strategy_engine.py`
- `reports/refactor_audit/B4_completion_report.md`

Existing scientific test assertions were retained. The TS strategy fixture only
replaces its date-only compatibility review time with a timezone-aware timestamp.
There is no new parser, timestamp validator, planner, executor or migration.
Schema version 9, transaction/approval/replay rules, compatibility revision
identity, B1 execution, B2 science and B3 evidence behavior are unchanged. No
scientific thresholds, VASP/NEB/DIMER/TS logic, production database, historical
scientific data, calculation output, POTCAR or model weights were modified.

Validation on the isolated publication worktree (Windows / Python 3.13.9):

```text
python -m ruff check scripts modules tests
All checks passed! (exit 0)

python -m pytest -o addopts= -q
1032 passed in 262.40s (0:04:22) (exit 0)

python -m pytest -o addopts= -q tests/test_registry_write.py tests/test_b4_registry_governance.py tests/test_registry_schema.py
72 passed in 2.94s (exit 0)
```

The initial source-worktree focused run also passed: 72 passed in 4.64s, exit 0.
Regressions cover omitted/explicit rows, unchanged caller input, identical plans,
approved apply, idempotent replay across both shapes, stale expected status with
no mutation, intentional input errors, invalid timestamp rejection without writes,
valid timezone timestamps, unchanged compatibility hashes and historical reviews.
Scoped `git diff --check` passed. The 353 pre-existing source-worktree status
entries were preserved and excluded from publication.

Repository-state housekeeping: startup audit exited 0 with zero errors and seven
pre-existing worktree/root-layout warnings. Read-only end-sync preflight found no
applicable proposals before the existing classification mismatch. The required
`python -m scripts.state_manager.cli sync --safe-only` exited 1 with
`repository item changed after classification: sbq_catalyst_agent_workflow.egg-info/PKG-INFO`;
no managed projection was applied. This pre-existing housekeeping blocker was
not repaired as part of B4.1.

Production-only uncertainties remain as documented above: validation used
temporary registries, not production deployment or live scientific jobs. This
closure does not authenticate reviewer identities or reconcile unknown production
operations. No merge or B5 work.
