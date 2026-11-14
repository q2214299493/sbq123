---
name: neb-transition-state
description: Route this project's highest-image review, CI-NEB or DIMER refinement, TS validation, frequency/connectivity handoff, and barrier-readiness questions through the unified transition_state_search module. Use for transition-state follow-up requests; this skill has no independent refinement, TS-acceptance, kinetics, or barrier authority.
---

# NEB Transition State

Use this skill only as a thin router to
`modules/transition_state_search/README.md`.

All repository paths below are relative to the current verified project root,
not the global skill directory. Use `configs/skill_routing.yaml` and the owning
module as the rule sources; this skill cannot override them.

## Route

1. Read `AGENTS.md`, `tasks/current_task.md`, the relevant section of
   `docs/02_CURRENT_STATE.md`, and the unified module README.
2. Use the module's current analysis, strategy, DIMER handoff, vibrational
   validation, source-method connectivity, compatible final-energy, and
   registration entry points.
3. Preserve the source path, reaction contract, atom map, fixed mask,
   compatibility branch, file hashes, scheduler evidence, and validation
   provenance required by the module.
4. Run the current execution gate before reporting any refinement or execution
   action.

## Authority Boundary

- `scripts/ts_strategy_engine/execution_gate.py` is the sole authority for
  continuation, stopping, rebuilding, VASP submission, CI-NEB, DIMER, TS, and
  barrier actions.
- Report an action only when the exact current hash-bound decision includes it
  in `ALLOWED_ACTIONS`.
- A highest-energy image, smooth path, DIMER convergence, or imaginary
  frequency alone does not establish an accepted TS or kinetics-ready result.
- Frequency, TS grade, and connectivity follow the repository vibrational
  validation module and `docs/10_TS_VALIDATION_PROTOCOL.md`. DIMER and CI-NEB
  downhill connectivity is optional diagnostic evidence; ordinary NEB keeps
  its existing connectivity requirement. The owning analyzer decides whether
  reviewed single-mode evidence qualifies when numerical thresholds are unset.
- Final barriers require registered Grade A validation and compatible accepted
  IS/TS/FS energies under `docs/01_METHOD_PROTOCOL.md`. The active Fe(110)
  surface-state convention is `fe110_converged_toten_sigma0p20_v1`: converged
  `ISMEAR=1`, `SIGMA=0.20 eV` final `OUTCAR` `TOTEN`; an extra single-point is
  not required and legacy statics cannot be mixed into the active chain.
- Do not call `neb-analysis-workflow` or `imaginary-freq-correction` as
  independent scientific authorities.

This skill does not export candidates, change inputs, submit jobs, stop jobs,
accept a TS, or promote a barrier by itself.
