# V.1.1 · Metallic Fe(110) Fischer–Tropsch workflow readiness

**The first defensible reaction-level output is the compatible electronic energy profile.** Six C1–C2 electronic barrier sets could be traced from the schema-9 registry back to all 18 state energies in the original OUTCARs. The CH* + CO* → CHCO* case also supports a reviewed C–C saddle assignment and a TS-only vibrational zero-point energy. The first missing inputs for a three-state thermal result are compatible IS and FS evidence. Both native engine handoffs are blocked. The single-reaction draft and the wider route inventory have different scopes.

Qualification used the published R.2.5 commit `9ee940e944e929ac056ee0836d6f4050d2213625` in an isolated checkout. Raw scientific files came from the separate development evidence workspace. The [evidence inventory](evidence_inventory.json) records relative locations, SHA-256 values, result IDs, compatibility fingerprints, and the published input files needed for replay. It contains metadata only. The registry was opened immutable, read-only and query-only after checking for a WAL. The existing registry inventory reader was also exercised on a byte-matched temporary copy.

## Scientific qualification across the full route

The November 17 inventory contains 13 proposed chemical steps and one reference-state link. Its four accepted electronic triples were supplemented by the November 18 registration receipts for R05 and R07. Their current barrier records and receipt hashes were verified. For each of the following six rows, final OUTCAR TOTEN, file SHA-256, convention, compatibility fingerprint and all three differences agree with the registry. Values are eV in the order TS−IS, TS−FS and FS−IS. This table qualifies only the electronic result for the indicated states.

| Step | Reaction and archived IS / TS / FS jobs | Forward | Reverse | Reaction | Limit on use |
| --- | --- | ---: | ---: | ---: | --- |
| R03 | CO dissociation · 9558184 / 9656664 / 9622455 | 1.35020905 | 2.05657334 | −0.70636429 | Carry the coadsorbed O into the next reference-state balance. |
| R04 | C* + H* → CH* · 9715450 / 9720181 / 9573951 | 0.88769187 | 0.74146691 | +0.14622496 | Reactant is configuration A. The registered FS energy directory lacks a sibling CONTCAR. Locate and bind the final structure before a thermal handoff. |
| R05 | CH* + CO* → CHCO* · 9839757 / 9998592 / 9842136 | 0.97360174 | 0.31429371 | +0.65930803 | Reviewed coadsorbed IS and Grade A saddle. Only the TS local ZPE is available. |
| R07 | INT06 → MID, H migration · 9748648 / 9796856 / 9737143 | 0.16732341 | 0.09964185 | +0.06768156 | CI-NEB saddle and VFA 9798421. Match the thermal subspace across this step. |
| R08 | MID → FS-A, O–H formation · 9737143 / 9746548 / 9725471 | 1.28582718 | 0.89481705 | +0.39101013 | Local segment only. Keep the preceding H migrations and the H reservoir explicit. |
| R09 | CH* + H* → CH₂* · 9701350 / 9709074 / 9622444 | 0.55454713 | 0.06974204 | +0.48480509 | Competing branch from configuration A. Methane selectivity needs additional steps and qualified fluxes. |

| Remaining route entry | Available evidence | Missing evidence before use |
| --- | --- | --- |
| R01 · CO adsorption | CO(g) 9733110 and CO/top 9558184 | Reviewed site, adsorption free energy and reversible adsorption/desorption model. |
| R02 · H₂ dissociation | Gas reference 9573527 and H adsorbate candidates | Matched H+H endpoint, pair occupancy, dissociation/recombination kinetics. |
| L01 · coupling-to-hydrogenation link | R05 FS 9842136 and H-containing IS-A 9725473 | H reservoir, coadsorption and site/configuration alignment. This is a reference-state link with no elementary rate. |
| R06 · IS-A → INT06 | 9725473 / Dimer 9833429 / 9748648. Archived maximum atomic force 0.015998 eV/Å, curvature −0.63616 eV/Å². | Final direction review remains pending. No matching TS validation row was found for that saddle. A reviewed mode, compatible barrier and thermal evidence are required. |
| R10 · O* + H* → OH* | Adsorption references | Matched coadsorbed endpoints, qualified saddle or justified kinetic model and free energies. |
| R11 · OH* + H* → H₂O* | OH, H and water references | Reaction-ready endpoints, qualified reaction kinetics and free energies. |
| R12 · water desorption | Adsorbed and gas references | Selected site, gas chemical potential, standard state and reversible desorption model. |
| R13 · C₂ product release | Adsorbed FS-A 9725471 | Connectivity-matched gas isomer, stability, desorption or onward mechanism and reverse process. |

The inventory supports planning a branched mechanism. Joining the rows requires reviewed species identities, site inventories and common reservoir references. In particular, the isolated CH* and CO* energies cannot supply the R05 coadsorbed-state energy. A steady state, TOF or product distribution for the full route would depend on unresolved feed, spectator and product fluxes.

## Raw evidence for the R05 handoff

The energetic branch is PBE, 400 eV, 5×5×1, metallic Fe(110) 3×3 five-layer Fe₄₅ with 18 fixed atoms, ISMEAR 1 and SIGMA 0.20 eV. All three ordered structures are Fe0–44, C45/C46/O47/H48. The original endpoint reviews accept the reclassified CH* + CO* IS and the CHCO* FS. Species IDs for the two IS fragments refer to the same CONTCAR. The [registry mapping](../../multiphase/ch_co_registry_mapping_20261119.md) identifies the source reviews and energy convention.

| State | CONTCAR SHA-256 prefix | Final OUTCAR TOTEN (eV) | OSZICAR completed ionic summaries / final F (eV) |
| --- | --- | ---: | --- |
| IS | `f8bc627180b4` | −385.14767079 | 295 / −385.14767 |
| TS | `0157a418cd1f` | −384.17406905 | 193 / −384.17407 |
| FS | `11dab1631a99` | −384.48836276 | 131 / −384.48836 |

The OSZICAR counts describe VASP summaries and include Dimer evaluations. The ordinary NEB 9994246 supplied the 04–05–06 triad. Its parent convergence check was false. The Dimer 9998592 completed with negative curvature (−5.751 eV/Å²), maximum atomic force 0.015198 eV/Å and a failed soft-force/torque check. The final scientific assignment comes from the scoped review, VFA job 2260 and the registration decision. Those distinctions matter when applying the same workflow to R06.

The VASP frequency reader reproduced all 12 signed modes, hashes and active indices 45–48. The VFA POSCAR and source TS CONTCAR have different byte hashes. Ordered atoms, periodic coordinates and cell agree. The VFA freezes the Fe atoms and uses SIGMA 0.10 eV. The review assigns mode 12 (−318.644011 cm⁻¹) to C45–C46 opening/closing, with Dimer-direction cosine about 0.934. The other 11 modes give **0.51405165 eV TS local ZPE**. ZPE differences, activation free energies and rates remain unknown.

The current exact-structure registry lookup reproduced the archived match lists for IS, TS and FS. Endpoint result rows contain no thermal correction. A separate local scan of `calculations/` and `outputs/` examined 1,470 INCAR or INCAR.* files, found ten IBRION 5–8 controls with readable co-located POSCARs and compared ordered species, cell and periodic coordinates. Three copies matched the TS and none matched either endpoint (cell tolerance 10⁻⁶ Å, fractional-coordinate tolerance 10⁻⁵). These are bounded local searches. The earlier [frequency audit](../../multiphase/ch_co_frequency_audit_20261119.md) additionally covers historical remote records. Alternate naming, atom reordering, external holdings and newer remote work were outside the fresh scan.

## End-to-end capability and reuse map

“Ready” applies to the output named in its row. “Missing scientific data” means that the operation can accept additional evidence today. “Blocked by scientific evidence” describes a downstream qualification decision. No row required a code repair or demonstrated a missing software contract.

| Step and existing owner / entry | Input → actual output | Consumer | Classification and outstanding evidence | New code |
| --- | --- | --- | --- | --- |
| Scientific Intake · `scripts.scientific_intake --operation kinetic_handoff` | CHCO intake → field-level missing report, exact archived object reproduced | Thermochemistry and reaction network | Ready for intake. Endpoint thermal routes and operating/model fields remain open. | No |
| Structure and species identity · `neb_agent.utils_structure.read_poscar`, `reaction_network.builder.from_registry_mapping` | Reviewed endpoints, atom roles, surface and three structures → state hashes and CH/CO/CHCO mapping | Frequency assignment, thermochemistry and network builder | Ready for R05 identity. Independent activities and occupancies need research review. | No |
| VASP evidence and registry · `ts_barriers → results → files`, `neb_agent.utils_vasp.parse_oszicar` | Schema-9 rows, final OUTCARs, structures, OSZICARs → compatible electronic profiles and provenance | Intake, network energy fields and researcher | Ready for six electronic triples. Keep the R04 structure limitation with the result. | No |
| NEB / Dimer / vibrational validation · `ts_strategy_engine` review records and `vasp_vibrations.parse_frequency_outcar` | Parent triad, Dimer, VFA POSCAR/OUTCAR and Grade A scope → reviewed R05 coordinate and signed local spectrum | Thermochemistry TS exclusion | Ready within R05 review scope. R06 still needs final direction and vibrational evidence. | No |
| Thermochemistry · `scripts.thermochemistry calculate` | Intake plus reviewed TS audit → partial state correction, six issue fields | Reaction network, then kinetic parameters | Reusable with missing scientific data. IS/FS each need a spectrum **or** a compatible correction. Temperature and standard state are also absent. | No |
| Reaction network · `scripts.reaction_network` | Registry mapping, intake and thermal result → content-addressed DRAFT and validation report | Site review, parameter builder | Ready for draft reconstruction. Element balance passes (C₂H₁O₁ on each side). Charge balance, formal catalyst phase and kinetic direction remain open. | No |
| Sites and vacancies · `scripts.reaction_network --site-proposal` | Parent version and bound geometric proposal → pending network, unknown per-inventory balances | Network conservation and both exports | Reusable with missing scientific data. Supply reviewed occupancies, free-site counts, exclusions and surface domain. | No |
| Kinetic parameters · `scripts.kinetic_parameters --format missing` | Versioned network → blocked dataset, forward and reverse rates null | CATKINAS / Zacros parameter exporters | Reusable with missing scientific data. Needs compatible Gibbs energies, rate law and scoped, unit-bearing parameters. | No |
| CATKINAS MKM · `kinetic_parameters.export.catkinas`, `baseline_mkm.single_point.prepare` | Fe dataset → denied export and archived QUALIFICATION → REJECTED receipt | Single-point execution gate | Blocked by scientific evidence. Both preparation and rate export were exercised offline. Conditions and validated input remain missing. | No |
| Zacros KMC · `kinetic_parameters.export.zacros`, `native_model.assemble` | Same Fe dataset → denied export before a native file exists | Zacros renderer and execution gate | Blocked by scientific evidence. Also needs local event pattern, neighbor graph, occupancy/exclusions and occurrence normalization. | No |
| Scientific analysis · `baseline_mkm.analysis.inspect_draft` | Network + parameter dataset → structural pathway and explicit missing-data report | Researcher / pathway review | Ready for structural inspection. Accepted result, matching receipt and fluxes required for kinetics. | No |
| State and provenance · `artifact_io`, registry source IDs, `state_manager.cli` | Hash-bound inputs and existing decisions → traceable versions, reviewed history and read-only preview | Each scientific owner and human reviewer | Ready for this provenance chain. Existing repository history-compaction and module-map drift are separate state-maintenance issues. | No |

## Exact handoff and next executable step

1. **Complete the R05 three-state thermal handoff first.** For the IS and FS hashes above, supply reviewed stable spectra for the same physical local basis (C45/C46/O47/H48, 12 active Cartesian components), or reviewed precomputed corrections bound to their state identities. Record source bytes or traceable reference, active map, constraints, units, model/low-mode convention, temperature and standard state. A different POSCAR byte hash requires evidence of ordered periodic geometry equivalence. For finite-temperature use, the TS requires the same reference and exclusion of the reviewed unstable coordinate. This surface-only step has no gas stoichiometry. Pressure is needed later for operating conditions.
2. **Acceptance for that one next task.** Use the existing intake and thermochemistry commands on the real R05 parent plus the supplied endpoint evidence. An absent endpoint, incompatible identity/basis, or unresolved conditions must keep the three-state Gibbs differences unavailable. With compatible reviewed evidence for all three states, verify ΔG‡forward − ΔG‡reverse = ΔGreaction at the declared conditions and retain every source binding. A thermal success alone must leave engine export blocked while independent site or rate gaps persist. This is an evidence handoff to the existing modules. No implementation or calculation has been initiated.
3. **Subsequent dependencies.** Review whether the two IS long bridges sharing Fe41 are independent, whether the two FS hollows sharing Fe41/Fe44 form one ensemble or two inventories, and whether off-top O47 adds an occupied site. Specify footprint per molecule, explicit vacancies consumed/released, charge, surface/phase, direction and applicability. Then bind rate-law form, forward/reverse parameters or reviewed derivation, units, degeneracies, standard states, operating conditions, validity range and provenance. Network-wide work also requires the reservoir joins listed above. If a future real input fails an existing contract, preserve that input and reproduce the failure in the owning module before proposing a code change.

## Replay results and limits

- With the archived thermal input, the public network CLI reproduced the original parent `e9dc0c89…` and pending-site network `2a80b67c…` byte-for-byte. The parameter dataset `a4191054…`, missing-data report and scientific analysis matched their archived JSON objects. The independently invoked CATKINAS and Zacros exporters each raised `Kinetic dataset is blocked for export` and wrote no output. The [Fe qualification receipt](../../multiphase/phase3_0/fe110_qualification.json) records execution `not_started` and approval `not_requested`; the [analysis](../../multiphase/phase3_1/fe110/report.md) retains null coverage, rates, TOF and selectivity.
- With freshly emitted thermochemistry, the only difference from the archived calculation object was the additional TS diagnostic `subspace_verified: true`. Passing that result directly through the network CLI and parameter builder produced a fresh DRAFT parent with the same electronic profile and blocked rates. The old site proposal was rejected against that different parent. A later thermal upload needs a proposal bound to its own parent.
- Windows focused regression passed **246 tests**: 188 across Scientific Intake, thermochemistry, reaction network, kinetic parameters, MKM analysis and the Fe single-point qualification case, plus 58 across site review, scientific priority and isolated engine imports. The full suite was outside this readiness check. Regression fixtures provide software checks only. No native scientific engine, production write, or new scientific acceptance was used.
- The configured local research-planning helper stopped at output-directory validation before producing a run or recommendations. The evidence and results above come directly from the source files, owning modules and regression checks. No external search, live scheduler determination or remote calculation was needed to qualify these archived states.

### Reproduce the offline qualification

From the qualification checkout in PowerShell, the following commands read the published documents and emit diagnostics to stdout. Use a new temporary directory with the network CLI's `--output-dir` to retain a reconstruction for byte comparison. The machine inventory supplies the paths and full digests for raw evidence held separately.

```powershell
$evidence = 'reports/multiphase'
$intake = "$evidence/ch_co_intake_20261119.json"
$thermal = "$evidence/phase2_2_chco_validation.json"
$network = "$evidence/networks/network-2a80b67c31201600a1858780bbe6c176b03f489fe24383441fca4f195b395483.json"
python -m scripts.scientific_intake $intake --operation kinetic_handoff
python -m scripts.thermochemistry calculate $intake --ts-review "$evidence/ch_co_frequency_audit_20261119.json" --phase adsorbate
python -m scripts.reaction_network "$evidence/ch_co_registry_mapping_20261119.json" --project-id sbq123 --intake $intake --thermochemistry $thermal --site-proposal "$evidence/phase2_3_1_site_proposal.json"
python -m scripts.kinetic_parameters $network --format missing
```
