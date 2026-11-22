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

# Kinetic Data Schema

## Purpose

Translate validated DFT and thermochemistry outputs into machine-readable species, energy, reaction, barrier, rate, and coverage-dependence records.

For versioned catalyst and kinetics records, use the [multiphase JSON contracts and offline validator](multiphase_contracts.md).

## Required Inputs

- registered and validated adsorption states
- Grade A transition states
- consistent DFT energy branch and free-energy corrections
- units, temperature, pressure, reference convention, and provenance

## Outputs

- species table
- electronic and free-energy table
- balanced reactions and forward/reverse barriers
- rate expressions and prefactors
- coverage-dependence parameters with valid ranges
- export package for downstream post-processing tools:
  - CATKINAS-ready mean-field MKM input fields
  - Zacros-ready event/lattice/rate fields for surface KMC

No ambiguous free-text energy may feed kinetics.

## Post-Processing Handoff Rule

For partial local, external, literature and user-supplied evidence, use the
[scientific intake and scoped acceptance contract](scientific_intake.md).

CATKINAS and Zacros 4.0 consume only validated records from this module and the reaction-network module. They must not receive hand-entered energies or barriers unless each value has units, reference convention, source file, and review status.

## Done Criteria

Machine-readable tables, units, references, confidence/review fields, validators, and CATKINAS/Zacros export contracts exist.

## Condition-specific kinetic parameters

The offline parameter engine consumes a content-addressed reaction network and a reviewed choice of rate law. It reuses the Phase 1 parameter schema, including units, validity range, uncertainty and coverage terms. [Rate laws, review contract and export commands](kinetic_parameters.md)

## Reaction-to-model readiness

Run `python -m scripts.scientific_intake --kinetic-readiness PROJECT.yaml TASK.yaml` for an offline JSON result.
The project and task use the [existing Scientific Intake contract](scientific_intake.md). A task may supply
a hash-pinned `models` document in the kinetic parameter engine's bindings format, or an existing
`dataset`. Supply `intake` and `ts_review` to recalculate state corrections for the intake's reaction.
An optional `thermal_phase` selects the thermochemistry owner's phase convention.

For each context, `kinetic_readiness.reactions` contains conservation, state corrections, direction-specific
rates, blockers and evidence roles. A reaction can retain qualified parameters when a different reaction
prevents full-network assembly. The separate `engines.mkm` and `engines.kmc` entries contain native
file contents and a manifest when their respective preparation checks pass. Execution requires the
existing native execution gate. [Three offline examples](../../reports/workflow_development/stage_v2_1/completion.md)
