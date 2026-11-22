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
- optional comparison of comparable observables when matched MKM results are available
- Zacros `general_output.txt`, `specnum_output.txt`, `procstat_output.txt`, `history_output.txt`, `lattice_output.txt`, and restart metadata when present

Surface-reaction KMC is distinct from GCMC adsorption loading.

Phase 2.5 builds a periodic lattice and translates approved directed rates and molecular footprints into Zacros 4.0 inputs. The project configuration supplies basis sites, physical cell vectors, neighbor translations, initial state and reference-site density per cell. A typed graph check compares the number of distinct matching transitions with the reviewed event normalization. Zacros 4.0 read all four inputs and completed 20 synthetic Ni/Cu events. See the [field contract and assembly command](../../reports/multiphase/phase2_5_native_contracts.md) and [validation receipt](../../reports/multiphase/phase2_5/native_validation.json).

## Done Criteria

Phase 2.5.1 validated seeded mono- and bidentate lattices, pair interaction energies, and exact fixed-seed checkpoint continuation on the installed Zacros 4.0 build. Seed indices must follow a reviewed local-event leg order when the event model distinguishes site types. The repulsive rate-response test also exposed native activation-energy warning 804010. See the [per-feature matrix and benchmark outputs](../../reports/multiphase/phase2_5_1/capabilities.md).

The lattice/event model is traceable, detailed balance is checked, and the KMC outputs are reproducible. A KMC-only study can meet these criteria independently. When the objective includes comparison with MKM, establish comparability for each observable before interpreting differences. [Engine selection and cross-validation](../../docs/decisions/adaptive_mkm_kmc_optional_reactor.md)

For a generic network, consult the [Zacros 4.0 mapping audit](../../reports/multiphase/stage_b2_3_2_1/capabilities.md) and [oxide lattice requirements](../../reports/multiphase/stage_b2_3_2_1/oxide.md) before assigning typed edges, event multiplicity or per-inventory coverage.

The [seven-node oxide example](../../reports/multiphase/stage_b2_3_2_2/completion.md) exercises finite, open graph matching with two ordered molecular seeds. Its offline entry point returns a candidate lattice and event fragments, with separate counts for initial matches and maximum simultaneous occupancy.
