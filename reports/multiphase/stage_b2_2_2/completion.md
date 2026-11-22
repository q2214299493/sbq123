# Stage B.2.2.2 | Interphase species transfer

The exchange validator and the network builder now recognize an explicit `interphase_transfer`. A transfer moves molecules between two phase-resolved surface residents and accounts for vacancies on each side. The archived Fe(110) network retains its blocked MKM status. [Validation receipt](transfer_validation.json)

## Identity and contract assessment

| Question | Existing authority | Transfer check |
| --- | --- | --- |
| What moves? | The species IDs in the reaction's reactant and product maps | One resident species on each side, equal molecular counts, equal elemental compositions, consistent known charge |
| Where does it move? | Species surface IDs, surface phase owners, and the reaction's interface ID | Distinct phases, disjoint endpoint surfaces, reaction scope covering exactly those endpoint surfaces, matching interface when established |
| What changes at each site? | Catalog footprints and gross reaction vacancy counts | Release the coefficient-weighted source footprint and consume the coefficient-weighted destination footprint. Check each inventory even when its counterpart is incomplete. |
| What establishes conditions and origin? | Optional `operating_conditions_ref` uses the existing artifact path and SHA-256 contract. Reaction provenance and scientific review retain their existing fields. | The example's conditions and synthetic reversibility assumption resolve to a checked fixture. An absent profile remains unknown. |
| What establishes direction? | Existing three-state network reversibility and reaction stoichiometry | A declared reversible reaction has an explicit inverse with both vacancy maps exchanged. Unknown reversibility leaves the reverse direction absent. |

The V1 reaction schema gained an optional classification and a transfer-specific condition-profile reference. The V1 exchange path still requires complete typed fields, including Boolean reversibility. Partial evidence uses the existing `network-definition/1` path. A draft or blocked transfer may leave the contact unknown. Existing contact-private species and sites still require the matching interface. The B.1 V2 rate and source-term schemas retain their original bytes.

The two synthetic Ar residents have different species IDs, surfaces and structure labels. Their hosts are two phases of the same material. Both inventories carry the same site-type label and have distinct IDs. The pre-existing species fingerprint retains their separate identities. Coexistence alone creates no reaction. Synthetic structure labels identify the test states only.

## Independent conservation witness

One forward event moves one molecule in a finite synthetic cell. The separate counting fixture declares three members in pool A and five in pool B. B.2.1 coverage accounting and B.1 stoichiometric projection independently reproduce these hand counts.

| Measured quantity in the test cell | Before | After | Change |
| --- | ---: | ---: | ---: |
| Molecules on phase A | 2 | 1 | -1 |
| Molecules on phase B | 1 | 2 | +1 |
| Occupied / vacant / capacity in A | 2 / 1 / 3 | 1 / 2 / 3 | -1 / +1 / 0 |
| Occupied / vacant / capacity in B | 1 / 4 / 5 | 2 / 3 / 5 | +1 / -1 / 0 |
| Molecules in the cell | 3 | 3 | 0 |
| Physical sites in the finite cell | 8 | 8 | 0 |

Element, charge and each inventory have zero residual for this unit reaction extent. Adding the two capacities here is justified by the explicitly enumerated disjoint members of one cell. Source terms retain their native denominator. The network alone establishes capacity *change* for the mapped event. Absolute capacity requires independent inventory data.

## Evidence qualification for the fixture

| Dimension | Result | Binding or outstanding evidence |
| --- | --- | --- |
| Structural representation | STRUCTURALLY_VALID | Two synthetic endpoint references, distinct species and phase identities, explicit contact and gross vacancy maps |
| Stoichiometric validity | Verified | Molecular count, Ar, charge and both inventory balances pass |
| Energetic support | Missing | No located TS or supported barrierless treatment, compatible free-energy barriers or reaction Gibbs energy |
| Kinetic parameterization | Missing | No rate law or assigned rate parameters |
| Scientific review | Unreviewed | Synthetic provenance, no accepted scientific decision or bound network review |
| Engine execution eligibility | Blocked | MKM status blocked and execution authorization false. Neither native engine was invoked. |

A null site map leaves the corresponding occupied or vacancy change and capacity proof unavailable. The other resident retains its known inventory changes. An unresolved contact holds structural promotion open while known stoichiometry can still be inspected. A contradictory known site, element, charge or molecular balance fails validation. The test cell supplies no evidence for a real transfer pathway, its reversibility or its rate.

## Changed files

- `configs/kinetics/reaction.schema.json`
- `scripts/multiphase_contracts.py`
- `scripts/reaction_network/catalog.py`
- `scripts/reaction_network/builder.py`
- `scripts/kinetic_data/interphase_transfer.py`
- `modules/reaction_network/README.md`
- `tests/test_interphase_transfer.py`
- `tests/fixtures/multiphase/synthetic_interphase_transfer.json`
- `tests/fixtures/multiphase/synthetic_transfer_context.json`
- `reports/multiphase/stage_b2_2_2/transfer_validation.json`
- `reports/multiphase/stage_b2_2_2/completion.md`
- `reports/multiphase/stage_b2_2_2/regression.md`
- `reports/multiphase/stage_b2_2_2/handoff.md`
- `modules/state_handoff/events/history-stage-b2-2-2-interphase-transfer-20261122.json`

[Windows regression results](regression.md) · [State Handoff review](handoff.md)
