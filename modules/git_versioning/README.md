---
document_class: CURRENT_REFERENCE
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: MODULE_CONTRACT_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Git Versioning Module

## Purpose

Version project state, reproducible scientific inputs, scripts, and concise reports without committing licensed pseudopotentials or large VASP runtime output.

## Tracked by Default

- Project rules and state under `AGENTS.md`, `docs/`, and `tasks/`.
- Module documentation and concise reports.
- Source scripts and VASP/VTST input structures and settings.
- Reviewed geometry tables, path rationale, and small visualization files.
- Reusable code under `scripts/` or repository-backed skills; `pyproject.toml` and `tests/` define the current Python quality gate.

## Excluded by Default

- `POTCAR` and possible credentials.
- Raw VASP output such as `OUTCAR`, `WAVECAR`, `CHGCAR`, `vasprun.xml`, and `XDATCAR`.
- Temporary diagnostics, transfer archives, caches, and editor files.
- Raw optimized `CONTCAR`; copy an accepted endpoint to a clearly named `POSCAR`, `POSCARis`, `POSCARfs`, or `.vasp` file before versioning it.

One-off scripts and downloaded source snapshots belong under `archive/`. Calculation directories and imported packages are provenance snapshots; their embedded commands are not current defaults.

## Snapshot Command

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git_snapshot.ps1 -Message "task: concise description" -PathList "AGENTS.md;docs/02_CURRENT_STATE.md"
```

List every task-owned path. Omit `-Path` only when the whole worktree is intentionally in scope and has been reviewed.

Add `-Push` only after a private `origin` remote has been configured and verified:

```powershell
git remote add origin <PRIVATE_REPOSITORY_URL>
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/git_snapshot.ps1 -Message "task: concise description" -PathList "AGENTS.md;docs/02_CURRENT_STATE.md" -Push
```

The script stages the selected non-ignored changes, rejects known sensitive VASP files, credentials, and files larger than 10 MB, checks the staged diff, commits, and optionally pushes.

## Done Criteria

Sensitive/large files remain excluded, task-owned snapshots are reproducible, and the approved private remote accepts a verified test push.
