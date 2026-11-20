# Fe(110) endpoint evidence and reference review

**Decision on 2026-11-20.** Neither endpoint has a usable thermal route in the records examined. The two structures and electronic energies do have exact bindings. Each endpoint can independently enter through a signed spectrum or a reviewed precomputed correction. One endpoint can be completed while the other remains open. [State-level evidence and source hashes](endpoint_evidence.json) · [Candidate-by-candidate assessment](candidates.json)

| Audit | IS, coadsorbed CH* + CO* | FS, connected CHCO* |
|---|---|---|
| Target CONTCAR SHA-256 | `f8bc627180b430b3b64f748c05830a0372bc93a3750780cf7fe6c5eb0601762d` | `11dab1631a99f1e444d4c7ab9ca242609e07c912f656874005696e6498f15ab2` |
| Independent source | `03_cfg0_direct_vasp`, job 9839757; accepted CH+CO coadsorption reclassification | `03_extra2_repair_v1`, job 9842136; accepted connectivity-specific relaxation |
| Reviewed electronic energy | -385.14767079 eV | -384.48836276 eV |
| Source structure scope | Fe0–44, C45, C46, O47, H48; 18 fixed Fe | Same order and relaxation constraints, distinct coordinates |
| Source OUTCAR | IBRION=2; no frequency rows | IBRION=2; no frequency rows |
| Closest lead by chemistry | TS frequency POSCAR differs from IS by up to 2.014 Å at the same atom index | TS frequency POSCAR differs from FS by up to 3.394 Å at the same atom index |
| Endpoint stability, ZPE, ΔHthermal, S, Gcorr | Unknown for this coadsorbed pair | Unknown for this product geometry |

The structure comparison uses ordered atoms in matching cells and minimum-image fractional displacements converted to Å. The reviewed TS and its frequency input agree to within 1.2 × 10⁻¹¹ Å by this measure. Equal composition alone cannot establish that relationship. Neither the two isolated fragments' independent corrections nor those of a different CHCO geometry establish the required values.

## Fields still required

Each row applies **separately to IS and FS**. The supplied structure and electronic reference can already be cited. Neither state's relaxation flags establish its frequency subspace.

| Missing evidence | Why it matters | What the researcher can supply / what can substitute | Does this alone require new DFT? |
|---|---|---|---|
| Thermal source bound to the endpoint | Attaches numerical values to the electronic geometry | Cite the target hash, or provide original coordinates/cell/order and a reviewed identity or atom mapping. Give the source file, accession or DOI, method, reviewer, scope and status. | No; identity and provenance may be documented retrospectively. |
| Mobile atoms, axes and Hessian-to-structure map | Defines which substrate and adsorbate motions contribute | A matching POSCAR/OUTCAR, mapped Hessian with units, or provider's reviewed description of an equivalent subspace. State each component and the source's ordering. | Only a missing raw-data route may ultimately need a frequency job. |
| Signed modes, dimensions, imaginary/soft-mode review | A harmonic endpoint should be a minimum within the selected subspace. Counts test completeness. | Supply signed cm⁻¹ and the mapped dimensionality. For a precomputed value, document the provider's stability review, low-mode model, exclusions and scope. A single observed band cannot reconstruct the partition function. | A compatible reviewed precomputed package can replace a raw spectrum. |
| Frequency scale and model | Scaling or low-mode changes affect ZPE and entropy | Declare the factor and treatment. Cite calibration for non-unit scaling, or rationale for each scale when scales differ. State whether supplied corrections already include scaling. | No if source documentation establishes the convention. |
| ZPE, eV/state | Needed for a ZPE-corrected energy or a full Gibbs correction | Reviewed endpoint ZPE or derive from a compatible signed spectrum. ZPE alone can close the ZPE-only field. | Conditional on exhausting both routes. |
| Thermal enthalpy increment, eV/state | Separates finite-temperature excitation from ZPE | Supply ΔHthermal(T) excluding ZPE; if source includes ZPE, provide components and review the documented conversion. | No if a compatible spectrum or documented components exist. |
| Entropy, eV/K/state | Determines the −T S contribution; electronic smearing entropy is a different quantity | Supply vibrational S(T), or a compatible spectrum and model. If supplied as TS in energy units, give T and the sign convention for review. | Same two alternatives. |
| Gibbs correction, eV/state | Needed for reaction and activation free energies | Supply compatible components and Gcorr = ZPE + ΔHthermal − T S, or a reviewed spectrum. Record included contributions. The current contract checks the component sum; a lone ΔG or rounded barrier cannot establish it. | Same two alternatives. |
| Temperature and surface standard state | Needed to compare finite-temperature terms | Supply operating T in K and a named adsorbed-state reference shared by the three states. This elementary surface step has no gas stoichiometry. Operating pressures remain a separate kinetic input. | No; these are researcher/model choices. |
| Thermal basis, electronic reference and scientific review | Prevents mixing incompatible slabs, standard states and total-energy conventions | Document agreement with the local adsorbate harmonic scope and the electronic TOTEN branch, including cell/coverage, XC and any reviewed adaptation. Supply validation method, properties and limitations. | Metadata alone needs no calculation; unresolved physical differences can require a replacement source. |

## Common reference and TS protection

The three electronic records share `fe110_converged_toten_sigma0p20_v1` (PBE, 400 eV, 5×5×1 k mesh, 3×3 Fe(110) coverage). Electronic forward and reverse barriers remain 0.97360174 and 0.31429371 eV. The confirmed TS input fixes all Fe and moves C45/C46/O47/H48 in Cartesian x, y, z. The reviewed basis is `Fe110-C45-C46-O47-H48-local-harmonic`; its 12 signed modes use scale 1.0. Grade A assigns mode 12 (−318.644011 cm⁻¹) to the reaction coordinate. The remaining 11 give the recorded local ZPE 0.51405165 eV. The Hessian used SIGMA=0.10 eV. Its electronic energy cannot replace a SIGMA=0.20 eV barrier input. The 450 K synthetic check in the validation file supplies no operating temperature for Fe.

A common thermal reference remains **unconfirmed**. For the raw route each state needs its own structure/mapping review and a comparable local subspace; numbering in an external file may differ. For reviewed precomputed values, document the same physical basis. Full Gibbs requires the common temperature, standard state, and consistent components. Do not exclude an endpoint mode merely because the TS reaction coordinate was excluded. No occupancy or reversibility is inferred from geometry or the studied reverse reaction in the literature.

## Intake and release of individual fields

Use the existing Scientific Intake with the unchanged reaction ID `fe110_ch_co_to_chco_20261109`, a unique record ID, the relevant state, and `kind=spectrum` or `kind=corrections`. External and researcher-held sources may enter with a DOI, accession or file reference; a local VASP job ID is optional. For corrections, the contract accepts `structure_identity`, `thermal_basis`, `zpe_ev`, `thermal_enthalpy_ev`, `entropy_ev_per_k`, `gibbs_correction_ev`, `temperature_k` and `standard_state` as applicable. Keep source, units/conversions, review scope, limitations and uncertainty with the record. Scientific validation and scoped human acceptance are separate. Partial or unreviewed material can be saved. [Scientific Intake rules](../../../modules/kinetic_data/scientific_intake.md) · [Thermochemistry contract](../../../modules/thermochemistry/README.md)

A reviewed correction for either state can eliminate the need to calculate that state. If retrieval and provider follow-up leave a specific endpoint without either route, propose a matched frequency calculation for that endpoint for separate authorization. MKM remains blocked by missing thermal evidence and independent site, kinetic, operating-condition and reversibility requirements. [Live intake findings](endpoint_evidence.json)
