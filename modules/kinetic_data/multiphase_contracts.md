# Multiphase exchange contracts 1.0.0

A bundle describes catalyst identities, elementary steps, parameter sets and run metadata. Validate a UTF-8 JSON file from the repository or from an installed wheel with Python 3.11 or later.

```console
python -m scripts.multiphase_contracts tests/fixtures/multiphase/valid.json
```

Pass your bundle path in place of the example. Success exits 0. Malformed JSON, duplicate object keys, schema violations and inconsistent linked records exit 1 with a diagnostic. Validation is local and read-only. It resolves all Draft 2020-12 schema identifiers from bundled resources. The reserved .invalid host names are identifiers. Individual schemas describe record shape; validate the complete bundle for referential integrity and scientific arithmetic.

## Records and ownership

| Bundle array | Schema under configs/ | Identity and scope |
|---|---|---|
| projects | catalysis/catalyst_project.schema.json | project_id |
| materials | catalysis/catalyst_material.schema.json | material_id → project |
| phases | catalysis/phase.schema.json | phase_id → material, crystal composition, structure and source |
| surfaces | catalysis/surface.schema.json | surface_id → phase, Miller or Miller–Bravais indices, termination, explicit defects/vacancies |
| sites | catalysis/active_site.schema.json | site_id → surface, site type and local geometry. Multiple instances/types can belong to one surface. |
| interfaces | catalysis/interface.schema.json | interface_id → at least two distinct surfaces in one project, geometry and source structure |
| species | kinetics/species.schema.json | species_id, phase, elements, net charge in elementary-charge units, occupied sites, geometry, structure, structural provenance and review |
| reactions | kinetics/reaction.schema.json | reaction_id, stoichiometry, surface context, vacant site counts, IS/FS/TS references, energies and review |
| parameter_sets | kinetics/kinetic_parameter.schema.json | parameter_set_id → reaction, rate law, basis, standard states, source quantities and applicable conditions |
| runs | kinetics/simulation_run.schema.json | run_id, engine/version, parameter set IDs, per-engine input roles, output artifacts and separate status fields |

`configs/kinetics/bundle.schema.json` defines the envelope. `configs/catalysis/common.schema.json` defines shared identifiers, evidence, review states and quantities. Every record and bundle carries schema_version. Record types are closed to unknown properties. IDs are unique within each collection. Use distinct species IDs for different occupancies, geometries, structures or charge states. The fixture distinguishes gas H₂, single-site H₂ and H₂ spanning a Ni atop site and a Cu bridge site. These entries are synthetic.

Foreign keys resolve inside the bundle. Structure IDs, energy reference IDs, rate-law IDs, source calculation IDs and review receipts refer to external records. An energy reference ID denotes one reviewed compatibility branch, including method, energy convention and reference states. A review artifact has a path and lowercase SHA-256 digest. Consumers must resolve and verify those bytes and their authority before accepting science or execution. The validator never imports files named by a bundle or evaluates text expressions.

## Reaction checks

Each reaction side maps species IDs to positive integer molecular counts. Site occupancy maps site IDs to counts per molecule. Empty maps explicitly encode no free/occupied sites. For each site ID, occupied reactant sites plus consumed free sites equal occupied product sites plus released free sites. Required sites must cover that footprint and may include spectator sites. Site capacities are checked by ID. Two sites of the same type on different facets remain distinguishable. Atom counts and signed charge are conserved independently.

Each electronic or Gibbs triple contains reaction energy, forward barrier and reverse barrier. Each measured value is eV per elementary event with a reference and hash-bound source. If all three exist, forward minus reverse must equal the reaction energy within an absolute rounding allowance of 1e-8 eV. Gibbs values additionally share an explicit temperature and standard-state identity. The tolerance checks serialized arithmetic only. A missing quantity is null. The validator does not infer zero barriers, reverse rates, transition states or free energies.

A reversible draft may be incomplete. Eligible reversible parameters require both rate directions. An irreversible rate law has a null reverse rate. An independently known reverse barrier may still be recorded. A located TS requires its ID. A barrierless or unresolved step records a null TS ID. Reportable barriers and the treatment of a putative barrierless step still require the owning module's evidence.

## Parameter and manifest checks

Temperature uses kelvin, pressure uses pascals and solution reference concentration uses mol/m³. Standard-state IDs have consistent definitions within a bundle. A Gibbs parameter set binds to the reaction temperature and standard-state ID. The parameter conditions and coverage fractions must lie within their stated ranges. Rates carry an explicit prefactor/unit, temperature exponent, activation energy, symbolic law and degeneracy. V1 enumerates per-second units with dimensionless activities or explicit first/second pressure or concentration factors. Mixed or higher-order dimensional prefactors require normalized activities or a reviewed schema extension. Coverage terms identify the affected species, energy coefficient, expression, validity interval and whether the correction is already included. Unavailable uncertainty is null.

An eligible label requires accepted metadata and a review artifact. Eligible reaction records require reviewed substrate/species context, thermochemical evidence and available free-energy fields. Prediction and fixture sources are excluded. Rate barriers in eligible parameter sets cite their reaction barrier. The data contract checks internal consistency. Actual artifact bytes, reviewer identity, TS mode assignment, detailed balance of arbitrary rate expressions and kinetic eligibility remain subject to the existing scientific gates.

| Run engine | Input roles |
|---|---|
| CATKINAS | Named MATLAB input, optional thermodynamics_data |
| Zacros | Simulation, lattice, mechanism and energetics inputs, optional state input |
| reactor | Independent model definition, rate provider and operating conditions |

Input and result files are represented by path and SHA-256. Each engine has a closed set of input roles. Execution, numerical convergence, scientific review and approval are reported separately. A successful run can remain unconverged or unreviewed. A completed scientific claim requires outputs, converged/inapplicable numerical status and eligible parameters. No manifest field dispatches a process. Use the [installed engine assessment](../../reports/multiphase/external_engine_compatibility.md) when reviewing the native files.

## Test fixtures

`tests/fixtures/multiphase/valid.json` is an internally balanced, exploratory bundle. Paths and digest strings in the fixture are mock data. `invalid.json` contains a dangling project reference. The parameterized tests exercise additional single-field and cross-record failures. Neither fixture represents a measured or simulated kinetic dataset.
