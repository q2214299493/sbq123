# Final Staging Plan

Date: 2026-07-27

## Result

The verified integration allowlist contains 182 paths divided into five
disjoint groups. All commands below are PowerShell commands to be run manually
from the repository root. They were generated but not executed.

The plan intentionally excludes:

- `calculations/`, `outputs/`, `reports/`, and `data/`;
- `tasks/` and operational state documents;
- SQLite/database files, runtime state, scheduler evidence, caches, VASP output,
  NEB output, and other generated calculation material.

The two SQL files occur only in `blocked_migrations`. They are review-only and
remain prohibited from direct or real-database execution without separate
authorization; non-empty rollback is prohibited.

## Group counts

| Group | Paths |
|---|---:|
| `security_and_boundaries` | 59 |
| `neb_path_quality` | 21 |
| `ts_endpoint` | 28 |
| `documentation_and_release_baseline` | 69 |
| `blocked_migrations` | 5 |

The section display follows the category order requested by the user. The
manual commit order is `security_and_boundaries`, `neb_path_quality`,
`ts_endpoint`, `blocked_migrations`, then
`documentation_and_release_baseline`, as defined in
`FINAL_COMMIT_PLAN.md`.

## Manifest and allowlist validation

- Final-release manifest rows checked: 329.
- Missing paths: 0.
- Size mismatches: 0.
- SHA-256 mismatches: 0.
- Staging-array union: 182 paths.
- Cross-group overlap: 0.
- Prohibited calculation/output/runtime/database/generated paths: 0.

The current final binding is recorded only in
`artifacts/final_release_baseline/final_release_sha256.txt`; it is not copied
into this bound document, avoiding a circular hash.

## Manual staging protocol

Before every group, require an empty index:

```powershell
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) { throw 'Index is not empty; review or commit the prior group first' }
```

Run exactly one block, review/commit it according to `FINAL_COMMIT_PLAN.md`,
then continue. Do not combine the arrays and do not replace them with a glob.

### Immutable review-baseline whitespace exception

Three historical documents are byte-bound by Review Baseline v2/v3:

- `PHASE_2A1_CLOSURE_REPORT.md`
- `REVIEW_BASELINE_V2.md`
- `REVIEW_BASELINE_V3.md`

Their original bytes intentionally include Markdown hard-break spaces (and one
final blank line). Do not normalize them or update the old baseline hashes.
For the final documentation group, verify the exception with:

```powershell
python -m pytest -q tests/test_repository_contracts.py::test_review_baseline_v3_hash_bindings_match
git diff --cached --check -- . `
  ':(exclude)PHASE_2A1_CLOSURE_REPORT.md' `
  ':(exclude)REVIEW_BASELINE_V2.md' `
  ':(exclude)REVIEW_BASELINE_V3.md'
```

The unscoped staged check reports only these known immutable bytes. After the
commit, the ordinary worktree `git diff --check` must pass.

## security_and_boundaries

```powershell
Set-StrictMode -Version Latest
$security_and_boundaries = @(
  'configs/aqcat25_ts_active_learning.schema.json'
  'configs/aqcat25_ts_active_learning.yaml'
  'configs/aqcat25_ts_domain_gate.yaml'
  'configs/true_fe110_production.yaml'
  'scripts/aqcat25_ts_schema.py'
  'scripts/artifact_io.py'
  'scripts/convergence/common.py'
  'scripts/convergence/setup_alpha_fe_bulk_smearing.py'
  'scripts/neb_agent/analyze_neb_outputs.py'
  'scripts/neb_agent/check_endpoints.py'
  'scripts/neb_agent/check_neb_job.sh'
  'scripts/neb_agent/diagnose_path_geometry.py'
  'scripts/neb_agent/generate_path.py'
  'scripts/neb_agent/remote_monitor.py'
  'scripts/neb_agent/retrieval_prior_adapter.py'
  'scripts/neb_agent/submission.py'
  'scripts/neb_agent/utils_report.py'
  'scripts/neb_agent/utils_vasp.py'
  'scripts/scheduler_evidence.py'
  'scripts/ts_strategy_engine/active_learning.py'
  'scripts/ts_strategy_engine/active_learning_calibration.py'
  'scripts/ts_strategy_engine/active_learning_cli.py'
  'scripts/ts_strategy_engine/active_learning_common.py'
  'scripts/ts_strategy_engine/active_learning_domain.py'
  'scripts/ts_strategy_engine/active_learning_label.py'
  'scripts/ts_strategy_engine/active_learning_scheduler.py'
  'scripts/ts_strategy_engine/active_learning_training.py'
  'scripts/ts_strategy_engine/cli.py'
  'scripts/ts_strategy_engine/connectivity_evidence.py'
  'scripts/ts_strategy_engine/contract.py'
  'scripts/ts_strategy_engine/dimer_analysis.py'
  'scripts/ts_strategy_engine/evidence.py'
  'scripts/ts_strategy_engine/execution_decision.py'
  'scripts/ts_strategy_engine/execution_evidence.py'
  'scripts/ts_strategy_engine/execution_gate.py'
  'scripts/ts_strategy_engine/execution_gate_cli.py'
  'scripts/ts_strategy_engine/handoff.py'
  'scripts/ts_strategy_engine/strategy.py'
  'scripts/ts_validation/analyze_vfa.py'
  'scripts/ts_validation/connectivity.py'
  'scripts/ts_validation/prepare_vfa_from_ts_image.py'
  'scripts/vasp_inputs.py'
  'scripts/vasp_result_gate.py'
  'tests/test_alpha_fe_bulk_submission.py'
  'tests/test_aqcat25_ts_active_learning.py'
  'tests/test_artifact_io.py'
  'tests/test_config_boundaries.py'
  'tests/test_execution_gate_compatibility.py'
  'tests/test_external_command_boundaries.py'
  'tests/test_neb_execution_gate.py'
  'tests/test_neb_geometry.py'
  'tests/test_neb_remote_monitor.py'
  'tests/test_neb_submission.py'
  'tests/test_repository_contracts.py'
  'tests/test_ts_handoff.py'
  'tests/test_ts_strategy_engine.py'
  'tests/test_ts_validation.py'
  'tests/test_vasp_inputs.py'
  'tests/test_vasp_result_gate.py'
)
git add -- $security_and_boundaries

$actual = @(git diff --cached --name-only)
$delta = Compare-Object -ReferenceObject $security_and_boundaries -DifferenceObject $actual
if ($delta) { $delta; throw 'Staged paths do not match security_and_boundaries' }
```

## neb_path_quality

```powershell
Set-StrictMode -Version Latest
$neb_path_quality = @(
  'NEB_PATH_QUALITY_ARCHITECTURE.md'
  'PHASE_2B_BEHAVIOR_BASELINE.md'
  'PHASE_2B_BEHAVIOR_COMPATIBILITY.md'
  'PHASE_2B_CHANGESET_MANIFEST.md'
  'PHASE_2B_DIFF_REVIEW.md'
  'PHASE_2B_ENTRY_EQUIVALENCE_REPORT.md'
  'PHASE_2B_IMPLEMENTATION_REPORT.md'
  'PHASE_2B_PROPOSAL.md'
  'PHASE_2B_VERIFICATION_REPORT.md'
  'PHASE_2B_VERIFIED_CHANGESET.md'
  'configs/neb_agent/default_thresholds.yaml'
  'configs/neb_path_quality_control_v2.yaml'
  'scripts/neb_agent/magnetic_continuity.py'
  'scripts/neb_agent/path_quality_cli.py'
  'scripts/neb_agent/path_quality_control.py'
  'scripts/neb_agent/path_quality_service.py'
  'scripts/neb_agent/pilot_validation.py'
  'scripts/ts_strategy_engine/workflow.py'
  'tests/test_neb_path_quality_control.py'
  'tests/test_neb_path_quality_entrypoints.py'
  'tests/test_neb_pilot_validation.py'
)
git add -- $neb_path_quality

$actual = @(git diff --cached --name-only)
$delta = Compare-Object -ReferenceObject $neb_path_quality -DifferenceObject $actual
if ($delta) { $delta; throw 'Staged paths do not match neb_path_quality' }
```

## ts_endpoint

```powershell
Set-StrictMode -Version Latest
$ts_endpoint = @(
  'AGENT_RULE_TS_ENDPOINT.md'
  'PHASE_3A_CHANGESET_MANIFEST.md'
  'PHASE_3A_REPORT.md'
  'PHASE_3B_BEHAVIOR_COMPATIBILITY.md'
  'PHASE_3B_BEHAVIOR_VERIFICATION.md'
  'PHASE_3B_CHANGESET_MANIFEST.md'
  'PHASE_3B_DIFF_REVIEW.md'
  'PHASE_3B_IMPLEMENTATION_PLAN.md'
  'PHASE_3B_IMPLEMENTATION_REPORT.md'
  'PHASE_3B_PRECHANGE_SNAPSHOT.md'
  'PHASE_3B_VERIFICATION_REPORT.md'
  'PHASE_3B_VERIFIED_CHANGESET.md'
  'TS_ENDPOINT_API_CONTRACT.md'
  'TS_ENDPOINT_BEHAVIOR_BASELINE.md'
  'TS_ENDPOINT_CURRENT_ARCHITECTURE.md'
  'TS_ENDPOINT_DUPLICATION_AUDIT.md'
  'TS_ENDPOINT_FROZEN_ISSUES.md'
  'TS_ENDPOINT_ISSUE_CLOSURE_REPORT.md'
  'TS_ENDPOINT_REFACTORED_ARCHITECTURE.md'
  'configs/structure_purpose_routing.yaml'
  'configs/ts_connectivity_gate.yaml'
  'modules/structure_purpose_manager.py'
  'modules/ts_endpoint_database.py'
  'modules/ts_endpoint_evidence.py'
  'modules/ts_endpoint_generator.py'
  'modules/ts_endpoint_validator.py'
  'tests/test_structure_purpose_manager.py'
  'tests/test_ts_endpoint_contracts.py'
)
git add -- $ts_endpoint

$actual = @(git diff --cached --name-only)
$delta = Compare-Object -ReferenceObject $ts_endpoint -DifferenceObject $actual
if ($delta) { $delta; throw 'Staged paths do not match ts_endpoint' }
```

## documentation_and_release_baseline

```powershell
Set-StrictMode -Version Latest
$documentation_and_release_baseline = @(
  'AGENTS.md'
  'ARCHITECTURE.md'
  'BASELINE_INTEGRITY_REPORT.md'
  'CHANGESET_MANIFEST.md'
  'CLEAN_CHECKOUT_VERIFICATION.md'
  'CONDITION_CLOSURE_REPORT.md'
  'DEPRECATED_CODE.md'
  'E_SOURCE_ARCHITECTURE.md'
  'FINAL_API_COMPATIBILITY_REPORT.md'
  'FINAL_ARCHITECTURE.md'
  'FINAL_AUDIT_CLOSURE_MATRIX.md'
  'FINAL_BACKLOG.md'
  'FINAL_BEHAVIOR_COMPATIBILITY_REPORT.md'
  'FINAL_CHANGESET_MANIFEST.md'
  'FINAL_CODE_QUALITY_AUDIT.md'
  'FINAL_COMMIT_PLAN.md'
  'FINAL_REFACTOR_REPORT.md'
  'FINAL_STAGING_PLAN.md'
  'FINAL_VERIFICATION_REPORT.md'
  'PHASE_2A1_CLOSURE_REPORT.md'
  'PHASE_2A_REPORT.md'
  'PROJECT_AUDIT.md'
  'README.md'
  'REFACTOR_CHANGESET.md'
  'REFACTOR_PLAN.md'
  'REFACTOR_REPORT.md'
  'REVIEW_BASELINE_V2.md'
  'REVIEW_BASELINE_V3.md'
  'SOURCE_BASELINE_PLAN.md'
  'SOURCE_PROVENANCE_REPORT.md'
  'SUBMISSION_RECOVERY.md'
  'UNTRACKED_FILE_INVENTORY.md'
  'VERIFICATION_REPORT.md'
  'artifacts/final_release_baseline/blocked_migration_manifest.txt'
  'artifacts/final_release_baseline/config_manifest.txt'
  'artifacts/final_release_baseline/documentation_manifest.txt'
  'artifacts/final_release_baseline/final_release_sha256.txt'
  'artifacts/final_release_baseline/governance_manifest.txt'
  'artifacts/final_release_baseline/parent_review_baseline_v2_sha256.txt'
  'artifacts/final_release_baseline/production_source_manifest.txt'
  'artifacts/final_release_baseline/test_manifest.txt'
  'artifacts/refactor_changeset/changeset_sha256.txt'
  'artifacts/refactor_changeset/tracked_changes.patch'
  'artifacts/refactor_changeset/untracked_source_manifest.txt'
  'artifacts/review_baseline_v2/baseline_v2_sha256.txt'
  'artifacts/review_baseline_v2/current_config_manifest.txt'
  'artifacts/review_baseline_v2/current_document_manifest.txt'
  'artifacts/review_baseline_v2/current_migration_manifest.txt'
  'artifacts/review_baseline_v2/current_source_manifest.txt'
  'artifacts/review_baseline_v2/current_test_manifest.txt'
  'artifacts/review_baseline_v2/parent_baseline_sha256.txt'
  'artifacts/review_baseline_v3/baseline_v3_sha256.txt'
  'artifacts/review_baseline_v3/parent_v2_sha256.txt'
  'artifacts/review_baseline_v3/phase_2b_verified_document_manifest.txt'
  'artifacts/review_baseline_v3/phase_2b_verified_source_manifest.txt'
  'artifacts/review_baseline_v3/phase_2b_verified_test_manifest.txt'
  'artifacts/source_baseline/baseline_sha256.txt'
  'artifacts/source_baseline/formal_config_paths.txt'
  'artifacts/source_baseline/formal_migration_paths.txt'
  'artifacts/source_baseline/formal_source_paths.txt'
  'artifacts/source_baseline/formal_test_paths.txt'
  'docs/00_PROJECT_BRIEF.md'
  'docs/01_METHOD_PROTOCOL.md'
  'docs/10_TS_VALIDATION_PROTOCOL.md'
  'docs/14_CODE_ARCHITECTURE_GUIDE.md'
  'modules/convergence_workflow/README.md'
  'modules/transition_state_search/README.md'
  'modules/transition_state_search/strategy_rules.md'
  'scripts/README.md'
)
git add -- $documentation_and_release_baseline

$actual = @(git diff --cached --name-only)
$delta = Compare-Object -ReferenceObject $documentation_and_release_baseline -DifferenceObject $actual
if ($delta) { $delta; throw 'Staged paths do not match documentation_and_release_baseline' }
```

## blocked_migrations

```powershell
Set-StrictMode -Version Latest
$blocked_migrations = @(
  'GOVERNANCE_DOCUMENT_DECISION.md'
  'MIGRATION_REVIEW.md'
  'MIGRATION_REVISION_BACKLOG.md'
  'modules/calculation_registry/migrations/001_ts_endpoint_records.sql'
  'modules/calculation_registry/migrations/001_ts_endpoint_records_rollback.sql'
)
git add -- $blocked_migrations

$actual = @(git diff --cached --name-only)
$delta = Compare-Object -ReferenceObject $blocked_migrations -DifferenceObject $actual
if ($delta) { $delta; throw 'Staged paths do not match blocked_migrations' }
```

## Prohibited-path check after each staging block

```powershell
$staged = @(git diff --cached --name-only)
$explicitForbidden = @(
  'tasks/current_task.md',
  'tasks/backlog.md',
  'docs/02_CURRENT_STATE.md',
  'docs/03_DECISIONS_LOG.md',
  'docs/04_ERROR_LOG.md',
  'docs/05_FILE_INDEX.md',
  'docs/06_MODULE_MAP.md',
  'docs/13_WORK_HANDOFF.md'
)
$forbidden = @($staged | Where-Object {
  $_ -match '^(calculations|outputs|reports|data|tasks)/' -or
  $_ -match '(^|/)(__pycache__|\.pytest_cache|runtime)(/|$)' -or
  $_ -match '\.(sqlite3?|db|pyc|pkl|npz|out|log)$' -or
  $_ -in $explicitForbidden
})
if ($forbidden) { $forbidden; throw 'Forbidden path entered the index' }
```

`artifacts/refactor_changeset/tracked_changes.patch` and the baseline manifests
are formal review evidence. They contain no calculation directory payload and
are the only generated review artifacts admitted by this plan.

## Migration-specific guard

When reviewing `blocked_migrations`, confirm that the staged set is exactly five
review-only files and that no migration runner, schema version, or database file
is present:

```powershell
git diff --cached --name-only
Select-String -Path MIGRATION_REVISION_BACKLOG.md,GOVERNANCE_DOCUMENT_DECISION.md `
  -Pattern 'REVISED|PROHIBITED|REQUIRES_EXPLICIT_AUTHORIZATION'
git diff --cached --name-only -- scripts data configs modules/calculation_registry
```

The final command must list only the two SQL draft paths under
`modules/calculation_registry/migrations/`; it must not list the main schema,
runner code, config, or data.

## Final all-commit scope check

After the user has manually created all five commits, compare their union with
this plan using the pre-integration parent:

```powershell
$BASE_COMMIT = '<PRE_INTEGRATION_COMMIT>'
$integrated = @(git diff --name-only "$BASE_COMMIT..HEAD")
$expected = @(
  $security_and_boundaries
  $neb_path_quality
  $ts_endpoint
  $documentation_and_release_baseline
  $blocked_migrations
) | Sort-Object -Unique
$delta = Compare-Object -ReferenceObject $expected -DifferenceObject $integrated
if ($delta) { $delta; throw 'Integrated paths differ from the reviewed allowlist' }
```

The arrays must be loaded from this plan in the same PowerShell session, or
copied into a dedicated local review script without editing their contents.

## Non-actions

No `git add`, `commit`, `push`, `tag`, migration, database write, SSH, LSF,
`bsub`, `bkill`, VASP, or NEB command was executed while producing this plan.
