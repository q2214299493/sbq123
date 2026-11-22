# B.2.3.2.3 Zacros 4.0 synthetic oxide bridge validation

**Stage A passed. Native acceptance is pending.** The native-format lattice, seeds and elementary graph patterns encode two distinct CO2 molecules on seven sites. Direct inspection of the 4.0 release shows why the installed serial executable cannot qualify this case from the structural members alone. The researcher chose to retain the missing numerical inputs and complete the offline checks. There was no native process, accepted native output or approval request for an executable bundle.

## Offline structural readback

| Check | Observed in the rendered input |
| --- | --- |
| Finite, open site inventory | Acid nodes 1, 2, 3, 4 and oxygen nodes 5, 6, 7. One counting cell. |
| All typed edges | (1,5), (2,5), (2,6), (3,6), (3,7), (4,7) |
| Ordered native seeds | bridge-1 uses (1,5), bridge-2 uses (2,6). Each seed denotes one `CO2bridge*`; acid is leg 1 and oxygen is leg 2. |
| Initial desorption pattern matches | (1,5) and (2,6). Edge (2,5) connects legs on different molecules. Reversing only the first seed removes its match in the independent checker. |
| Initial adsorption pattern matches | (3,7) and (4,7). Both use oxygen-3, so only one can be added with the seeds fixed. |
| Initial inventory | Two molecular entities. Acid occupied 2/4 and vacant 2/4. Oxygen occupied 2/3 and vacant 1/3. |
| Maximum occupancy | Three disjoint bridges, witnessed by (1,5), (2,6), (3,7). Three oxygen nodes bound the maximum from above. |
| Per-event accounting | Adding either available bridge gives three molecules, one vacant acid and zero vacant oxygen. Removing one original bridge from the initial state gives one molecule, three vacant acid and two vacant oxygen. Both changes are offline consequences of the declared footprint. |

The [native members and hashes](native/input_manifest.json) reproduce source graph SHA-256 `77d0f2fe9ab30743eec527bf412c4f35ed0097dc66fb9514ae0bb541673d0fea` and archived mapping SHA-256 `bb0f706fefc969bdf67a5fa44b2c21f8f61ed2e09f1778a76d6b1b6d342e0971`. The structural manifest itself hashes to `01f93bb5ed6d6b1dc9e422a9ef90e554558e57862a1713b53469eae94ed3cdae`. Only lattice and state are complete native files. The simulation, energetics and mechanism templates carry explicit unbound fields. The source reaction's reversibility is null. The two directed patterns test adsorption and desorption placement.

## Why a zero-event run still needs input

The installed serial executable has SHA-256 `84a8f88d6df633eeea9eeac8aa9227237cdf2564a4dc72e0cab8a18c4ce119d2`, matching the archived 4.0 executable. The 4.0 vendor guide (19 July 2024) hashes to `cc64e35121f1637d3a371330882d2a53816bb15f0c3ee4d9b3b6fd4bd557f846`. Pages 52-54 cover explicit lattices, 60-68 cover patterns and rates, 69-71 cover seeding, and 87 describes event discovery diagnostics. Source reviewed in the local vendor distribution `zacros_4.0.zip` has archive SHA-256 `55ae665d845ad1120241b98e0a72192bb3737ade801275ec13c06d81fae9abae`. The installed companion executables are CE_Fit and MT_Jump_Ahead. Neither provides the Zacros KMC parser/initialization entry point. [Vendor release and installed guide index](../stage_b2_3_2_1/evidence.json)

| Vendor release source location | Consequence for this test |
| --- | --- |
| `commandline_module.f90` 30-69, `zacros_main.F90` 209-228 | The stock CLI has input and limit overrides. A lattice path override still enters the same five readers. The simulation reader runs first. There is no parser-only CLI option. |
| `simulation_parser_module.F90` 2738-2760, 1851-1858 | Temperature, total pressure, molecular weights and feed fractions for declared gases, and surface dentation must be supplied. Fractions may sum below unity. |
| `energetics_parser_module.f90` 750-761, `mechanism_parser_module.f90` 2991-3029 | An empty cluster model fails. Each directed step needs a prefactor and activation energy. A reversible-step declaration would also require a prefactor ratio. |
| `zacros_main.F90` 255-274, 516-528, 640-665 | Initialization seeds the lattice and catalogues processes before the serial zero-step guard. The guard precedes event execution. Enabling checkpoint output allows inspection of the zero-event state. |
| `lattice_handle_module.F90` 649-702, `restarts_module.F90` 141-155 | Native seeding follows leg order. The restart lattice-state block records per-site entity, species and leg plus an entity-to-sites table. These two views can be cross-checked. |
| `kmc_simulation_handle_module.F90` 1636-1647, 1754-1765, 2352-2360 | Initialization debug rows identify each elementary step and its ordered nodes. These rows can distinguish two adsorption plus two desorption placements from a different catalogue with the same total. |

## Minimum missing inputs and approval

The gas identity CO2, the surface species, its dentation, site types, graph and starting molecules are known. For a parameterized zero-event fixture, supply the intended temperature (K), total pressure (bar), positive CO2 fraction or equivalent partial pressure, the synthetic adsorption and desorption Arrhenius parameters (prefactor with native units/pressure basis and activation energy in eV for each), and a complete energetic cluster definition with a stated energy convention. A documented null-interaction *model* can be supplied explicitly. Vendor example 100 supplies a traceable CO2 mass of 44.0096 in the native convention; its simulation input hashes to `30de7fa0eae4d5646016796156efb57d2986fe5a1e3172cd9968fb04ac0d002f`. Its kinetic parameters belong to that example. The stock reader permits omitted gas energies with a warning. Confirm the selected gas-energy convention when binding the control dataset. This diagnostic needs no real oxide rate measurement or equilibrium constant.

Stage B can subsequently review the five native reader confirmations. Stage C can review the restart site rows and the initialization section of `process_debug.txt`. Event-zero trajectory sampling can produce a header without a state row when the serial loop exits before propagation. The restart provides the site ledger in that case. A total number of processes or a cumulative count of executed events cannot establish the four ordered matches. Each native launch requires independent hash-bound approval. A complete approved prior output may be inspected read-only. Proposed serial limits are zero events, 15 s native wall limit, 30 s external timeout, one process and zero retries. The wall-time control is checked in the simulation loop; the external timeout covers startup. Input and plan hashes for a runnable bundle remain null.

The surface KMC entry gate owns model qualification. The repository's shared action check verifies an existing module decision against the current state hash, allowed action and vocabulary. An executable path and the opt-in archived benchmark runner supply no authorization for this oxide. Stage D has no execution plan. For future dynamic acceptance, measured events must satisfy `N = 2 + Nads - Ndes`, vacancy counts `(4-N, 3-N)`, and the separately specified checkpoint-recovery comparison. [Stage requirements and approval boundaries](stages.json) / [parser status](parser_receipt.json) / [initial-state status](initial_state_receipt.json)

Both worktrees passed 680 focused offline tests. The 8 archived native re-executions were explicitly excluded. Hash verification covered the original graph, Ni/Cu evidence and the eight benchmark archives. [Regression scope and results](regression.md) / [State Handoff](handoff.md)

## Changed files

- `modules/surface_kmc/README.md`
- `scripts/surface_kmc/bridge_input.py`
- `tests/test_zacros_bridge_input.py`
- `reports/multiphase/stage_b2_3_2_3/.gitattributes`
- `reports/multiphase/stage_b2_3_2_3/native/lattice_input.dat`
- `reports/multiphase/stage_b2_3_2_3/native/state_input.dat`
- `reports/multiphase/stage_b2_3_2_3/native/mechanism_input.dat.in`
- `reports/multiphase/stage_b2_3_2_3/native/simulation_input.dat.in`
- `reports/multiphase/stage_b2_3_2_3/native/energetics_input.dat.in`
- `reports/multiphase/stage_b2_3_2_3/native/input_manifest.json`
- `reports/multiphase/stage_b2_3_2_3/stages.json`
- `reports/multiphase/stage_b2_3_2_3/parser_receipt.json`
- `reports/multiphase/stage_b2_3_2_3/initial_state_receipt.json`
- `reports/multiphase/stage_b2_3_2_3/completion.md`
- `reports/multiphase/stage_b2_3_2_3/regression.md`
- `reports/multiphase/stage_b2_3_2_3/handoff.md`
- `modules/state_handoff/events/history-stage-b2-3-2-3-oxide-zacros-structural-preflight-20261122.json`
