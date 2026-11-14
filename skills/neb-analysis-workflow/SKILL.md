---
name: neb-analysis-workflow
description: Route this project's VASP NEB/CI-NEB monitoring, diagnosis, force and geometry trends, completed-path review, and next-action questions through the unified transition_state_search module. Use for NEB status or analysis requests; this skill produces no independent continue, stop, rebuild, CI-NEB, DIMER, TS, or barrier authority.
---

# NEB Analysis Workflow

Use this skill only as a thin router to
`modules/transition_state_search/README.md`.

All repository paths below are relative to the current verified project root,
not the global skill directory. Use `configs/skill_routing.yaml` and the owning
module as the rule sources; this skill cannot override them.

## Route

1. Read `AGENTS.md`, `tasks/current_task.md`, the relevant section of
   `docs/02_CURRENT_STATE.md`, and the unified module README.
2. Use the module's canonical compact monitor and parsers. Treat scheduler
   output as queue-state evidence only and calculation files as electronic,
   ionic, force, energy, and geometry evidence.
3. Reuse parsed evidence within the checkpoint. Run detailed inspection only
   when the compact summary cannot resolve a blocker.
4. Run the repository path-quality evaluator and execution gate exactly as the
   module specifies when an action question is in scope.

## Authority Boundary

- Monitoring, parsers, geometry checks, force trends, and path-quality reports
  produce evidence only.
- `scripts/ts_strategy_engine/execution_gate.py` is the sole NEB action
  authority.
- Report continue, stop, rebuild, submit, CI-NEB, DIMER, TS, or barrier
  actions only when the current hash-bound decision lists the exact action in
  `ALLOWED_ACTIONS`.
- Never let a lower-priority pass override an earlier electronic, geometry,
  endpoint, mapping, path, or validation failure.
- Do not calculate or promote a final barrier directly from an NEB energy
  profile; follow the module's compatible final-energy and registration gates.
  `docs/01_METHOD_PROTOCOL.md` defines the active Fe(110) surface-state
  convention `fe110_converged_toten_sigma0p20_v1`: compatible converged
  `ISMEAR=1`, `SIGMA=0.20 eV` final `OUTCAR` `TOTEN`, without a required extra
  single-point. Legacy statics cannot be mixed into that active energy chain.

This skill does not call `neb-transition-state` as a separate authority and
does not own thresholds, VASP settings, job control, or scientific acceptance.
