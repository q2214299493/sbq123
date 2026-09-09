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

# Baseline Mean-Field MKM

## Purpose

Solve the non-coverage-self-consistent mean-field mechanism for coverages, rates, TOF, selectivity, and degree of rate control.

## Primary Software

- CATKINAS is the preferred local mean-field MKM tool; its verified path, runtime, and I/O contract are in `configs/postprocessing_software.yaml`.
- The quickstart proves software execution only, not project-specific scientific validity.

## Entry Gate

- balanced reaction network
- validated free-energy barriers and prefactors
- temperature, pressure/feed, site density, and rate-law conventions
- CATKINAS input file generated from traceable kinetic records, not manual untracked values

## CATKINAS Input Scope

- reaction mechanism equations and site notation
- activation/free-energy inputs or approved scaling/BEP parameters
- gas pressure or concentration conditions
- initial/frozen coverages when specified
- calculation mode: single, curve, or map
- optional DRC and plotting settings

## Outputs

- steady-state solution and site/mass-balance residuals
- TOF, selectivity, coverage, and DRC tables
- reproducible solver settings and provenance
- CATKINAS `result_INPUT*` folder metadata and parsed outputs, when execution is enabled

## Done Criteria

Mass/site balances close and the CATKINAS inputs, solver settings, rates, coverages, selectivity, and DRC outputs are reproducible and traceable.
