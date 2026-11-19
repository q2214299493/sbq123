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
- As of 2026-11-19 the supplied single, curve and map examples have result files. The local quickstart log dated 2026-06-26 confirms startup. Completion is unconfirmed (完成未确认). The Fe(110) model still needs a validated input and result. See the [installed-file assessment](../../reports/multiphase/external_engine_compatibility.md).

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

Phase 2.5 assembles a fixed-temperature CATKINAS single point with frozen gas partial pressures. It consumes an eligible Phase 2.4 dataset, verifies the supplied parameter table, and publishes a byte-hashed input directory. Independent text readback checks stoichiometry, indices, correction switches and both rate coefficients. The installed 20230524 P-code reported expiry before accepting the synthetic model on 2026-11-19. Native reading and numerical completion remain unconfirmed. See the [field contract and assembly command](../../reports/multiphase/phase2_5_native_contracts.md) and [validation receipt](../../reports/multiphase/phase2_5/native_validation.json).

- steady-state solution and site/mass-balance residuals
- TOF, selectivity, coverage, and DRC tables
- reproducible solver settings and provenance
- CATKINAS `result_INPUT*` folder metadata and parsed outputs, when execution is enabled

## Done Criteria

The [Phase 2.5.1 compatibility record](../../reports/multiphase/phase2_5_1/catkinas_compatibility.json) distinguishes the expired installation from the authorized November distribution. The newer P-code read the exact archived reaction and sites. Its equation generator reported no overall reaction and stopped in a symbolic assignment before returning either coefficient. See the [bounded target attempt](../../reports/multiphase/phase2_5_1/catkinas_target_attempt.json).

Mass/site balances close and the CATKINAS inputs, solver settings, rates, coverages, selectivity, and DRC outputs are reproducible and traceable.
