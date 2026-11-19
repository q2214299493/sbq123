# Native model input contracts

Run the following commands from the checkout. Each creates an immutable input directory. Repeating the command verifies an existing identical directory. An existing directory containing changed inputs or solver outputs is rejected. The CLI validates the dataset revision, eligibility, table, species, configuration, units and normalization before writing. Model assembly confers no execution authority.

```powershell
$src = "reports/multiphase/phase2_4"
$cfg = "tests/fixtures/multiphase/native_interface_config.json"
python -m scripts.native_model catkinas "$src/synthetic_interface_dataset.json" $cfg "$env:TEMP/phase25-cat-input" --table "$src/synthetic_interface_catkinas.json"
python -m scripts.native_model zacros "$src/synthetic_interface_dataset.json" $cfg "$env:TEMP/phase25-zac-input" --table "$src/synthetic_interface_zacros.json"
```

Manifests bind the canonical dataset version, table and configuration hashes, file byte hashes, and the readback results. Run an authorized smoke test in a separate fresh copy of the inputs. The installed paths, runtime roles and example locations are in [the software inventory](../../configs/postprocessing_software.yaml). Both adapters currently model gases and adsorbates.

## CATKINAS single-point input

The local `ReadMe.m`, supplied single-point example input, and stored `result_single/data1.mat` define this adapter's field interpretation. MATLAB invokes `CATKINAS('INPUT_phase25')` from the run directory. The startup banner identifies build 20230524. The vendor documents `<->` as the equation identifier.

| Generated field | Meaning and units |
| --- | --- |
| `(i): lhs <-> rhs [Ea G0]` | One-based equation index in approved table order. Integer stoichiometric coefficients determine mass-action powers. Gas symbols denote species with pressures in bar. Adsorbates carry a site suffix. `#i` indicates a vacancy on inventory i, and `#` denotes a single inventory. The manifest maps physical species and sites to these tokens. |
| `Ea`, `G0` | eV per event. These are apparent single-temperature energies derived by Phase 2.4 from the numerical bar-based coefficients. Forward and reverse barriers are Ea and Ea − G0. At the recorded T the Eyring expression reproduces both coefficients. The activated collision model can therefore have an apparent Ea different from its input activation free energy. Derive a new table for each temperature. |
| `T`, `P_<gas>_FROZ` | Kelvin, frozen species partial pressure in bar. Inputs must sum to the table total pressure. Phase 2.4 converts activity relative to the supplied standard pressure to powers of numerical bar before the energy transformation. |
| `Qi_<species>_INIT`, `Qi_v_INIT` | Initial fractional occupation and remaining vacancy by site inventory. Single-site names use `Q_`. Coverage-specific barriers can be reused only if their specified fractions equal the initial condition and all equations conserve those fractions. |
| `CalMode`, `CalcDRC`, `Istart`, `npar` | 0 selects a single point, disables DRC and restart, and requests no parallel workers. |
| `ThermoMode=0`, `BarrierMode=-2`, `ConsMode=0` | Disable thermochemical corrections, adsorption/desorption barrier corrections and barrier constraints for this input so the fixed-point coefficients are preserved. |
| `MaxTime`, `MaxOdeTime`, `TimeMode=0`, `PlotMode=0`, `PlotType=0` | Per-Newton-attempt and per-ODE-attempt limits in seconds, fixed limits and no plots. An outer process timeout bounds the full smoke attempt. |

Two-site dissociation generates two typed vacancies and two adsorbates. The audited native grammar provides no verified exact forward-only or single-molecule cross-inventory representation. The adapter reports these cases before writing. A large finite reverse barrier or treating one bidentate molecule as two independent fragments would change the model.

## Zacros 4.0 files

The installed 4.0 manual and example define the following fields. The Phase 2.4 table already contains rates per matching occurrence at the approved T and gas pressure convention.

| File | Fields, units and numbering |
| --- | --- |
| simulation_input.dat | `temperature` K, `pressure` bar, `n_gas_species`, `gas_specs_names`, `gas_energies` eV/molecule, `gas_molec_weights` g/mol, `gas_molar_fracs` partial/total pressure. `n_surf_species`, `surf_specs_names`, `surf_specs_dent` give the surface inventory in the manifest's index order and its integer footprints. |
| Sampling and limits | `random_seed` integer, `snapshots off`, `process_statistics` and `species_numbers on event 1` sample every event. `max_steps` events, `max_time` simulated seconds, `wall_time` real seconds, `finish` terminator. `no_restart` suppresses checkpoints when requested. |
| lattice_input.dat | `lattice periodic_cell`, two in-plane `cell_vectors` in Å, `repeat_cell` integer counts. `n_site_types`, `site_type_names`, `n_cell_sites`, `site_types`, `site_coordinates` describe a project-defined ordered fractional basis. `neighboring_structure` uses one-based basis index pairs and unit-cell translations self, north, east, northeast or southeast. Links are undirected and periodic. |
| mechanism_input.dat | Each `step` has a unique name linked to reaction ID and direction. `sites`, `site_types`, `neighboring` encode the local graph. Project event edges are zero-based and native slots one-based. `initial` and `final` rows give entity number, species or vacancy, and dentate number. Each molecule shares an entity across its legs. `gas_reacs_prods` uses negative reactant and positive product counts. |
| Native rates | `pre_expon` is the condition-specific rate per match in s⁻¹ bar⁻ⁿ for total gas order n. `activ_eng` is 0 eV for the already thermally evaluated coefficient. Distinct directed steps retain each reviewed coefficient and the exchanged initial and final patterns. At empty coverage, count matching placements once and multiply by pressure powers. |
| energetics_input.dat | Ordered `cluster` blocks declare `sites`, `site_types`, optional `neighboring`, `lattice_state`, integer `graph_multiplicity` and `cluster_eng` in eV. Nonideal clusters and gas energies require a matching reviewed local-event energetics hash. The reviewed local event must also declare `coefficient_basis: isolated_reactants` and a dimensionless `forward_proximity_factor` between zero and one. The builder writes explicit `prox_factor` values ω forward and 1 − ω reverse for the two directed steps. The synthetic ideal configuration explicitly supplies zero gas energy and an empty cluster list. Zacros requires a nonempty file, represented by zero-energy vacancy terms for its two inventories. |
| state_input.dat | Optional `initial_state` with `seed_on_sites <species> <indices>`. Global site numbers are one-based with basis sites contiguous in each repeated cell. Each seed must have the required typed footprint, connected sites and no overlap. An explicitly empty seed list starts vacant. |
| Restart | With `write_restart: true`, native checkpoint writing remains enabled. To stage a previous checkpoint, pass `--checkpoint` and `--checkpoint-receipt`; the receipt binds `checkpoint_sha256` and `model_sha256` (canonical manifest hash before restart). Zacros gives an existing `restart.inf` priority over normal inputs. The smoke run used a fresh directory with restart disabled. |

The local graph count divides unique transitions by the configured number of reference sites. It must equal the approved patterns per reference site. The coefficient was already divided by this factor in Phase 2.4. Explicit forward/reverse steps trigger Zacros warning 4008. For this ideal benchmark their numerical ratio satisfies the reviewed equilibrium relation. Interacting lattices, populated starts and checkpoint resumes have static coverage only. Their native numerical behavior requires separate model-specific validation.
