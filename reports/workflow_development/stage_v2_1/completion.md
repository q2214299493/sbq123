# V.2.1 reaction-to-model readiness

Scientific Intake now takes a versioned reaction network through conservation, state thermochemistry, forward/reverse parameter qualification and offline native input assembly. Run it from the repository root with `python -m scripts.scientific_intake --kinetic-readiness PROJECT TASK`. The JSON response contains a separate record for each reaction and a whole-network decision for each engine.

## Reproducible examples

| Project and task | Offline result | Native boundary |
| --- | --- | --- |
| [Ni/Cu project](../../workflow_design/stage_f1_2/nicu/project.yaml) and [task](../../workflow_design/stage_f1_2/nicu/task.yaml) | All four synthetic steps qualified on the 400 K Gibbs reference. The CATKINAS input matched the archived file byte for byte, SHA-256 `b793e6f37f2262e4a006f912d18950c17581ccc014aa9779008741a4e31890f8`. The resulting receipt, result and V2.1 rate bindings support the archived TOF of **81.5127701616477 events per reference site pair per second**. Stable DRC values were 0.45025755212448043 for hydrogenation and 0.040690451158404334 for transfer. Statistical rate uncertainty remains unknown. [Output including native input](nicu.json) | The reference pair contains one Ni and one Cu site. The pressure point was H₂ 1.0, NO 0.5 and HNO 0.1 bar. CATKINAS input was reconstructed. The supplied project lacks a qualified Zacros configuration, and three reactions lack reviewed event patterns. |
| [Fe(110) project](fe110_project.yaml) and [task](../../workflow_design/stage_f1_2/fe110/task.yaml) | For CH* + CO* → CHCO*, IS/TS/FS energies were −385.14767079, −384.17406905 and −384.48836276 eV. The forward, reverse and reaction electronic differences were +0.97360174, +0.31429371 and +0.65930803 eV. The thermochemistry owner reproduced the TS-local ZPE of 0.51405165 eV with the Grade A assignment and mode 12 excluded. [State records and missing evidence](fe110.json) | Both endpoints require compatible vibration or correction evidence. Temperature, standard state, reversible direction, charge/site balance and reviewed rate parameters remain unresolved. All three Gibbs differences and both rates remain null. Both engines are blocked. The three CONTCARs, three electronic OUTCARs and TS vibrational OUTCAR at the declared relative paths in the development evidence tree independently matched the seven intake SHA-256 values. The published example reads the archived intake and review. |
| [Oxide project](../../workflow_design/stage_f1_2/oxide/project.yaml) and [task](../../workflow_design/stage_f1_2/oxide/task.yaml) | The seven-node synthetic graph has two multidentate CO₂ entities. Acid occupancy is 2/4 and oxygen occupancy 2/3. The topology, original failed initialization and separately hash-pinned corrected input can be inspected independently. [Graph, inventories and receipts](oxide.json) | The consumed plan failed on `temperature 400` with Zacros error 1002. The five corrected native files verify against their manifest. Successful initialization of those bytes remains unverified. Missing kinetic evidence blocks both engines. |

Each linked result is public CLI stdout serialized with LF line endings. Two fresh processes with different Python hash seeds produced identical bytes for each example. The State Handoff event binds their exact SHA-256 digests.

## Scientific ownership and interpretation

- The existing network owner verifies its version and applies the element, charge and site balance rules. Unknown inventories appear as unresolved. Inconsistent totals appear as invalid input on the affected reaction. Phase, surface, interface, stoichiometry and state identity come from the network.
- For state intake, the existing thermochemistry engine selects compatible records, uses the signed TS assignment, applies documented conditions and checks three-state Gibbs closure at its 1e−9 eV tolerance. Reviewed reaction-level energy triples use the network owner's existing 1e−8 eV closure tolerance. Newly supplied state evidence can yield a preview. A changed scientific subject requires a new bound snapshot and review before kinetic handoff.
- The kinetic parameter engine applies its existing rate laws, standard activities, gas and vacancy orders, validity ranges, uncertainty and detailed-balance checks per reaction. A null rate remains unknown. An explicitly irreversible reverse direction is labeled inapplicable. Where available, archived native coefficients and their denominator come from the network-bound V2.1 rate contract.
- Reaction qualification and whole-network assembly have separate results. For example, removing the adsorption model from the four-step benchmark still yields the three other rows' parameters. Each engine uses its existing input builder and reports its own mapping and configuration blockers. A separate offline test assembles Zacros inputs on a supported synthetic lattice and rejects an unsupported neighbor direction. All three published examples carry `execution_authorized: false`.

## Baseline and scope

Development took place on `codex/v2-1-kinetic-pipeline` in an isolated worktree. Verified ancestry in order was R.2.5 `9ee940e9`, V.1.1 `629ada12`, V.1.2.1 `6dbc0fb3`, F1.1 `89d140de` and the requested F1.2 baseline `02680f0b5c18d8c157aa77c8b804cfb57a781953`. The source, fixtures and scientific evidence were reused in place. This change adds an option to the existing CLI and extends existing owners. Existing intake and inspection commands remain available.

## Handoff

State Manager recorded pending `proposal-00871cff5531a3d133e03c8c` for [the history event](../../../modules/state_handoff/events/history-v2-1-reaction-kinetic-readiness-20261122.json). The choices are `approve` and `reject`. The initial audit recorded pre-existing drift on `docs/06_MODULE_MAP.md#module_row:transition_state_search`. As on F1.2, the separate `sync --safe-only` check exited 2 with `state history source changed before proposal generation`. All 355 checked event, cache and selected projection files had identical membership and digests before and after safe-only. The proposed historical projection awaits human review.

## Changed files relative to F1.2

```text
modules/kinetic_data/README.md
modules/state_handoff/events/history-v2-1-reaction-kinetic-readiness-20261122.json
reports/workflow_development/stage_v2_1/completion.md
reports/workflow_development/stage_v2_1/fe110.json
reports/workflow_development/stage_v2_1/fe110_project.yaml
reports/workflow_development/stage_v2_1/nicu.json
reports/workflow_development/stage_v2_1/oxide.json
scripts/kinetic_data/project_inspection.py
scripts/kinetic_data/project_references.py
scripts/kinetic_parameters/engine.py
scripts/scientific_intake.py
tests/test_kinetic_pipeline.py
```

## Windows offline regression

Python 3.13.9 and pytest 8.4.2 ran the 39 modules below in one invocation from the isolated checkout with §python -m pytest -o addopts= -q -ra --tb=short§. The final run had **1,068 passed, one skipped, zero failed** in 131.46 s. The skip was §test_live_closed_cycle§, which requires an explicitly reviewed native run and decision. Ruff and §py_compile§ passed on all five changed Python files. Full repository discovery and Linux were outside this run.

| Selection (module names omit §tests/test_§ and §.py§) | Coverage |
| --- | --- |
| §kinetic_pipeline§ (13 passed) | Three public CLI demonstrations, immutable binding, local source tampering without observable selection, conflicting archives, partial multi-reaction output, invalid inventory, independent adapter assembly, unsupported topology, complete three-state Gibbs closure, missing IS and missing FS. |
| §project_inspection§ (15 passed), §scientific_intake§, §thermochemistry§ | F1.2 replay and legacy CLI, record selection and thermal calculations. A changed mixed-mode error message was detected during development and restored before the final run. |
| §rate_network_binding§, §b1_contract_acceptance§, §rate_dimensions§, §rate_output_v2§, §kinetic_parameters§ | Network binding, ten archived rates, coefficient units and scientific qualification. |
| §state_manager§, §b4_state_governance§, §state_log_projection§, §state_sync_repository_items§, §state_sync_task_ownership§, §state_sync_safe_only§, §registry_schema§, §registry_write§, §registry_excel_promotion§, §b4_registry_governance§ | State, safe-only mutation checks and Registry isolation. |
| §zacros_zero_event_control§, §zacros_zero_event_native_receipt§, §native_advanced§, §mkm_single_point§ | Serialization, offline receipts, native preparation and authorization gates. |
| §native_imports§, §stoichiometric_sources§, §b5_architecture_boundaries§ | Independent adapter imports, conservation arithmetic and maintained import graph. |
| §multiphase_contracts§, §reaction_network§, §inventory_accounting§, §multidentate_coverage§, §interphase_transfer§, §cross_phase_elementary§, §catkinas_oxide_multidentate_audit§, §oxide_bridge_topology§ | Fe(110) blocking, multiphase identities, species and vacancy accounting, interface and oxide fixtures. |
| §native_rate_adapters§, §b1_native_acceptance§, §catkinas_closed_cycle§, §zacros_bridge_input§, §native_model§ | Engine-specific input reconstruction and archived result replay. |

The CLI, archive replay and regression used offline data. No VASP, NEB, DIMER, CATKINAS or Zacros jobs were run. No production SQLite writes, automatic scientific acceptance or execution approvals were performed.
