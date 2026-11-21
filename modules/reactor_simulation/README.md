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

# Reactor Simulation

## Purpose

For reactor-scale objectives, use validated macroscopic species source terms to predict conversion, yield, selectivity and profiles. The initial design targets are isothermal CSTR and PFR. Existing qualified source terms can supply the model independently of a new MKM or KMC run. [Reactor architecture decision](../../docs/decisions/adaptive_mkm_kmc_optional_reactor.md)

## Entry Gate

- validated macroscopic kinetic source terms with explicit units, normalization, operating conditions and applicability to the requested reactor conditions
- reactor type, feed, flow, temperature, pressure, catalyst loading, and site density
- transport and heat/mass-transfer assumptions

## Outputs

- equations, unit checks, boundary/initial conditions, profiles, and operating-condition sensitivity

## Done Criteria

Units close and conversion/selectivity profiles are reproducible under documented reactor, transport, and operating assumptions.
