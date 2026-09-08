# Migration Revision Backlog

Date: 2026-07-27

## Current status

| File | Classification | Revision | Direct execution | Real-database execution |
| --- | --- | --- | --- | --- |
| `modules/calculation_registry/migrations/001_ts_endpoint_records.sql` | `FORMAL_MIGRATION` | `REVISED` | `PROHIBITED` | `REQUIRES_EXPLICIT_AUTHORIZATION` |
| `modules/calculation_registry/migrations/001_ts_endpoint_records_rollback.sql` | `FORMAL_MIGRATION` | `REVISED` | `PROHIBITED` | `PROHIBITED_FOR_NONEMPTY_TABLE` |

The former `BLOCKED / NEEDS_REVISION` implementation conditions are closed.
This does not authorize execution against `data/project_registry.sqlite3`.

## Closed revision requirements

1. Complete existing-table validation covers columns, types, nullability,
   primary key, foreign keys, indexes, uniqueness, check constraints, and the
   endpoint extension version.
2. Completion is not inferred from the table name.
3. Repeat execution validates the exact extension shape and then returns
   without DDL.
4. Forward DDL starts in an explicit transaction and post-validation failure
   rolls the extension back.
5. Legacy `rollback=True` is rejected.
6. The dedicated rollback API requires an exact confirmation phrase and an
   empty table.
7. Non-empty rollback is unconditionally rejected, so no automatic
   data-destroying backup/restore path exists.
8. Temporary SQLite tests cover forward, repeat, incompatible table,
   post-validation failure rollback, missing confirmation, non-empty refusal,
   and empty rollback.

## Version-chain decision

The endpoint table is an optional registry extension with its own
`ts_endpoint_schema_version=1`. It is not folded into the core
`schema_version=5` chain in this correction:

- existing version-5 registries continue to open unchanged;
- workflows that do not persist TS endpoints do not require an endpoint table;
- the adapter never creates or migrates the extension implicitly;
- an explicitly authorized caller must invoke the validated migration API.

This is a deliberate extension boundary, not an untracked version.

## Remaining authorization gate

Before any real database execution:

1. make a recoverable copy of the target database;
2. record its SHA-256 and schema summary;
3. obtain explicit project-owner authorization for that exact path;
4. run the validated API, not either SQL file directly;
5. verify `PRAGMA foreign_key_check`, extension schema, and the post-run hash.

No real database execution occurred during this revision.
