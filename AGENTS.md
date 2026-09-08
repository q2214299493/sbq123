# Project Rules for Codex

## Minimal Startup

1. Read `tasks/current_task.md`.
2. Run `repo-state audit --phase start` for repository or calculation-state
   work. It is read-only; do not treat its findings as scientific evidence.
3. Read only the relevant section of `docs/02_CURRENT_STATE.md`.
4. Read `modules/README.md` and the README of the module that owns the task.
5. Read `docs/00_PROJECT_BRIEF.md` and `docs/01_METHOD_PROTOCOL.md` only when
   starting a calculation, changing a scientific method, or resolving a conflict.
6. Read decisions, errors, preferences, file indexes, historical records, and
   memory only when the task requires them. Memory is handoff-only unless the
   task explicitly concerns migration or recovery.

Work on the one executable step in `tasks/current_task.md`. Put displaced or
newly discovered work in `tasks/backlog.md`. Do not reconstruct project state
from chat history or ordinary `.codex` memory.

## Task Focus

- Identify the minimum files and live sources needed before inspecting anything.
- Do not recursively explore unrelated directories or load old calculations,
  archives, backups, or large logs unless the task requires them.
- Prefer local reusable scripts, compact parsers, `scp`, and short SSH commands
  over fragile remote one-liners.
- Never run, submit, stop, delete, rename, overwrite, restart, or resubmit a
  useful calculation without explicit user authority.

## Evidence and Authority

Use each source only for the state it can establish:

- Scheduler output is authoritative for queue state only.
- Calculation files are authoritative for electronic and ionic progress.
- Final structures and parsed outputs are authoritative for geometry and
  reported energies.
- Scientific validity requires the owning module's validation protocol.
- State documents summarize evidence but do not override live calculation files.
- Chat history and ordinary memory are not authoritative project state.

Always separate scheduler `PEND/RUN/DONE/EXIT`, electronic convergence, ionic or
force convergence, geometry validity, and scientific validity.

## Scientific Boundaries

- Backend roles and handoffs are authoritative only in
  `configs/execution_backends.yaml`.
- Use `BUCT(sbq)` / host `MZ73` only for AQCat25 GPU inference, adsorption
  candidate pre-relaxation/ranking, endpoint ML relaxation, IDPP/BA-Sella
  transition-state candidate acceleration, and force-model fine-tuning. Connect as
  `sbq@10sx4jr711576.vicp.fun:36039` with
  `C:\Users\86177\.ssh\id_ed25519_fe_agent`, `IdentitiesOnly=yes`; never read,
  display, copy, or modify the private-key contents. Remote writes are limited
  to `/home/sbq/sbq/`.
- Use only `sunboquan-codex` for VASP/VTST calculations; active calculation
  paths are in `docs/02_CURRENT_STATE.md`.
- `work` is the orchestration, evidence-gate, review, and registry authority.
  GPU candidates must return to `work` for review before any VASP handoff;
  direct GPU-to-VASP transfer and automatic remote submission are forbidden.
- AQCat25 adsorption energies/forces/relaxations and AQCat25/BA-Sella saddle
  guesses are predicted candidates only. They cannot remove an
  evidence-required adsorption motif by themselves, replace whitelist-first
  evidence or VASP results, prove a final adsorption site/global minimum, pass
  vibration/connectivity validation, or establish scientific acceptance.
- Follow the active compatibility branch defined in
  `docs/01_METHOD_PROTOCOL.md`.
- Never combine energies across incompatible XC functionals, POTCAR families,
  ENCUT convergence branches, slab models, magnetic conventions, occupation
  conventions, or reference-energy conventions.
- Use a validated and explicitly documented final-energy convention for every
  energy difference. Metallic slabs and isolated molecular references may use
  different occupation settings when scientifically required, but their final
  reported energies must follow `docs/01_METHOD_PROTOCOL.md`. Never mix
  undocumented or unconverged branches in one reported energy difference.
- Do not change a locked scientific protocol without explicit approval.
- Before a new calculation or externally seeded structure/path, use
  `modules/catalysis_data_retrieval/`. Search its whitelist first and stop when
  a usable matching motif exists. For adsorption-site selection only,
  `NO_WHITELIST_MATCH` permits its controlled authoritative-journal fallback;
  calculation modules never run an independent literature search.
- Use external adsorption evidence only to select and rank plausible motifs and
  to seed reviewed geometry such as sites, bond lengths, angles, heights, and
  orientations. Never import its energies into local results, the registry, or
  Excel; compatible local calculations alone determine reportable energies.
- Keep adsorption, convergence, NEB, DIMER, vibration, thermochemistry,
  kinetics, KMC, and reactor work in their owning modules.
- Use `modules/transition_state_search/README.md` for the unified NEB/CI-NEB/DIMER
  strategy and gates. Preserve atom order and
  Selective Dynamics; never use pure C/O endpoint interpolation. Run `dist.pl`
  and `nebmovie.pl 0` before review/submission, and `nebmovie.pl 1` after
  completion or stopping and before interpretation.
- `scripts/ts_strategy_engine/execution_gate.py` is the sole NEB execution
  authority. Parsers, monitors, path-quality checks, strategies, and workflows
  produce evidence only. Continue/stop/rebuild/VASP submission/CI-NEB/DIMER/TS
  or barrier actions require a current hash-bound gate decision that explicitly
  lists the action in `ALLOWED_ACTIONS`; executors must reject every missing,
  stale, or forbidden action. Apply the priority order in the transition-state
  module README, and never let a lower-priority pass override an earlier fail.
- Use `modules/incar_custodian/` for INCAR advice. Geometry, path, and mode
  failures take priority over parameter tuning.

For NEB and DIMER validation, follow the README of the owning module.

## Monitoring

- Prefer parsed summaries over raw VASP, scheduler, or script output.
- Query each required live source only as needed for one checkpoint and reuse
  the parsed result within the turn.
- Use the canonical compact NEB monitor in `modules/transition_state_search/README.md`.
  Detailed SCF, force, or log output is opt-in or reserved for a bounded
  diagnostic that summaries cannot resolve.
- Routine NEB summaries include queue state, completed steps, electronic
  status, each image's latest atomic/NEB force and trend, geometry verdict, and
  the main blocker.
- Run geometry parsing when geometry is requested, a warning needs diagnosis,
  or a calculation finishes or stops.
- Keep routine progress in chat; do not create report files unless requested.

## State and Modules

- Keep `docs/02_CURRENT_STATE.md` compact and replace-in-place, not historical.
- At the end of repository or calculation-state work, run
  `repo-state sync --safe-only`. Apply only review-free managed projections.
  If it returns a review request, show the exact proposal ID and choices to the
  user; do not select an answer or edit an event in place.
- Update state only when evidence, status, decision, blocker, path, or next
  action materially changes. A no-change check needs no repository edit.
- Record durable decisions in `docs/03_DECISIONS_LOG.md`, unresolved failures in
  `docs/04_ERROR_LOG.md`, important files in `docs/05_FILE_INDEX.md`, and module
  status in `docs/06_MODULE_MAP.md`.
- A module is `Planned`, `Active`, `Blocked`, or `Completed`. Mark it completed
  only when its done criteria and outputs exist.

## Context-Safe Inspection

Unknown, potentially large, binary, recursive, or log-like output must be
byte-capped. Check file size and type before reading an unknown file. Never dump
full large VASP outputs, databases, binaries, archives, backups, or large logs
into context. Prefer targeted extraction and compact parsers.

Default inspection pattern:

    COMMAND 2>&1 | head -c 4000

Output truncation is for inspection only. Do not infer command success from a
truncated pipeline. When the original exit status matters, capture and report it
separately. A truncated pipeline is not proof that validation, parsing, copying,
submission, or another state-changing command succeeded.

For context-safe shell inspection, follow `skills/context_safe_shell.md`.

For VASP output diagnosis, follow `skills/vasp_output_inspection.md`.

## Quality and Files

- Never invent facts. Use `Needs confirmation` when evidence is missing.
- Grade TS candidates only through `docs/10_TS_VALIDATION_PROTOCOL.md`; apply
  provenance rules only through `docs/11_DATA_PROVENANCE_PROTOCOL.md`.
- Keep reusable code under `scripts/` or repository-backed skills and
  one-off/downloaded material under `archive/`.
- Preserve user changes in a dirty worktree and avoid unrelated rewrites.

## Validation

Use the lightest validation that can confirm the current change.

- Text-only documentation changes: inspect the changed lines or diff only.
- Single Python-file changes: run `python -m py_compile FILE.py`.
- Single shell-file changes: run `bash -n SCRIPT.sh`.
- Local module logic changes: run Ruff on the changed files or owning module and
  run the directly related tests.
- Core workflow, parser, job-submission, production-result, or cross-module
  changes: run the relevant broader validation suite.
- Run the full repository test suite only when explicitly requested or when
  cross-module behavior may be affected.

Do not default to `ruff check .` when the repository contains generated,
archived, downloaded, calculation, or large runtime directories. Expand scope
only when shared behavior may be affected.

Never run expensive calculations, submit VASP jobs, or launch NEB, DIMER, MKM,
KMC, reactor, or other scientific workflows merely to validate a small code or
text change.

## Version Control

Do not commit or push unless the user explicitly requests it or
`tasks/current_task.md` explicitly authorizes it.

When a commit is authorized:

- include only task-owned changes;
- do not include unrelated user changes;
- never force-add ignored VASP outputs, `POTCAR`, credentials, or large runtime
  files.

Never push without explicit authorization. A local commit is not an off-machine
backup.

## Communication

Report only:

- what changed;
- what was validated;
- the validation result;
- remaining uncertainty or blockers.

Mention output truncation only when it could affect the conclusion. Show raw
diffs only when explicitly requested. Do not dump raw logs when a concise parsed
result is sufficient.
