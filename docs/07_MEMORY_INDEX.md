# Memory Index

This index tracks controlled migration progress. It does not replace the original source files.

## Source Inventory

| Source | Availability | Intended Use | Notes |
|---|---|---|---|
| `C:\Users\86177\.codex\memory\sessions\active-session.md` | Available | primary legacy session summary | Review by bounded category only. |
| `modules/memory_migration/archive/PROJECT_CONTEXT_MEMORY.md` | Available | secondary project summary and cross-check | Deduplicate against the primary memory. |
| Local `neb_Abridge_to_D_*`, `_tmp_*`, `_diag_*`, and `_pre*` folders | Available | verify historical structures, jobs, and diagnostics | Scientific files are read-only during migration. |
| Remote archived job folders | Available | verify job IDs, archive paths, and final outputs | Key NEB/DIMER directories were inventoried in `MM-003`. |
| Old chat transcripts outside the listed memory files | Needs confirmation | recover missing decisions only | Do not copy full conversations. |

## Category Progress

| Category | Destination | Status | Last Batch | Notes |
|---|---|---|---|---|
| Adsorption energies and endpoint origins | `docs/08_HISTORICAL_RESULTS.md` | Migrated | `MM-002` | Raw clean/gas OUTCAR paths remain uncertain. |
| DIMER failures and parameter lessons | `docs/08_HISTORICAL_RESULTS.md` | Migrated | `MM-003` | Only decisive failure classes retained. |
| Historical NEB diagnostics | `docs/08_HISTORICAL_RESULTS.md` | Migrated | `MM-003` | Path, periodicity, SCF/path separation, and MPI lessons retained. |
| Fe convergence tests | `docs/08_HISTORICAL_RESULTS.md` | Migrated | `MM-002` | Baselines verified; extra sweep interpretation remains open. |
| MKM, KMC, and reactor planning | `docs/08_HISTORICAL_RESULTS.md` and module map | Migrated | `MM-004` | Downstream modules registered as planned/blocked, not completed. |
| Server templates and recurring commands | `docs/09_USER_PREFERENCES.md` | Migrated | `MM-001` | Live server paths were checked on 2026-06-23. |
| User fixed preferences | `docs/09_USER_PREFERENCES.md` | Migrated | `MM-001` | Twenty durable records accepted; one needs confirmation. |
| Historical job IDs and archive paths | `docs/08_HISTORICAL_RESULTS.md` | Migrated | `MM-003` | Repetitive/transient jobs excluded. |
| Calculation results worth preserving | `docs/08_HISTORICAL_RESULTS.md` | Migrated | `MM-002,MM-003` | Values and lessons carry verification qualifiers. |
| Repository-first operation and retention policy | `docs/09_USER_PREFERENCES.md` and external continuity summaries | Migrated | `MM-005` | Durable rules retained; failed-job and transient monitoring logs excluded. |
| Corrected true Fe(110) dataset policy | external continuity summaries | Migrated | `MM-005` | Facet correction and the pending unified-thickness gate retained. |

## Batch Register

| Batch | Scope | Status | Accepted Items | Report |
|---|---|---|---:|---|
| `MM-000` | Module scaffolding only; no historical facts migrated | Completed | 0 | Not required |
| `MM-001` | Fixed preferences and current server templates | Completed | 20 | `modules/memory_migration/reports/MM-001_report.md` |
| `MM-002` | Adsorption, endpoints, and Fe convergence | Completed | 11 | `modules/memory_migration/reports/MM-002_report.md` |
| `MM-003` | Decisive NEB and DIMER diagnostics | Completed | 15 | `modules/memory_migration/reports/MM-003_report.md` |
| `MM-004` | MKM, KMC, and reactor workflow planning | Completed | 10 | `modules/memory_migration/reports/MM-004_report.md` |
| `MM-005` | Repository-first rules and corrected true Fe(110) state | Completed | 7 | `modules/memory_migration/reports/MM-005_report.md` |

## Migration Completion

All supported categories have been reviewed through `MM-005`. Remaining `Needs confirmation` items are evidence gaps, not unmigrated categories. The original memory files remain available for audit; their dated authoritative summaries point back to this repository.

Progress status values: `Not started`, `In review`, `Partial`, `Migrated`, or `Blocked`.
