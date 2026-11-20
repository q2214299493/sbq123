# Thermochemistry qualification at 523 K

The 523 K scenario uses metallic Fe(110), a 1 bar gas standard pressure and the provisional site-based surface activity definition. CO and H₂ contribute 8.3 and 16.7 bar to a 25 bar syngas feed. These four surface reactions have no gas-phase stoichiometric term. The feed alone cannot set H* or CO* activities. [Operating reference](../phase3_2_3_2/operating_conditions.json) · [Thermochemistry reference](../phase3_2_3_2/thermochemistry_reference.json)

| Local saddle | Verified VFA job | Active atoms, zero-based | Modes; excluded reaction coordinate | Use in this pilot |
|---|---|---|---|---|
| R1 CO dissociation | 9694935 | C45, O46 | 6; mode 6 | Grade A local mode evidence. Endpoint spectra and matched thermal reference pending. |
| R2 C–H formation | 9721851 | Fe32,37,41,43,44; C45, H46 | 21; mode 21 | Grade A local mode evidence. The five mobile Fe atoms are part of this Hessian. |
| R3 C–C coupling | 2260 | C45, C46, O47, H48 | 12; mode 12 | Grade A. Local harmonic ZPE 0.51405165 eV and conditional 523 K Gibbs correction +0.27948341 eV per TS. |
| R4 INT06→MID | 9798421 | Fe37–40, H49 | 15; mode 15 | Grade A CI-NEB segment. Scoped hydrogen migration spectrum. |
| R4 MID→FS-A | 9747902 | O47, H49 | 6; mode 6 | Grade A DIMER segment. Scoped O–H formation spectrum. |
| R4 IS-A→INT06 | No accepted VFA identified | Unknown | Unknown | DIMER 9833429 requires final-mode review. Its force convergence alone supplies no partition function. |

Each of the five available frequency OUTCAR hashes matches the registry. The frequency input and associated saddle have identical ordered species, matching cells and maximum atom-by-atom periodic displacements below 1.2 × 10⁻¹¹ Å. Each signed spectrum matches its own active Cartesian dimension and registered imaginary frequency. Full signed modes, original constraints, settings and hashes are in the [evidence matrix](evidence_matrix.json).

The thermochemistry parser checked all five spectra. The harmonic routine reproduced R3 from the exact archived signed frequencies, its documented unit scale, and the Grade A exclusion. The retained positive modes give ΔHthermal = 0.23455413 eV and S = 0.0008969835 eV/K; the increment excludes ZPE. The finite-temperature correction includes ZPE once. The other spectra establish local mode assignments. The scoped search found no corresponding project-reviewed scaling and 523 K correction convention for those states. Subspaces differ across the R4 segments. No common scale, cutoff or matching endpoint spectrum was assigned.

**IS and FS were checked independently for each step.** Twelve physical Hessian directories from the previous inventory and current reaction trees were screened against the eight selected endpoints and the internal R4 segment endpoints. No frequency POSCAR matched an endpoint by ordered atoms, cell and coordinates (1e−6 Å screening tolerance). JSON correction and scaling fields were also searched in the named source directories. This local screen leaves unregistered or externally held material open for Scientific Intake. [Comparison results and search scope](thermochemistry_search.json)

For each state, supply a structure-bound signed spectrum with its reviewed active atoms/constraints and low-frequency treatment, **or** compatible reviewed ZPE, thermal enthalpy increment, entropy and Gibbs correction at the selected temperature and standard state. A local VASP ID is optional. Prioritize records already available to the researcher. No new calculation was shown to be necessary. The R3 endpoint audit supplies the full field-level checklist. [Endpoint evidence](../phase3_2_3_1/missing_data.md)
