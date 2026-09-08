# Review Baseline v2

Date: 2026-07-27  
Baseline type: additive review baseline  
Parent: `artifacts/refactor_changeset/changeset_sha256.txt`

## Result

Review baseline v2 records the accepted Phase 2A source baseline, the exact
repository-artifact contract expansion, the governance decision, and the
blocked migration state. It does not replace or rewrite the historical A/B/C
review chain.

The SHA-256 of the parent file is
`4e6e65ef073580b91e8ee971c77f096a478485e92ac8f7001c106806121c6efc`,
as recorded in `artifacts/review_baseline_v2/parent_baseline_sha256.txt`.

## Manifest scope

| Manifest | Bound content |
| --- | --- |
| `current_source_manifest.txt` | 10 Phase 2A `FORMAL_SOURCE` files |
| `current_test_manifest.txt` | 6 Phase 2A `FORMAL_TEST` files plus `tests/test_repository_contracts.py` |
| `current_config_manifest.txt` | 3 Phase 2A `FORMAL_CONFIG` files |
| `current_migration_manifest.txt` | 2 `FORMAL_MIGRATION` files with `BLOCKED`, `PROHIBITED`, and `NEEDS_REVISION` status |
| `current_document_manifest.txt` | governance, Phase 2A/2A.1 review documents, the historical changeset manifest, and the five source-baseline files |

Every current manifest records repository-relative path, Git status, byte
size, and SHA-256. The migration manifest additionally records its four frozen
status fields.

The five accepted source-baseline files are preserved and recorded:

| Path | SHA-256 |
| --- | --- |
| `artifacts/source_baseline/baseline_sha256.txt` | `4dd963fc31e65e8f7f5ebd1e56d9958100547918f9817d180e45632ebcf3b86a` |
| `artifacts/source_baseline/formal_config_paths.txt` | `7c97534237a792a627701351caf5f9ed488ebd523ef93b26692e7003732a4e6e` |
| `artifacts/source_baseline/formal_migration_paths.txt` | `d32dfcf660f3d9031b6116ef44345320710fd1b17b176ae176e952b7da3e6475` |
| `artifacts/source_baseline/formal_source_paths.txt` | `42c2b21f30b0c1eb8c23c8a0ff18aded2defe9909937edb88249a22750bfdee9` |
| `artifacts/source_baseline/formal_test_paths.txt` | `3ae46e2af2fbb03ed4c3fe4bef0a73296f61db27b172d81e2371815f7d012995` |

## Explained repository-contract change

The earlier accepted change to `tests/test_repository_contracts.py` added an
exact five-file allowance for `artifacts/source_baseline/`; this made the
historical patch no longer reverse-applicable to the current test file. Phase
2A.1 keeps that accepted change and adds only the exact seven-file
`artifacts/review_baseline_v2/` allowance.

The artifact checks now use one exact layout mapping. There is no
`artifacts/**` wildcard and no prefix or suffix allowance. Four regression
tests prove:

1. the exact three-directory layout is accepted;
2. an undeclared file is rejected;
3. an undeclared directory is rejected;
4. a copied calculation file named `OUTCAR` is rejected.

The pre-existing exact three-file `artifacts/refactor_changeset/` and exact
five-file `artifacts/source_baseline/` constraints remain unchanged in
substance.

## Governance and migration decisions

`AGENT_RULE_TS_ENDPOINT.md` is registered by the project owner as
`FORMAL_GOVERNANCE_DOCUMENT`. It governs agent behavior, approvals, and the
endpoint workflow; it does not replace configuration Schema, formal scientific
protocol, tested code logic, or human scientific review.

Both endpoint SQL files remain `FORMAL_MIGRATION`, but integration is
`BLOCKED`, execution is `PROHIBITED`, and review is `NEEDS_REVISION`. This
baseline creates no execution authority.

## Exclusions

Calculation inputs, calculation outputs, runtime state, generated outputs,
database files, and database backups are excluded. Existing dirty-worktree
calculation/runtime content is not reclassified or copied into this baseline.

## Chain verification

- All 25 entries in the existing source baseline matched their recorded
  SHA-256 before and after Phase 2A.1.
- The historical patch, untracked-source manifest, changeset hash file, and
  historical `CHANGESET_MANIFEST.md` hash remained byte-identical.
- `baseline_v2_sha256.txt` binds the six v2 input/current manifests, all four
  Phase 2A.1 reports, and the five source-baseline files. It intentionally does
  not hash itself.
