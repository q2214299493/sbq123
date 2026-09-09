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
