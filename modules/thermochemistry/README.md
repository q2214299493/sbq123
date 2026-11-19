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

## Phase 2.2 executable interface

Read a VASP Hessian and its frequency POSCAR, or calculate directly from Phase 2.1 JSON. All commands write JSON to stdout. They read the named files without database or scheduler access.

```text
python -m scripts.thermochemistry parse OUTCAR POSCAR
python -m scripts.thermochemistry parse OUTCAR POSCAR --reaction-id example --state IS --thermal-basis reviewed-local-model
python -m scripts.thermochemistry calculate reports/multiphase/ch_co_intake_20261119.json --ts-review reports/multiphase/ch_co_frequency_audit_20261119.json --phase adsorbate
python -m scripts.thermochemistry calculate base.json upload.json --operation zpe --ts-review review.json
```

The parser records both hashes, the actual OUTCAR settings, all signed modes and the POSCAR's Cartesian activity flags. With a reaction and state it emits an unreviewed intake draft. Compare the expected Cartesian dimension with the parsed count and review the mapping to the electronic structure. Gas internal-mode projection can have a different dimension. Records from external software can supply the same signed cm⁻¹ array, expected count, mapped atoms, constraint description, structure identity, method and thermal basis. A partial Hessian describes just the selected degrees of freedom. Use zero-based atom numbers and one-based mode numbers.

The existing intake selects evidence by operation, structure, common basis and energy reference. Source metadata, scientific review, uncertainty and scoped human acceptance travel with the result. A usable but unverified input yields a scoped estimate. The calculator also compares active maps, constraints and scales across raw spectra. Use the same basis identifier on mixed raw/precomputed routes only after verifying the definitions, treatments and active subspace. Document any correspondence before normalizing equivalent labels or atom order.

For an endpoint, include every positive mode of the selected subspace. An imaginary mode or a zero harmonic quantum raises a diagnostic. For a TS, pass its existing Grade A mode review. The CHCO audit is accepted directly. An external review JSON can carry `grade`, `review_reference`, `structure_identity`, and `assignment`; for a raw TS spectrum also supply `mode_index`, `frequencies_cm1`, `atom_map`, `constraints` and the matching `source_artifact_hash` when known. These fields describe a completed owning-module or equivalent reviewed assignment. The engine consumes that decision. For precomputed TS data the scientific review of the corrections must cover the exclusion convention and common basis. Full calculations require temperature and standard state. A surface ZPE needs neither.

## Components and conventions

For each included frequency use ε = hcν̃ in eV, x = ε/(kT), and n = 1/(exp(x)−1). ZPE is Σ ε/2. The thermal enthalpy increment is Σ εn. The vibrational entropy is k Σ[xn − ln(1−exp(−x))]. The correction is ZPE + ΔHthermal − TS. The implementation uses expm1 for small x and exponential decay for large x. No soft-mode cutoff or frequency floor is applied. Very soft modes can make harmonic entropies physically unreliable even when the calculation is numerically stable. The SI definitions fix h, c, k and the joule/eV conversion. [NIST base unit definitions](https://www.nist.gov/si-redefinition/definitions-si-base-units)

For an adsorbate the fixed-slab harmonic Helmholtz contribution approximates its Gibbs correction with negligible pΔV. For a linear or nonlinear gas molecule, provide internal vibrational modes, operating pressure in Pa and a record-level `thermal_model` containing `phase: gas`, `mass_amu`, `moments_amu_angstrom2` (one perpendicular moment or three principal moments), `symmetry_number` and `electronic_degeneracy`. The engine adds ideal-gas translation including pV, classical rigid-rotor terms and ground-state degeneracy. This model assumes dilute gas, rotational temperatures well below T, and negligible excited electronic populations. Record the gas pressure convention explicitly. Gas rotation/translation is never added to a precomputed total. Reaction/path degeneracy belongs to the later rate model.

An intake `corrections` value uses eV per state for ZPE, the thermal enthalpy increment **excluding ZPE** and the Gibbs correction, plus eV/K per state for entropy. Include temperature, standard state, structure and thermal basis. Full inputs must satisfy the component sum (1 µeV absolute and 1e−9 relative tolerance). More coarsely rounded inputs need compatible precision or a documented re-expression. ZPE alone can be submitted for the ZPE operation. Energy differences retain their electronic and thermal parts. Reaction closure is checked to 1e−9 eV; endpoint gaps leave the combined reaction result empty.

Optional `thermal_model.frequency_scale` scales all wavenumbers and needs a `scaling_reference` for a non-unit factor. `independent_mode_sigma_cm1` gives one standard uncertainty per original mode. First-order propagation uses ∂ZPE/∂ε = 1/2 and ∂G/∂ε = 1/2 + n; the excluded TS mode contributes neither. The reported sigma is conditional on fixed temperature, scale, gas parameters and the chosen model. Precomputed records can supply `zpe_sigma_ev` and `gibbs_sigma_ev`, electronic records `electronic_sigma_ev`. Reaction sigmas use quadrature only under explicit `--independent-errors` and with all contributing sigmas. Correlation, model discrepancy and unknown errors remain outside this estimate. Textual uncertainty metadata is preserved.
