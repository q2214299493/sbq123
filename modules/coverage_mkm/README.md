# Coverage-Self-Consistent MKM

## Purpose

Iterate coverage-dependent adsorption energies, barriers, or lateral interactions with the MKM solution.

## Primary Software

- CATKINAS is the preferred local tool when coverage dependence can be expressed through approved descriptor or energy-update functions.
- CATKINAS inputs may use descriptor scans or user-provided functions only after the interaction model, valid coverage range, and provenance are documented.
- Runtime and I/O details are owned by `configs/postprocessing_software.yaml`.

## Entry Gate

- functioning baseline MKM
- justified interaction model, parameters, valid coverage range, and convergence criteria
- traceable CATKINAS input transformation from the baseline kinetic dataset

## Outputs

- self-consistent coverages, corrected energies/barriers, rates, and convergence history
- checks for multiple steady states, oscillation, and parameter-range violations
- CATKINAS curve/map outputs when coverage-dependent scans are used

Use only when coverage dependence is evidenced; it is not an automatic replacement for baseline MKM.

## Done Criteria

The coverage iteration converges within declared tolerances, valid ranges are respected, and multiple-state or oscillatory behavior is checked and recorded.
