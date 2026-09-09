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

# Thermochemistry

## Purpose

Compute and audit ZPE, enthalpy, entropy, Gibbs free energy, and activation free-energy corrections.

## Entry Gate

- stable-state frequencies are validated
- TS is Grade A under `docs/10_TS_VALIDATION_PROTOCOL.md`
- temperature, pressure, standard states, and treatment of low modes are defined

## Outputs

- correction components for every species and TS
- corrected reaction and activation free energies with units and provenance
- documented exclusion of the reaction-coordinate imaginary TS mode

## Done Criteria

Every accepted species and TS has traceable correction components, assumptions, units, conditions, and corrected reaction/activation free energies.
