# Network closure and minimum evidence for the Fe(110) pilot

All four selected equations conserve C, H and O. Taking one forward event of each, the molecular balance consumes **2 CO* and 2 H*** and produces **1 O* and 1 C₂H₂O***. Internal C*, CH* and CHCO* cancel. The seven-adsorbate stoichiometric matrix has four independent reaction columns. Consequently the steady-state equation for these seven surface populations can only have **zero net flux in all four columns** in the isolated four-step model. This is a structural result; no kinetic flux was calculated. [Stoichiometric matrix and gate result](qualification.json)

The supplied equations show a vacancy on the left of R1 and on the right of R2 and R4. R3 supplies no explicit vacancy symbol. These are the requested formal equations. Site type, molecular footprint, independent site inventory, vacancy consumption/release by domain and charge assignments remain unconfirmed. Site regeneration cannot be counted from asterisks alone. All species are adsorbed on the selected metallic Fe surface; the Fe-FT industrial active phase remains outside this assignment.

## Candidate supporting processes

| Process required for sustained turnover | Existing evidence located | Minimum missing evidence |
|---|---|---|
| CO adsorption/desorption | Gas CO 9733110 and adsorbed CO/top 9558184 | Matched gas/surface references and sites; reviewed adsorption equilibrium and sticking/desorption or equivalent kinetics. |
| H₂ dissociation and H* supply | Gas H₂ 9573527 and H-containing structures | Paired sites, reviewed H/H+H reference and H* activity; free-energy/kinetic model for supply and recombination. |
| O* removal to OH* | R1 coadsorbed C+O endpoint; adsorption references for O, H and OH | Matched O+H encounter and OH end states, site and free-energy/rate evidence. Account for spectator O at the R1→R2 handoff. |
| OH* hydrogenation and H₂O desorption | OH, H and water references in the historical inventory | OH+H and water endpoint mapping, water chemical potential, kinetic model for formation and release. Relate vacancy regeneration to the same site inventory. |
| C₂ product release | Connectivity-specific [CH]–[C]–OH* FS-A | Matching gas isomer or reviewed downstream product, desorption/conversion law, free energy and product reservoir pressure. |
| Site and molecular reference alignment | Relaxed geometries and site projections | Reviewed site classes, footprint multiplicities, vacancy inventory and charge balance. Match spectators and coadsorption references across R1→R2, R2→R3 and R3→R4; provide encounter/diffusion treatment where applicable. |

The earlier inventory identifies partial sources for these processes. The live registry contains six accepted electronic barrier sets; none covers an entire feed, oxygen-removal or product-release process with reviewed 523 K parameters. No supporting reaction was appended. A hypothetical clamped H* reservoir or irreversible product sink would change the question.

## Reaction-specific actions

1. **R1.** Retain the CO/top–DIMER–C+O barrier. Obtain compatible endpoint corrections for the C/O local model and qualify site/vacancy assignments and the spectator-O reference.
2. **R2.** Keep reactive IS-A 9715450 as selected by geometry, retaining comparison candidate C 9715455. Use the archived product CONTCAR copy, which matches the reviewed digest and the terminal OUTCAR coordinates. Supply comparable vibrational/thermal inputs, including treatment of nearby Fe motion and reactive encounter probability.
3. **R3.** Supply IS and FS corrections independently. Its TS local correction is already available. Confirm coadsorbed CH/CO and product footprints, independent activities and any released sites; isolated CH and CO energies do not establish the coadsorbed reference.
4. **R4.** Review existing DIMER 9833429 final direction/soft residuals first. If supported, qualify its frequency evidence and compatible energy chain before accepting IS-A→INT06. Preserve the two accepted onward segments. Each segment needs compatible endpoint/TS corrections and an explicit kinetic treatment before serial kinetics or a reviewed coarse-grained parameter can be derived.
5. **Kinetic handoff.** Each modeled direction needs activation and reaction Gibbs energies on the same 523 K basis, reviewed reversibility, prefactor/transmission or alternative rate law, activity powers and applicable conditions. Gas pressure orders cannot be inferred from the feed ratio. Test detailed balance only after both directional coefficients and thermodynamic evidence exist. Overall TOF also requires a declared product boundary and normalization.

Researchers can supply corrections or a reviewed parameterization without rerunning an existing calculation. Any later frequency or structure job requires its own scoped proposal after the evidence review. [Versioned kinetic dataset](kinetic_dataset.json) · [Thermochemistry qualification](thermochemistry.md)
