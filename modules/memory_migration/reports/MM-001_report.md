# MM-001 Migration Report

- Batch: `MM-001`
- Completed: 2026-06-23
- Scope: fixed preferences and current server templates
- Accepted records: 20
- Unresolved records: 1
- Scientific calculation files modified: none

## Sources

1. `C:\Users\86177\.codex\memory\sessions\active-session.md`
2. `modules/memory_migration/archive/PROJECT_CONTEXT_MEMORY.md`
3. `C:\Users\86177\.codex\skills\vasp-catalysis-workflow\SKILL.md`
4. Current `AGENTS.md` and `docs/01_METHOD_PROTOCOL.md`
5. Read-only checks on `sunboquan-codex`

## Verification

- Verified: `~/sbq/agent/jobs`, `~/vasp541std.lsf`, `~/vasp541vtst.lsf`, VASPKIT executable, and `~/bin/PBE` exist.
- Verified: `~/sbq/Fe_agent_demo` does not exist and is superseded for this project.
- Deduplicated recurring rules across both memory files.
- Excluded all scientific results and transient job history from this batch.

## Result

`docs/09_USER_PREFERENCES.md` now contains source-linked durable rules. One approval-policy ambiguity remains marked `Needs confirmation` and is recorded in the error log.
