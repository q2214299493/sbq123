# Local Data Store

`project_registry.sqlite3` is the local machine-readable calculation registry. The binary database is generated from the versioned schema and is not a substitute for source calculation files.

Versioned artifacts:

- schema: `modules/calculation_registry/schema.sql`
- initializer: `scripts/init_registry.py`
- project rules: `docs/11_DATA_PROVENANCE_PROTOCOL.md`

Database backup/export policy is **Needs confirmation**. Do not insert guessed values; use null/unknown states with evidence notes.

`state_handoff/projection_manifest.json` is a versioned hash manifest for
managed Markdown views. Immutable repository-lifecycle events live under the
owning module rather than in the calculation registry. Generated review
proposals are cached under ignored `data/cache/state_handoff/`.
