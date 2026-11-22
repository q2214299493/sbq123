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

# Reaction Network

## Purpose

Assemble validated states and transition states into atom- and site-balanced elementary reactions.

## Required Inputs

- registered species and site definitions
- validated IS/FS pairs and Grade A TSs
- consistent reaction/free-energy and forward/reverse barrier data

## Outputs

- stoichiometric reaction table
- site-balance rules and reversibility
- source geometry and TS links
- consistency checks for atoms, sites, and thermodynamic cycles

## Done Criteria

Every elementary step balances atoms and sites, links source states/TSs, and passes forward/reverse thermodynamic consistency checks.

## Build and inspect a version

Run from a checkout or installed wheel. Omitting `--output-dir` prints the network. Supplying a directory writes `network-<content SHA-256>.json` once. Replaying identical inputs returns the same artifact. A conflicting or interrupted file is preserved for inspection.

```text
python -m scripts.reaction_network tests/fixtures/multiphase/valid.json
python -m scripts.reaction_network reports/multiphase/ch_co_registry_mapping_20261119.json --project-id sbq123 --intake reports/multiphase/ch_co_intake_20261119.json --thermochemistry reports/multiphase/phase2_2_chco_validation.json --output-dir reports/multiphase/networks
```

The first input can be a complete Phase 1 bundle, the partial Phase 1 registry field mapping, or a JSON definition with `format: network-definition/1`. Native definitions use the Phase 1 collection and field names. Supply one project, its materials, phases, surfaces, sites and interfaces, plus species and elementary reactions. Empty collections can be omitted. Preserve unknown charge, occupancy, vacant sites, phase identity, energy or reversibility as null. Empty site dictionaries mean a known zero. A complete Phase 1 bundle still passes through its own schema and semantic validator. [Phase 1 fields](../kinetic_data/multiphase_contracts.md)

In a native definition, supply explicit `reactants` and `products` with positive integer counts, or use `endpoint_candidates`. Each candidate has a reaction ID, surface/interface context and `initial` and `final` objects containing `structure_id` and an array of assigned `species_ids`. Repetition counts molecules. The builder emits a draft with the original assignments. Supported classifications include adsorption, desorption, dissociation, association, hydrogenation, dehydrogenation, C–C coupling (`c_c_coupling`), C–O cleavage (`c_o_cleavage`), diffusion, multi-site, surface and interfacial reactions. Classification is supplied or left as `other`; assigning fragments from coordinates and identifying a mechanism still need scientific review.

## Species, sites and evidence

Species IDs index an in-memory catalog. Physical fingerprints include catalyst project, material, catalyst phase and facet, molecular phase, interface, composition, charge, site counts/types, geometry/configuration, structure identity and fragment indices when supplied. Duplicate IDs and physical aliases are reported. Use distinct configuration IDs or structure evidence to distinguish actual isomers. Site IDs resolve in a surface domain. Multi-site occupancy is counted per molecule. On each site ID, occupied reactant sites plus consumed vacancies must equal occupied product sites plus released vacancies, including multiplicities. A supplied required-site footprint must cover those counts.

Repeat `--intake` to attach Phase 2.1 documents for the corresponding reaction. Structures and electronic state energies are bound by identity and reference. Only available differences are derived, and TS barriers need a located TS. A scoped site-mapping decision can attach occupancies by species ID and site ID, or an unambiguous site type on the relevant domain. The original geometric projections, decision and effective mapping are retained separately. Conflicting mappings for the same species require reconciliation. Literature, user and external records retain their source metadata and may omit local calculation IDs. [Intake and decisions](../kinetic_data/scientific_intake.md)

Use `--thermochemistry` for the matching Phase 2.2 result or its validation envelope. Where electronic registry IDs differ from thermochemistry geometry digests, supply `state_identities` keyed by IS, TS and FS, and `electronic_reference_convention` if the network reference is a compatibility fingerprint. Binding checks cover each structure, state energy, correction basis, temperature and standard state. Electronic and Gibbs closure are checked separately. Across steps the validator checks dependencies in the stoichiometric matrix within each common energy convention and condition. Unknown site accounting is excluded from cycle counts. An unknown direction has no reverse reaction definition; an independently sourced reverse barrier can remain in the evidence.

## Validation levels and reviews

| Level | Meaning in the artifact |
|---|---|
| DRAFT | Traceable candidate with identified missing structural evidence. Contradictory known balances or dangling references raise an error. |
| STRUCTURALLY_VALID | Endpoints, species/context and applicable element, charge and site accounting are traceable and internally consistent. |
| THERMODYNAMICALLY_VALID | The step also has compatible, internally consistent Gibbs quantities for the required directions. An exploratory fixture can test this arithmetic. |
| SCIENTIFICALLY_ACCEPTED | An explicit network decision binds the current reaction subject. Relevant source and review artifact digests and accepted upstream records also pass the checks. |
| KINETICALLY_ELIGIBLE | The accepted step additionally carries eligible reaction and parameter records from an unchanged, validated Phase 1 bundle, including coverage dependencies. Execution remains under downstream gates. |

Each reaction reports its origin, user confirmation, scientific review, bound network review, validation level and MKM status separately. A user decision on a supplied definition uses `user_confirmation` with `definition_sha256` over the reaction without that decision, acceptance status, reviewer (`accepted_by`), reason, scope containing `reaction_definition`, and timezone-aware acceptance timestamp. A site-mapping decision has its original narrower scope. To import a scientific network review, first inspect the candidate's `subject_sha256`. Pass an independently reviewed JSON file using `--decision` with `reaction_id`, that digest, `decision` (accepted or rejected), `reviewer`, `reviewed_at` with time zone, and `reason`. Repeat `--evidence` for the actual review and source artifacts. Changing the reviewed subject invalidates that decision. The reviewer remains responsible for scientific authority and provenance.

For a located TS, attach the owning Grade A assignment with `--ts-review` when preparing a subject for scientific or kinetic review. The file carries the reaction ID, review reference, assigned coordinate and matching TS structure identity. The existing Phase 2 audit envelope is also supported. The builder consumes the decision and verifies its binding. A supplied site confirmation or a successful energy check alone cannot promote a candidate.

The immutable version includes the complete catalog, supplied parameters and coverage terms, file digests, site-mapping and thermochemistry versions, validation results and acceptance records. No operation opens the production database or dispatches a job. [Fe(110) validation report](../../reports/multiphase/phase2_3_chco_network_validation.json)

## Reviewing site identities and stoichiometry

Add `--site-proposal reports/multiphase/phase2_3_1_site_proposal.json` to the Fe(110) registry command above to reproduce the pending draft. To apply a researcher decision, also pass `--site-confirmation PATH_TO_FILLED_COPY.json`. Use the same parent inputs and output directory. The proposal identifies the exact parent network, and the decision identifies the original proposal by canonical JSON SHA-256. Each result gets its own immutable version.

Confirm physical site identities or define a site inventory with a documented geometric scope. Site IDs belong to individual surface domains; type names may recur on other surfaces. Use the existing interface ID for a cross-surface reaction. Record per-molecule occupancies and forward vacant-site counts. A null count map is unknown, an empty map confirms zero, and explicit zero counts remain in the review record. A partial decision can establish balance on one domain while another remains unknown. Checks multiply counts by species coefficients and compare each inventory independently. A known imbalance or conflict with an established occupancy fails the build. Confirmed reversibility creates an explicit inverse with exchanged vacancies. Scientific and kinetic review remain separate.

[Fe(110) researcher instructions and evidence](../../reports/multiphase/phase2_3_1_site_review.md)

A native project surface can declare its allowed `site_types` alongside its phase, facet and optional lattice metadata. Older definitions establish their local vocabulary through their existing site records. For a partial or extended catalog, supply `--site-catalog FILE` with the site review. This JSON declares `format: surface-site-types/1`, the exact `project_id` and a `surface_site_types` object mapping surface IDs to allowed names. The confirmation binds the file using `site_catalog_sha256`, computed with `scripts.artifact_io.sha256_json` on the parsed JSON. Keep a new configuration version when introducing a new type. Each interface site component resolves on its own surface. Geometry classification belongs to the source project. The generic builder consumes identities and counts without deriving centers from any particular lattice.

### Read-only identity audit

Use `--identity-report FILE` to inspect catalyst ownership before a reaction exists. Supply a single-project Phase 1 bundle, a `network-definition/1` or an immutable `reaction-network/1` snapshot. The command checks a snapshot's content version and binds the source file's SHA-256. It writes a new report once. Unknown owners, unassigned surfaces and missing structural provenance appear on the affected rows. An invalid declaration in this review view has no scientific or execution authority. Complete exchange and network validation retain their own entry points.

```console
python -m scripts.reaction_network tests/fixtures/multiphase/synthetic_identity_domains.json --identity-report ownership.json
```

For the Fe confirmation template also pass `--site-catalog reports/multiphase/phase2_3_1_fe110_site_types.json`. For an independent example, run `python -m scripts.reaction_network tests/fixtures/multiphase/synthetic_oxide_site_network.json`. This synthetic oblique oxide surface declares Lewis-acid and basic-oxygen inventories and binds one molecule across both.

## Interphase species transfer

Declare `reaction_type = interphase_transfer` in a Phase 1 bundle or a partial `network-definition/1`. Use one resident species ID per side and equal molecular coefficients. The two residents must have the same elemental composition and compatible declared charge. Their surface owners identify distinct phases. Their catalog records retain the individual structures, configurations and site footprints. Supply the reaction's contact ID when established. An unknown contact can be recorded in a partial or noneligible definition. An interface-private site still requires its own contact binding.

For each molecule the forward event releases the source footprint and consumes the destination footprint. The network checks the gross counts against the corresponding species coefficient, site ID and owning surface. Its transfer assessment reports signed changes in occupied sites, vacancies and capacity for each affected inventory. Null means an operand is missing. An unknown footprint on one side leaves the other side's accounting available. The existing molecular coverage contract supplies absolute capacities on a declared counting reference. The stoichiometric coefficients describe changes per reaction event.

Use `operating_conditions_ref` for a profile with a path and SHA-256 and `provenance` for the evidence bindings. The reaction definition and those bindings enter the reviewed subject. The usual `reversible` field controls construction of the reverse direction. A partial definition can keep it null. Structural validation creates no kinetic parameters or engine approval.

Run `python -m scripts.reaction_network tests/fixtures/multiphase/synthetic_interphase_transfer.json` to inspect the offline example. The accompanying synthetic counting cell and conditions are arithmetic test inputs. [Validation and qualification](../../reports/multiphase/stage_b2_2_2/completion.md)

## Cross-phase elementary reactions

Declare `reaction_type = cross_phase_elementary`, the participating `phase_ids`, their `surface_ids` and one `interface_id`. A two-phase contact and a single explicitly catalogued three-phase junction use the same fields. A collection of pairwise contacts does not establish a triple junction. A partial definition can set the interface to null when its participants have independent surface bindings. Interface-private species and inventories still require the matching explicit contact.

Reactant and product maps bind phase-resolved species and positive molecular coefficients. Molecule counts on opposite sides may differ. Association can produce an interface-bound species or a product on a third phase. Use `interphase_transfer` for an explicitly identified transfer of the same resident molecule. Formula equality alone selects neither class.

An optional `ts_species_id` binds a located transition complex to a catalog species. Its surface, contact, structure identity, total reacting composition, charge and transient site footprint must agree with the event. The TS contributes no stable population to either endpoint. TS acceptance requires the existing independent review.

Inspect `site_balance_by_inventory` for occupied and vacant counts on each side. A null operand leaves its balance open. The partial network path can also retain unknown participant composition or charge. Missing chemistry blocks structural promotion while independently known inventory proofs remain inspectable. The complete V1 exchange schema continues to require known species chemistry. Absolute physical capacities use the B.2.1 counting contract with one ID per shared inventory.

`cross_phase_qualification` reports the contact, endpoint stoichiometry, electronic evidence, Gibbs evidence, parameters, review and individual engine readiness. The value `supplied` describes data availability. MKM and KMC need their own native qualification and execution approval. [Scope, synthetic examples and qualification matrix](../../reports/multiphase/stage_b2_2_3/completion.md)
