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

# Surface-Reaction KMC

## Purpose

Model site heterogeneity, diffusion, lateral interactions, and spatial correlations that mean-field MKM cannot represent.

## Primary Software

- Zacros 4.0 is the preferred local surface-reaction KMC engine; its verified path, shell entry, work area, and I/O contract are in `configs/postprocessing_software.yaml`.
- The example run proves software execution only, not project-specific scientific validity.

## Entry Gate

- lattice and site model
- elementary event catalog with validated rates/barriers
- diffusion and neighbor rules
- detailed-balance and boundary-condition definitions
- Zacros input files generated from traceable kinetic records, not manual untracked values

## Zacros Input Scope

- `simulation_input.dat`
- `lattice_input.dat`
- `energetics_input.dat`
- `mechanism_input.dat`
- optional `state_input.dat`

## Outputs

- event statistics, coverage evolution, spatial distributions, TOF, and uncertainty
- comparison with baseline MKM under matched conditions
- Zacros `general_output.txt`, `specnum_output.txt`, `procstat_output.txt`, `history_output.txt`, `lattice_output.txt`, and restart metadata when present

Surface-reaction KMC is distinct from GCMC adsorption loading.

## Done Criteria

The lattice/event model is traceable, detailed balance is checked, outputs are reproducible, and matched-condition comparison with baseline MKM exists.
