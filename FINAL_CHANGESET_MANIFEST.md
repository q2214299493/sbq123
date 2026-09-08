# Final Changeset Manifest

Date: 2026-07-27

## Scope

This manifest records the completed refactor, the authorized endpoint issue
closure, and manual-integration preparation. It excludes the pre-existing
calculation/runtime dirty worktree.

The final formal asset set contains:

- 128 production source/skill assets;
- 39 tests and fixtures;
- 29 formal configuration/Schema files;
- 10 authoritative governance documents;
- 2 review-only endpoint migration files;
- 120 documentation files.

Each row in `artifacts/final_release_baseline/` records path, bytes, Git
worktree status, and SHA-256. Those file-level manifests are the exhaustive
inventory.

## Endpoint closure changes

Production/configuration:

1. `configs/structure_purpose_routing.yaml`
2. `modules/ts_endpoint_evidence.py`
3. `modules/ts_endpoint_generator.py`
4. `modules/ts_endpoint_validator.py`
5. `modules/ts_endpoint_database.py`
6. `modules/calculation_registry/migrations/001_ts_endpoint_records.sql`
7. `modules/calculation_registry/migrations/001_ts_endpoint_records_rollback.sql`

Tests:

8. `tests/test_ts_endpoint_contracts.py`
9. `tests/test_repository_contracts.py`

Behavior changes are recorded in `TS_ENDPOINT_ISSUE_CLOSURE_REPORT.md`.

## Final reports and plans

- `FINAL_AUDIT_CLOSURE_MATRIX.md`
- `FINAL_CODE_QUALITY_AUDIT.md`
- `FINAL_ARCHITECTURE.md`
- `FINAL_API_COMPATIBILITY_REPORT.md`
- `FINAL_BEHAVIOR_COMPATIBILITY_REPORT.md`
- `FINAL_BACKLOG.md`
- `FINAL_CHANGESET_MANIFEST.md`
- `FINAL_REFACTOR_REPORT.md`
- `FINAL_VERIFICATION_REPORT.md`
- `FINAL_STAGING_PLAN.md`
- `FINAL_COMMIT_PLAN.md`
- `CLEAN_CHECKOUT_VERIFICATION.md`
- `TS_ENDPOINT_ISSUE_CLOSURE_REPORT.md`

## Release-baseline artifacts

1. `artifacts/final_release_baseline/parent_review_baseline_v2_sha256.txt`
2. `artifacts/final_release_baseline/production_source_manifest.txt`
3. `artifacts/final_release_baseline/test_manifest.txt`
4. `artifacts/final_release_baseline/config_manifest.txt`
5. `artifacts/final_release_baseline/governance_manifest.txt`
6. `artifacts/final_release_baseline/blocked_migration_manifest.txt`
7. `artifacts/final_release_baseline/documentation_manifest.txt`
8. `artifacts/final_release_baseline/final_release_sha256.txt`

The binding file hashes the other seven files and intentionally excludes
itself.

## Migration classification

The two SQL files remain in the historical staging group named
`blocked_migrations`, but their implementation review status is now:

- `FORMAL_MIGRATION`;
- `REVISED`;
- direct SQL execution prohibited;
- real-database execution requires explicit path-specific authorization;
- non-empty rollback prohibited.

No SQL was run against the real registry.

## Exclusions

The release manifests and staging allowlist exclude:

- `calculations/`, `outputs/`, `data/`, `archive/`, and caches;
- databases, VASP artifacts, scheduler evidence, and runtime state;
- credentials and private paths;
- operational `tasks/` and current-state/log/index/handoff documents.

These exclusions are release-scope decisions, not deletion.

## Manual integration

`FINAL_STAGING_PLAN.md` contains 182 exact, disjoint paths across five manual
groups. No `git add`, commit, push, or tag was executed.
