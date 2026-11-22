# V.1.2.1 · Fe(110) CH* + CO* → CHCO* thermochemistry

**Qualification is partial.** The existing evidence supports three compatible electronic energies and one state-local vibrational result, the TS ZPE of **0.51405165 eV**. Neither endpoint has a qualified spectrum or precomputed correction in the searched holdings. Temperature and standard state are also unspecified. Reaction Gibbs energy, both activation Gibbs energies and their closure residual remain unavailable. This assessment uses baseline `629ada1264bb40796f2458ba7c5b948ccaa2e83c` and records the evidence at its existing level of review.

## State-by-state compatibility

| State | Accepted structure SHA-256 · final electronic TOTEN | Geometry and source verification | Thermal classification and reusable output |
| --- | --- | --- | --- |
| IS · coadsorbed CH* + CO* · 9839757 | `f8bc627180b430b3b64f748c05830a0372bc93a3750780cf7fe6c5eb0601762d` · −385.14767079 eV | Accepted reclassified endpoint. C45/H48 and C46/O47 are two fragments of one periodic structure. Relaxation OUTCAR has 295 TOTEN and EDIFF exits, an accuracy marker and timing footer. | **Accepted** structure and electronic energy. Endpoint thermal data **missing**. Minimum stability under the local Hessian remains unverified. |
| TS · Dimer 9998592 · VFA 2260 | `0157a418cd1fba1be886426361d494ffbdce9a15d1a9132b996a3481ffcc1a6a` · −384.17406905 eV | Dimer OUTCAR has 193 TOTEN and EDIFF exits, accuracy marker and timing footer. The VFA POSCAR has a distinct byte identity, `c1b035d47a15cf8211d23dd25d4216a46c82a33b3b5c0957b03b86e7a49ade8d`. The ordered atoms and cell match, with maximum wrapped displacement 1.19 × 10⁻¹¹ Å. | **Accepted** for the previously reviewed local spectrum, C–C saddle assignment and TS-only ZPE. **Conditionally reusable** at finite temperature after the common reference and low-frequency treatment are specified. |
| FS · connected CHCO* · 9842136 | `11dab1631a99f1e444d4c7ab9ca242609e07c912f656874005696e6498f15ab2` · −384.48836276 eV | Accepted connected product. Relaxation OUTCAR has 131 TOTEN and EDIFF exits, an accuracy marker and timing footer. | **Accepted** structure and electronic energy. Endpoint thermal data **missing**. Minimum stability under the local Hessian remains unverified. |

The six structure/energy-source hashes were rechecked against the registry mapping. Each model contains five layers of metallic Fe(110) in the same 3×3 cell, ordered Fe0–44/C45/C46/O47/H48. The electronic source structures have 18 fixed Fe. Relaxation convergence establishes the electronic reference for the accepted state; endpoint curvature still needs an independent frequency measurement. Full file locations, OUTCAR hashes and calculation/result IDs are in the [candidate inventory](candidate_inventory.json).

## Frequency and correction candidates

Fresh inspection covered `calculations/` and `outputs/` in the development evidence workspace. Of 1,470 INCAR/INCAR.* files, ten specified IBRION 5–8. Of 800 files with OUTCAR in the name, 24 contained numbered real or imaginary frequency rows. Their union gives 26 directories. Each scientific candidate was compared independently with IS, TS and FS by ordered elements and cell, then by maximum same-index minimum-image displacement. Screening used an absolute cell tolerance of 10⁻⁶ Å and an ordered displacement threshold of 10⁻⁵ Å. The original raw spectrum and stable source hashes control reuse across copies.

| Candidate group | Direct check | IS / FS disposition |
| --- | --- | --- |
| Four R05 TS directories | Three completed copies share `d707a332f1af5d0835e1935d351d9a28b011bd4672e4de3b00833fb93f62f9a9`; the fourth is preparation only. Frequency POSCAR is 2.014 Å from IS and 3.394 Å from FS by maximum ordered displacement. | **Incompatible** for either endpoint. One independent reviewed TS dataset. |
| Eight directories with spectra from other systems | Different composition (including CO, CH, CH₂ and C₂H₂O on Fe). Per-file active axes, signed imaginary modes, dimension, convergence markers and settings are recorded in the inventory. | **Incompatible** for both. The isolated fragments cannot supply the coadsorbed IS correction. |
| One additional November 21 input for the 9833429 IS-A/INT06 Dimer | Fe₄₅C₂OH₂; mobile indices 36, 37, 39, 40, 42, 43, 49. No local spectrum in that directory. This lead postdates the earlier candidate inventory. | **Incompatible** for both on composition and physical subspace. |
| Thirteen test copies | Fixture provenance; no source-bound equilibrium POSCAR for either endpoint. | **Incompatible** for scientific use. |
| Precomputed ZPE, enthalpy, entropy or Gibbs corrections | Exact endpoint-hash registry lookup returned energy, geometry or force results only. Across 1,648 result rows the thermal/frequency-name lookup returned one imaginary-frequency magnitude. In 38,243 local JSON/CSV/YAML/Markdown files, 282 cited a full state hash or the reaction ID; nine also contained correction/spectrum terms. Their populated fields concern imaginary frequencies or an inclusion flag. | **Missing** for each endpoint. No concrete correction candidate qualified even conditionally. |

For a structure mismatch, a matching temperature or scaling rule cannot restore transferability. For a missing field the inventory records null. The current file search complements the wider November 20 audit of labelled and unlabelled VASP outputs, XML dynamical matrices, seven targeted archives, correction terms/aliases, workbooks and six Hessian inputs on the VASP host. A fresh read-only connection to that host timed out. New remote-only files and private or unindexed holdings therefore remain unverified. [Earlier search boundaries and per-candidate archive records](../../multiphase/phase3_2_3_1/candidates.json)

## Thermochemical reference and Gibbs assessment

Use `fe110_converged_toten_sigma0p20_v1` for electronic differences. For vibrations, the existing basis is `Fe110-C45-C46-O47-H48-local-harmonic`: the four adsorbate atoms move in all Cartesian directions and the Fe substrate is frozen. Job 2260 has one reference plus 24 central-displacement force evaluations with 25 EDIFF exits, 25 TOTEN records and normal termination. Its full signed spectrum re-parsed with the owning VASP reader. Formal Grade A review assigns mode 12 (−318.644011 cm⁻¹) to C45–C46 opening/closing. Excluding that coordinate leaves 11 positive modes. The lowest is 116.365467 cm⁻¹. The archived calculation uses unit scaling, without a frequency floor, and supplies no uncertainty estimate. The generic soft-mode assessment is still open; the scoped mode review remains authoritative for this TS. No new acceptance decision was made.

| Quantity | IS | TS | FS |
| --- | --- | --- | --- |
| Electronic state energy (eV) | −385.14767079 | −384.17406905 | −384.48836276 |
| Local ZPE (eV) | Missing | 0.5140516496724512 | Missing |
| Thermal enthalpy increment, vibrational entropy, Gibbs correction | Missing | Undetermined at unspecified temperature and standard state | Missing |

For a later finite-temperature calculation, declare a common adsorbed-state reference per surface cell and temperature in K, with the same local harmonic/scaling and low-mode convention across the three states. Record the reference for the coadsorbed pair as one configuration. There is no gas stoichiometric term in this elementary reaction. An electronic smearing width does not specify a thermodynamic temperature. Operating pressures or independent CH/CO activities belong to a separate kinetics qualification.

For each qualified state the owning module forms the electronic energy plus ZPE, thermal enthalpy increment and minus temperature times entropy, all on that reference. It checks the absolute residual of (TS−IS) − (TS−FS) − (FS−IS) against **10⁻⁹ eV**. A precomputed correction must also pass the module's component-consistency check. Here the *electronic* differences are +0.97360174, +0.31429371 and +0.65930803 eV and close at the reported precision. The **Gibbs closure test is not evaluable**: reaction result and closure residual are null. Neither a zero correction nor the TS-only ZPE was substituted for a missing state.

## Primary literature and transfer decision

The search used facet, CHCO/ketenyl and coadsorbed CH + CO terms with Hessian, frequencies, Gibbs and ZPE, including project-whitelisted archive domains. The previously linked Fe(110) paper and its original supplement were checked directly. No indexed record located in this search establishes a state-resolved correction for either local 3×3 target. This is a bounded search result.

| Evidence class | Finding and use |
| --- | --- |
| Directly transferable corrections | None located for the local cell, coverage, ordered geometry, active subspace and thermal reference. |
| Barrier correction differences | Li et al., Table S1, reaction 15a, describes **dissociation**, CHCO → CH + CO, on Fe(110) p(5×5). ZPE shifts the dissociation barrier by −0.05 eV (0.68 → 0.63) and reaction energy by −0.03 eV (−0.82 → −0.85). Reversing the authors' rounded numbers implies an association-barrier shift near −0.02 eV for *their* model. These are relative ZPE effects. They do not identify individual endpoint ZPEs, entropy or finite-temperature Gibbs corrections. [Primary paper](https://doi.org/10.1021/acs.jpcc.8b10310) · [Supporting Information, Table S1 and Figure S16](https://doi.org/10.1021/acs.jpcc.8b10310.s001) |
| Qualitative reference | Figure S16 supports comparison of the C–C reaction motif. Cell size, coverage and state mapping prevent numerical transfer. The independently retrieved supplement matched the archived SHA-256 `c5f9a6d23f7d1a16ca40945b071e53dba6bb9304807fa4ca792be23734c40d17`. |
| Incompatible model | The linked stepped Fe(710) CO/CHₓ coupling study concerns a different facet and site environment. Its thermochemical parameters cannot be assigned to these metallic Fe(110) endpoints. [Primary paper](https://doi.org/10.1021/acs.jpcc.8b04265) |

## Minimum missing calculation, if compatible evidence cannot be supplied

Either endpoint can be completed independently by providing reviewed corrections with source hashes, structure correspondence, active-subspace definition, units, components, temperature, standard state and method. Where that route is exhausted, **two separate local partial-Hessian frequency calculations** would supply the missing measurements. No new TS frequency calculation is indicated.

| Proposed endpoint | Exact geometry source in the scientific workspace | Independent acceptance check |
| --- | --- | --- |
| IS · coadsorbed pair | `calculations/fe110_five_c2_adsorption_20261006/final_review_20261012/sources/03_cfg0_direct_vasp/CONTCAR`, IS digest above | Preserve both fragments, original atom order, cell and coordinates. Confirm the joint local minimum and all 12 stable vibrational modes. |
| FS · connected product | `calculations/fe110_five_c2_adsorption_20261006/final_review_20261012/sources/03_extra2_repair_v1/CONTCAR`, FS digest above | Preserve the connected CHCO geometry, cell and atom order. Confirm its local minimum and all 12 stable vibrational modes. |

For each prospective POSCAR, copy the exact accepted cell and ordered coordinates. Set Fe0–44 to FFF and C45/C46/O47/H48 to TTT. Verify the source CONTCAR digest first, then record the new POSCAR digest and compare ordered periodic coordinates; changing selective dynamics can change file identity. Use the 2260 INCAR and KPOINTS hashes in the inventory as templates. Match the approved PAW-PBE identities in Fe/C/O/H order (06Sep2000 / 08Apr2002 / 08Apr2002 / 15Jun2001, respectively), original masses and spin branch. Check licensed potential bytes against the approved source on the execution host before any later launch.

| Setting | Specification from job 2260 |
| --- | --- |
| Electronic and magnetic | GGA=PE, ENCUT=400 eV, PREC=Accurate, ISPIN=2, MAGMOM=`45*2.2 2*0.0 1*0.0 1*0.0`, ISMEAR=1, SIGMA=0.10 eV, EDIFF=1e-7 eV, NELM=200, NELMIN=5, ALGO=Fast, LREAL=.FALSE., LASPH=.TRUE., LDIPOL=.FALSE. |
| Brillouin-zone mesh | Gamma-centered 5×5×1, shift 0 0 0, same 3×3 five-layer slab and vacuum. |
| Hessian | IBRION=5, NFREE=2, POTIM=0.015 Å, ISYM=0, NSW=1, LCHARG=.FALSE., LWAVE=.FALSE. Twelve Cartesian coordinates give 24 signed displacements plus a reference evaluation per endpoint. |
| Acceptance | Preserve original POSCAR/OUTCAR/OSZICAR, settings, hashes and atom map. Verify normal completion, SCF convergence for every force evaluation, consistent magnetic solution, all signed modes and dimension. Investigate any imaginary or ambiguous low mode before calling the endpoint a minimum. Keep a written rationale for scaling or any hindered-motion treatment. |

These Hessians test the four-atom subspace. Fe coupling, coverage, magnetic metastability, finite-displacement noise and low-mode entropy remain model uncertainties. Their SIGMA=0.10 eV TOTEN must not replace the reviewed electronic energies at SIGMA=0.20 eV. A full slab Hessian or isolated-fragment calculation would change the thermal reference and requires separate justification.

## Regression, provenance and handoff

Scientific Intake returned incomplete for ZPE, thermochemistry and kinetic handoff. The thermochemistry engine returned `partial` with either spectrum or compatible corrections still required separately for IS and FS, plus temperature and standard state. Kinetic parameter generation replayed the archived dataset and retained blocked export. **116 focused Windows tests passed** across Scientific Intake, thermochemistry and kinetic parameters. No scientific executable was launched. The read-only registry SHA-256 before and after the verification was `258f4ce1a103971721c9c085eca07ac5fb1b2461fb61370fba1fc726eeaabd61`.

For reproduction, run `python -m scripts.thermochemistry calculate reports/multiphase/ch_co_intake_20261119.json --ts-review reports/multiphase/ch_co_frequency_audit_20261119.json --phase adsorbate` from the qualification checkout. To inspect the signed raw modes, use `python -m scripts.thermochemistry parse OUTCAR POSCAR` on the bound 2260 files. Full-suite regression and fresh remote data were outside the verified results. The configured RSI diagnostic rejected its task scope before generating advice or a new dashboard. The classification above uses the original files, scientific reviews, supplementary data and direct module results.

**Next evidence decision:** request the two structure-bound endpoint packages, together with the target temperature and adsorbed-state standard state. Keep each unavailable field missing until its own evidence arrives.
