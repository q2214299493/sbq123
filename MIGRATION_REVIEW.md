# Migration Review

Date: 2026-07-27

## Conclusion

**REVISED — SAFE FOR SEPARATE REVIEW, NOT AUTHORIZED FOR REAL EXECUTION**

The forward and rollback SQL remain formal review-only assets. All execution
must go through the guarded functions in `scripts/ts_endpoint/database.py`.
The historical `modules.ts_endpoint_database` path is a compatibility alias.

## Forward migration safeguards

`apply_ts_endpoint_migration()` now:

1. opens only an existing core-schema-v5 registry;
2. rejects endpoint metadata without its table;
3. validates a same-name table before treating the operation as complete;
4. checks all 14 columns, SQLite types, nullability, primary key, three foreign
   keys, reaction index, four-field uniqueness, check constraints, and
   `ts_endpoint_schema_version=1`;
5. starts `BEGIN IMMEDIATE` before new DDL;
6. validates the complete result before commit;
7. relies on the registry context manager to roll back any error.

An injected post-creation validation failure was tested and left neither the
table nor its version metadata behind.

## Rollback safeguards

- `apply_ts_endpoint_migration(..., rollback=True)` always refuses.
- `rollback_empty_ts_endpoint_migration()` requires the exact confirmation
  phrase `DROP EMPTY TS ENDPOINT TABLE`.
- The table is fully validated before rollback.
- Any non-empty table is refused.
- Empty rollback runs in an explicit transaction and verifies removal of both
  table and extension version.

There is intentionally no automatic destructive rollback path for endpoint
records.

## Version boundary

The endpoint persistence table is maintained as an optional, independently
versioned registry extension. It is not inserted into the core schema-version
chain because that would force unrelated version-5 registries to migrate and
would make current code reject the real registry before an authorized data
change.

The adapter does not run the extension migration during construction, queries,
or writes.

## Real registry evidence

Path: `data/project_registry.sqlite3`

- SHA-256 before revision verification:
  `4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb`
- No migration was executed against it.
- The final verification rechecks the same hash.

## Remaining gate

The code revision is complete. Actual application to a real database remains a
separate, path-specific, explicitly authorized operation with backup and
post-run verification.
