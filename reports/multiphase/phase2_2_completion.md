# Phase 2.2 thermochemistry — 2026-11-19

The read-only engine calculates ZPE from a reviewed spectrum, finite-temperature state corrections from harmonic or documented precomputed inputs, and reaction and activation free energies from compatible states. Local calculation IDs are optional. [CLI and conventions](../../modules/thermochemistry/README.md)

## Capability audit and implementation

- The thermochemistry module previously contained its contract README. Phase 2.1 selected and assessed typed records, thermal bases and conditions; it supplied no numerical integration.
- The TS validation analyzer already parsed VASP mode headings and real and indexed displacement rows, and the Dimer/CI review owned the mode assignment. The new streaming reader shares the heading parser, derives the active Cartesian flags from the existing POSCAR reader, and hashes the original bytes. The NEB energy and force parsers retain their existing role.
- The implementation adds a harmonic oscillator kernel, an ideal-gas molecular contribution, a precomputed adapter and a reaction calculator. It keeps the original signed spectrum and identifies the single excluded TS coordinate. For limited user-accepted data it labels the result as a scoped estimate. No submission, execution gate, production registry or MKM route is called.
- The intake schema accepts optional model and uncertainty metadata. An unchanged Phase 2.1 document continues to validate. The base case was read without edits. Raw, precomputed and mixed routes all use the existing intake selections. The independent error model is optional and does not estimate missing uncertainties.

## Fe(110) evidence benchmark

Reparsed the actual job 2260 OUTCAR and POSCAR and checked both SHA-256 values, 12 signed wavenumbers and active indices 45–48 against the Phase 2.1 audit. The reviewed Grade A assignment identifies mode 12 (−318.644011 cm⁻¹). The **11 retained modes yield a partial-Hessian TS ZPE of 0.51405165 eV**, using unit scaling. The full report includes each included frequency, source hashes and settings. [Validation JSON](phase2_2_chco_validation.json)

| Electronic difference | eV |
|---|---:|
| TS − IS | 0.97360174 |
| TS − FS | 0.31429371 |
| FS − IS | +0.65930803 |

The archived DFT evidence establishes the electronic differences and the TS zero-point correction within that active subspace. IS and FS still lack compatible thermal evidence. Temperature and standard state are unspecified. The report therefore retains null endpoint corrections and a null reaction free-energy result.

## Numerical and regression validation

The analytical oscillator fixture has occupation one. It exercises unit conversion, ZPE, the thermal enthalpy increment, entropy and Gibbs correction independently. Very soft positive modes, frozen high-frequency modes, active subspaces, TS review bindings, uncertainty derivatives, gas pressure dependence, source mixing, closure, and incompatible inputs have targeted tests. Synthetic endpoint uploads exercise the complete numerical route; their numbers do not enter the Fe(110) evidence report. A separate synthetic surface spectrum (100, 500, 1500 cm⁻¹ at 450 K) gave 0.0708510860 eV, compared with 0.0708511232 eV from ASE 3.29.0 HarmonicThermo. Absolute difference was 3.72 × 10⁻⁸ eV.

The development validation passed **274 tests**: 26 new engine cases, 139 Phase 0/1/2.1 and packaging regressions, and 109 existing TS/scientific-contract tests. Compilation, import, schema and targeted Ruff checks passed. The tests assess software correctness. The case audit supports only the electronic and partial-Hessian TS results above.

**Next evidence step.** Supply mapped IS and FS spectra or compatible precomputed corrections, with the target temperature, standard state and the existing local thermal basis, then rerun the calculator on the base intake and the supplemental document.
