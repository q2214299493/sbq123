# MM-005 Migration Report

Date: 2026-06-28

## Scope

Durable repository-first workflow rules and the corrected true Fe(110) dataset state.

## Sources Reviewed

- `AGENTS.md`
- `tasks/current_task.md`
- `docs/01_METHOD_PROTOCOL.md`
- `docs/02_CURRENT_STATE.md`
- `docs/06_MODULE_MAP.md`
- User retention instruction dated 2026-06-28

## Accepted

1. The repository is the ordinary continuation source; external memory is only a dated pointer and recovery aid.
2. Use only `sunboquan-codex` and the active project root `~/sbq/agent/jobs`.
3. Calculation inputs from external data require the catalysis whitelist and ranked retrieval gate.
4. Corrected true Fe(110) uses nine Fe atoms per layer; the clean 4-8-layer campaign is complete.
5. Production thickness remains gated by matched 5-vs-7-layer adsorption/reaction observables; one selected thickness must be used consistently.
6. Continuity memory retains durable rules only and excludes failed-task and transient monitoring logs.

## Explicitly Excluded

- Failed NEB, DIMER, adsorption, or convergence task logs
- Historical scheduler states and repetitive job IDs
- Per-step forces, energies, and electronic iterations
- Raw output excerpts, generated movies, and full chat transcripts

## Destinations

- `docs/07_MEMORY_INDEX.md`
- `docs/09_USER_PREFERENCES.md`
- `C:\Users\86177\.codex\memory\sessions\active-session.md`
- `modules/memory_migration/archive/PROJECT_CONTEXT_MEMORY.md`
