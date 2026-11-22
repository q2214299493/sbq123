# F1.2 regression and change inventory

**Windows offline result: 996 passed, one explicitly gated live CATKINAS test skipped, zero failures (116.24 s).** The run used Anaconda Python and pytest with `-o addopts= -q -ra --tb=short` in the isolated feature worktree. The skip requires both `--catkinas-reviewed-run RUN DECISION` arguments. No native execution option was supplied. Ruff and `py_compile` passed on all seven changed Python files (six runtime and one test file).

## Tests run

The complete test-file selection follows. Each name denotes `tests/test_<name>.py`. Some files exercise several regression groups.

| Group | Test files |
| --- | --- |
| New inspector, references, three acceptance cases and existing positional CLI | `project_inspection`, `scientific_intake` |
| R.2.1 and ten-output/two-qualification byte replay | `rate_network_binding`, `b1_contract_acceptance` |
| R.2.2 state, safe-only and registry | `state_manager`, `b4_state_governance`, `state_log_projection`, `state_sync_repository_items`, `state_sync_task_ownership`, `state_sync_safe_only`, `registry_schema`, `registry_write`, `registry_excel_promotion`, `b4_registry_governance` |
| R.2.3 serialization, historical receipts and native authorization | `zacros_zero_event_control`, `zacros_zero_event_native_receipt`, `native_advanced`, `mkm_single_point` |
| R.2.4 import and conservation boundaries | `native_imports`, `stoichiometric_sources`, `b5_architecture_boundaries` |
| B.1 dimensional, rate and kinetic contracts | `rate_dimensions`, `rate_output_v2`, `kinetic_parameters` |
| B.2 multiphase contracts and Fe draft qualification | `multiphase_contracts`, `reaction_network`, `inventory_accounting`, `multidentate_coverage`, `interphase_transfer`, `cross_phase_elementary`, `catkinas_oxide_multidentate_audit`, `oxide_bridge_topology` |
| Native replay and model boundaries | `native_rate_adapters`, `b1_native_acceptance`, `catkinas_closed_cycle`, `zacros_bridge_input`, `native_model` |

The 15 inspector tests check the three positive archives against independent numerical and identity expectations. They cover edited bytes, wrong network, cross-project substitution, absent optional configuration, missing required scientific evidence, unsupported version, escaping path, duplicate roles across scopes or YAML keys, absent raw files, intake-only and historical context-only projects, multiple reactions/points, catalog-only inspection, missing uncertainty evidence and incompatible CLI options. The changed-DRC test snapshots every input file before and after inspection and verifies that turnover remains available from its own evidence.

## Acceptance output identity

Hashes cover published UTF-8 JSON with LF line endings, generated through the public CLI.

| Case | Output SHA-256 |
| --- | --- |
| Fe(110) | `388b6fa9ee167254e9866483084949af8d3a398980d75741f1c3c6dc495e7cc8` |
| Ni/Cu | `29da4a8e43efe0f02c4dd275995bc18f4e919dff22a97c4f277532ab813f05c7` |
| Synthetic oxide | `a36e0ad3363e379a6fc1f0f1299b90f1dec45bf9a1d6fb5f945cec65ae57fd4e` |

**Limits.** This is a focused Windows regression. The full repository suite and Linux suite were not run for F1.2. Native solver behavior, source files unavailable at the declared base, arbitrary project-specific observable names and a successful corrected-oxide run are outside these results. A successful inspector command can report blocked science.

## Exact changed files

- `modules/kinetic_data/scientific_intake.md`
- `modules/state_handoff/events/history-f1-2-readonly-project-inspection-20261122.json`
- `reports/workflow_design/stage_f1_2/completion.md`
- `reports/workflow_design/stage_f1_2/fe110/inspection.json`
- `reports/workflow_design/stage_f1_2/fe110/project.yaml`
- `reports/workflow_design/stage_f1_2/fe110/task.yaml`
- `reports/workflow_design/stage_f1_2/nicu/inspection.json`
- `reports/workflow_design/stage_f1_2/nicu/project.yaml`
- `reports/workflow_design/stage_f1_2/nicu/task.yaml`
- `reports/workflow_design/stage_f1_2/oxide/inspection.json`
- `reports/workflow_design/stage_f1_2/oxide/project.yaml`
- `reports/workflow_design/stage_f1_2/oxide/task.yaml`
- `reports/workflow_design/stage_f1_2/regression.md`
- `scripts/kinetic_data/project_inspection.py`
- `scripts/kinetic_data/project_references.py`
- `scripts/kinetic_data/reaction_intake.py`
- `scripts/reaction_network/builder.py`
- `scripts/scientific_intake.py`
- `scripts/thermochemistry/engine.py`
- `tests/test_project_inspection.py`
