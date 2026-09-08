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
