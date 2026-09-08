# Implementation Status

## Implemented

- VASP final-energy, convergence-marker, electronic-step, OSZICAR, and numeric
  NEB image parsing.
- Standardized `vasp_result.json` persistence with source paths and explicit
  missing/error states.
- Typed kinetic record construction and non-overwriting dataset registration.
- Standalone reviewed kinetic-parameter handoff contract validation with
  units, source/dataset hashes, method fingerprints, scientific gates, manual
  review fields, and strict downstream eligibility.
- Independent scientific/provenance validation report generation.
- Validation-gated static CATKINAS and Zacros adapter generation.
- Shell-free, single-attempt CATKINAS/Zacros process execution with timeout,
  stdout/stderr, status, runtime, and history.
- Strict simulator result parsing and reaction-ID mapping.
- Neutral TOF, coverage, selectivity, and reaction-rate reporting.
- Seven-step fail-fast workflow state management and status inspection.
- Central configuration, phase-specific logs, reproducible environments,
  automated tests, and release documentation.

## Not implemented

- Automatic VASP or NEB calculation/submission.
- Automatic adsorption/reaction/mechanism discovery.
- AI reaction, barrier, or catalyst prediction.
- Activation-energy calculation or automatic missing-data completion.
- Import/promotion of approved handoffs into a new kinetic dataset version.
- Workflow or adapter consumption of approved handoffs.
- TS verification beyond storing existing evidence/status fields.
- RDS assignment, catalyst ranking, scientific interpretation, or optimization.
- Automatic failed/interrupted workflow retry.
- Guaranteed native executable CATKINAS or Zacros project generation.
- A scientifically complete redistributable end-to-end example.

## Release classification

Engineering preview: core modules and failure behavior are tested. The
standalone handoff contract is defined, but the scientific end-to-end loop is
still blocked by non-overwriting dataset promotion, workflow/adapter
integration, and native simulator-input contracts documented in
`CODE_REVIEW.md`.
