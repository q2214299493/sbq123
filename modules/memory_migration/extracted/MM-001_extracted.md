# MM-001 Extracted Notes

## Scope Reviewed

- Legacy session memory: stable preferences and later corrections.
- Project context memory: duplicate check and late server/path corrections.
- VASP workflow skill: server tools, evidence gates, and submission checks.
- Current project rules: authoritative conflict resolution.

## Accepted Themes

Twenty durable preferences were accepted across project continuity, module/task management, server use, command safety, VASP templates, structure/path review, literature evidence, monitoring, failure response, and artifact placement.

## Conflicts Resolved

1. Remote root: legacy `~/sbq/Fe_agent_demo` is superseded by `~/sbq/agent/jobs`; the former is absent and the latter was verified on 2026-06-23.
2. Resume source: project state files now take precedence over legacy memory files.
3. Report location: this repository uses `reports/`; the legacy external report folder is not the project default.
4. NEB image count: no universal fixed count was retained. The active input and core allocation determine image count; ordinary-before-CI staging remains durable.

## Unresolved Conflict

- Whether every submission requires a fresh explicit approval or whether a user may delegate autonomous submission for a task remains `Needs confirmation`. Pre-submission review and all technical gates remain mandatory.

## Excluded from MM-001

- energies, barriers, forces, geometries, and convergence values
- historical job status and archive results
- DIMER and NEB failure details
- MKM/KMC/reactor planning content
- long narrative or duplicated chat-derived text
