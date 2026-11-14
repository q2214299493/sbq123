---
name: imaginary-freq-correction
description: Route this project's TS frequency parsing, imaginary-mode assignment, A/B/C grading, optional connectivity diagnostics, partition-function eligibility, and kinetics-readiness questions through modules/ts_vibrational_validation. Use for NEB/CI-NEB/DIMER frequency validation; this skill has no independent mode-correction, TS-acceptance, or kinetics authority.
---

# Imaginary Frequency Correction

Use this skill only as a thin router to
`modules/ts_vibrational_validation/README.md`.

All repository paths below are relative to the current verified project root,
not the global skill directory. Use `configs/skill_routing.yaml` and the owning
module as the rule sources; this skill cannot override them.

## Route

1. Read `AGENTS.md`, `tasks/current_task.md`, the relevant section of
   `docs/02_CURRENT_STATE.md`, the module README, and
   `docs/10_TS_VALIDATION_PROTOCOL.md`.
2. Accept only a contract-bound, technically converged source candidate
   prepared through the repository transition-state workflow.
3. Use the module's repository entry points for VFA preparation, frequency and
   eigenvector analysis, grading, validation registration, and optional
   connectivity diagnostics under the source-method policy. Downhill
   connectivity is optional for DIMER and CI-NEB; ordinary NEB retains its
   existing connectivity requirement.
4. Use `configs/true_fe110_production.yaml` for the active partial-Hessian
   settings and frequency thresholds. Route INCAR generation or recovery
   through `modules/incar_custodian/`.

## Validation Boundary

- Record every imaginary frequency and eigenvector; assign the principal mode
  to the intended reaction coordinate using reviewed evidence.
- DIMER acceptance requires technical convergence, negative curvature, one
  accepted meaningful imaginary mode for the intended reaction, and complete
  hash-bound frequency evidence. Bidirectional downhill connectivity is not a
  DIMER acceptance gate.
- Raw imaginary-mode count, visual inspection alone, or file existence do not
  establish a TS grade.
- When both frequency thresholds are unset, the owning analyzer may apply the
  reviewed single-mode branch for DIMER or converged CI-NEB: normal completion,
  exactly one raw imaginary mode, accepted target-mode and geometry reviews,
  and current hash-bound source evidence remain required. CI-NEB additionally
  requires `single_imaginary_mode_assessment=accepted_target_mode` and an actual
  converged climbing-image path. Missing review, extra modes, incomplete output
  or an ambiguous assignment cannot use that branch. Partial or invalid
  threshold settings are configuration errors; never invent numerical cutoffs.
- Apply only the A/B/C precedence rules in
  `docs/10_TS_VALIDATION_PROTOCOL.md`. Only registered Grade A evidence is
  eligible for thermochemistry or kinetics.
- Exclude the accepted reaction-coordinate imaginary mode from the TS
  partition function. Never silently remove, convert, or relabel another mode.

This skill does not create an independent correction method, submit or stop
VASP jobs, accept a TS, modify a kinetic table, or invoke downstream kinetics
without the repository validation and execution gates.
