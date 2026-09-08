# File Index

This is a navigation index, not a duplicate file listing. Use `git ls-files` for the complete tracked inventory.

Strategy improvement: `modules/transition_state_search/LEARNING.md` documents
warm-start capture, reference BA-Sella selection, immutable failure history,
the submission retry check, and the complete local CLI. Its policy is
`configs/ts_strategy_engine/learning.yaml`; code lives in the existing
`scripts/ts_strategy_engine/` module and tests in `tests/test_ts_strategy_learning.py`.

Sella integration: `modules/transition_state_search/SELLA_BRANCH.md` describes
the optional MatRIS NEB/Sella route, existing BA-Sella route, shared VASP
learning loop and local validation limits. Entry points are
`scripts/prepare_ml_candidate_active_learning.py` and
`scripts/prepare_ml_candidate_rerun.py`; optimizer code is
`scripts/ml_sella_candidate.py`, tested by `tests/test_ml_sella_candidate.py`.
The current warm-start proposal is `outputs/ts_sella_integration_20260905/strategy_proposal.json`.

MZ73 MatRIS/Sella smoke validation: `scripts/matris_sella_smoke.py` enforces
one-structure runtime limits; `tests/test_matris_sella_smoke.py` covers budget
and authorization rejection. The job-1509 request, returned files and work-side
review are under `outputs/matris_sella_smoke_20260905/`.

## Authority

| Path | Owns | Read when |
|---|---|---|
| `AGENTS.md` | startup, monitoring, state, quality, and Git rules | every new thread |
| `tasks/current_task.md` | the one executable task | every continuation |
| `docs/02_CURRENT_STATE.md` | compact live snapshot and next action | every continuation |
| `docs/00_PROJECT_BRIEF.md` | long-term goal and success criteria | new direction or scope conflict |
| `docs/01_METHOD_PROTOCOL.md` | approved scientific methods and calculation standards | new calculation or method change |
| `docs/03_DECISIONS_LOG.md` | durable decisions and consequences | when a prior decision matters |
| `docs/04_ERROR_LOG.md` | unresolved scientific/workflow failures | diagnosis or retry |
| `docs/06_MODULE_MAP.md` | module status, dependencies, and current gate | module handoff or intake |
| `modules/<module>/README.md` | module inputs, workflow, outputs, and done criteria | work in that module |
| `docs/09_USER_PREFERENCES.md` | durable user preferences | preference-sensitive task |
| `docs/10_TS_VALIDATION_PROTOCOL.md` | TS A/B/C grading | TS or frequency work |
| `docs/11_DATA_PROVENANCE_PROTOCOL.md` | registry and traceability rules | calculation/result registration |
| `docs/12_WORKFLOW_ARCHITECTURE.md` | end-to-end stage order and boundaries | cross-module planning |
| `docs/13_WORK_HANDOFF.md` | current Fe(110) handoff, blockers, conflicts, and takeover sequence | task transfer or new operator onboarding |
| `skills/fe110-adsorbate-pilot-builder/` | true Fe(110) adsorption pilot-building rules | preparing small Fe(110) adsorbate tests |
| `skills/chemical-plausibility-gate/` | final chemical identity, reaction-event, and plausibility gate | before result promotion, endpoint reuse, or Excel insertion |
| `skills/dataset-compatibility-gate/` | result comparison, deduplication, registry, and Excel promotion gate | before comparing or promoting calculated results |

Current protocols override historical reports, calculation snapshots, imported packages, and memory records.

## Current Code

| Path | Purpose |
|---|---|
| `scripts/ts_strategy_engine/` | V3 reaction fingerprint, TS-template retrieval, strategy composition, NEB analysis, DIMER handoff, and learning records |
| `scripts/neb_agent/` | internal NEB numerical backend: endpoint/path checks, path generation, analysis, restart, split, and crop |
| `scripts/convergence/` | convergence campaign generation, validation, and summaries |
| `scripts/adsorption/build_fe110_adsorption.py` | clean Fe(110) top-layer site generation and anchor-based adsorbate placement |
| `scripts/adsorption/gas_vasp_common.py` | single owner of gas-reference INCAR, KPOINTS, LSF job script, POSCAR rendering, and POTCAR metadata |
| `scripts/adsorption/build_gas_h2_chx.py` | isolated H2/CH/CH2/CH3/CH4 reviewable VASP gas-relaxation inputs |
| `scripts/adsorption/build_gas_cho_chxo.py` | isolated CHO/CH2O/CH3O/CH4O reviewable VASP gas-relaxation inputs |
| `scripts/adsorption/build_gas_oxygenated_isomers.py` | isolated COH/CHOH/CH2OH oxygenated-isomer VASP gas-relaxation inputs |
| `scripts/adsorption/build_fe110_c2_coads.py` | user-reviewed initial and missing-only C+O/C2/C2O/C2+O Fe(110) structure builder |
| `scripts/adsmind_lite/` | lightweight adsorption pre-screening, relaxed-state analysis, deduplication, and export |
| `scripts/ts_validation/` | reviewed TS-to-frequency handoff |
| `scripts/state_manager/` | immutable repository-lifecycle events, audits, projections, review proposals, and the `repo-state` CLI |
| `modules/state_handoff/` | repository task/history lifecycle policy, immutable event ledger, and approved unique-content archive |
| `configs/state_handoff.yaml` | managed-view, review, archive, size, and external-path policy for `repo-state` |
| `configs/state_handoff_event.schema.json` | versioned JSON Schema for immutable state events |
| `scripts/git_snapshot.ps1` | guarded repository snapshot |
| `scripts/init_registry.py` | empty registry initialization |
| `skills/` | repository-backed project skills |
| `configs/` | machine-readable routing, thresholds, TS families/templates, schemas, and software paths |
| `configs/skill_routing.yaml` | skill ownership and result-governance routing |
| `configs/execution_backends.yaml` | local `work`, AQCat GPU, and VASP server roles plus required handoffs |
| `configs/aqcat25_handoff.schema.json` | exact v2 adsorption/TS work-GPU handoff paths and types |
| `configs/aqcat25_domain_gate.yaml` | Fe45 AQCat25 empirical force thresholds and applicability limits |
| `scripts/aqcat25_handoff.py` | executable schema, file-hash, atom-order, and Selective Dynamics validator |
| `scripts/aqcat25_calibration.py` | VASP final-force extraction and AQCat25 calibration metrics |
| `scripts/aqcat25_gpu_job.sh` | generic manifest-driven MZ73 adsorption job and producer exit record |
| `scripts/aqcat25_ml_neb.py` | AQCat25 ASE ML-NEB/conditional ML-CI-NEB complete-path runner and restart evidence |
| `scripts/aqcat25_ml_neb_job.sh` | MZ73 complete-path Slurm wrapper with producer exit evidence |
| `scripts/aqcat25_ml_path_committee.py` | fixed-path inference with at least three unique AQCat25 checkpoints; emits uncalibrated per-image model disagreement |
| `scripts/ts_strategy_engine/ml_neb_path.py` | work-side GPU path manifest validation and accepted-review finalization |
| `scripts/ts_strategy_engine/active_learning_path.py` | complete-path VASP-label batch, force-error aggregation, fine-tuning, and full-path rerun state machine |
| `configs/true_fe110_production.yaml` | selected five-layer/`5x5x1` production protocol; any layer-count study is a separate non-mixing validation branch |
| `configs/fe110_adsorbates_step12a.yaml` | Step 12A adsorbate anchors, internal geometries, orientations, and Fe-anchor distances |
| `configs/fe110_adsorbates_h2_chx_pilot.yaml` | accepted H2/CHx gas geometries, placement rules, and representative pilot sites |
| `configs/fe110_adsorbates_oxygenated_main_pilot.yaml` | CHO/formyl, CH2O/formaldehyde, CH3O/methoxy, and CH4O/methanol Fe(110) pilot placement rules |
| `configs/adsmind_lite/` | surface taxonomy, high-risk gates, adsorbate rules, analysis thresholds, and backend modes |
| `configs/adsmind_lite/evidence_gate.yaml` | whitelist-stop, authoritative-literature fallback, provenance, and stable-motif count rules |
| `scripts/adsmind_lite/evidence_gate.py` | deterministic adsorption external-evidence decision and motif deduplication |
| `tests/` | current-code and repository-contract regression tests |
| `pyproject.toml` | Python dependency, Ruff, format, and pytest authority |

Exact commands belong only in the owning module README. `scripts/README.md` and `skills/README.md` provide short routing indexes.

## Current Scientific Data

| Path | Status |
|---|---|
| `modules/convergence_workflow/inputs/fe110_true_facet_thickness_20260627/` | corrected true Fe(110) 4-8-layer campaign inputs and submission mapping |
| `modules/convergence_workflow/results/fe110_true_facet_thickness_20260628.csv` | reviewed force, structure, and surface-excess results for jobs `9554558-9554562` |
| `modules/catalysis_data_retrieval/outputs/20260628_fe110_database_layers/` | whitelist-validated Catalysis-Hub Fe(110) layer-count audit and hybrid retrieval output |
| `modules/catalysis_data_retrieval/outputs/20260628_alpha_fe_bulk_kmesh/` | whitelist-validated NOMAD pure-Fe2 bcc structure/k-mesh evidence used for the `c_fe` bulk preparation |
| `modules/catalysis_data_retrieval/outputs/20260629_h2o_gas/` | whitelist-validated NOMAD isolated H2O VASP/PBE structure and handoff for job `9558015` |
| `modules/fe_convergence_baseline/` | valid alpha-Fe bulk package |
| `calculations/alpha_fe_bulk_c_fe_20260629/` | alpha-Fe bulk pre-submission provenance and remote input hashes for `sunboquan-codex:~/sbq/c_fe` |
| `calculations/true_fe110_clean_20260629/` | reviewed input snapshot for the five-layer 3x3 true Fe(110) clean slab under `sunboquan-codex:~/sbq/Fe110/fe110` |
| `calculations/fe110_clean_static_v2_20260704/` | replacement five-layer Fe(110) `5x5x1` matched final-static inputs |
| `calculations/fe110_step12a_registry_backfill_20260828/` | compact remote audit, hash-bound registry batch/plan/apply receipts, and provenance for 23 missing Step 12A records plus three TS status corrections |
| `calculations/fe110_step12a_gas_references_20260828/` | CO/H/O/OH/C gas-reference inputs, returned VASP evidence, OH incomplete-output recovery, hash-bound registry receipts, and the accepted 19-energy Step 12A batch |
| `outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx` | canonical eight-column adsorption workbook; H contains the 19 receipt-backed Step 12A electronic adsorption energies |
| `data/registry_promotion_receipts/step12a-*-eads-excel-20260828.json` | 19 immutable registry-to-Excel receipts for the unique Step 12A rows |
| `data/backups/课题一吸附_最终_before_step12a_eads_promotion_20260828.xlsx` | safety backup before replacing legacy same-species relative values with formal Eads |
| `data/backups/project_registry_before_step12a_excel_promotion_20260828.sqlite3` | SQLite backup immediately before the 19 Excel promotions and status-history additions |
| `calculations/fe110_c2_coads_pilot_20260714/` | five submitted C+O/C2/C2O/C2+O `NSW=300` relaxation inputs and candidate manifest; jobs `9622455-9622459` |
| `calculations/fe110_c2_coads_missing_20260714/` | six deduplicated missing-only C+O/C2/C2O/C2+O `NSW=300` relaxation inputs and candidate manifest; jobs `9622460-9622465` |
| `calculations/fe110_care8_isomers_20260716/rebuilt/` | two candidate-08 `[C]O[CH][CH]` rebuild input folders; `NSW=80` jobs `9629858-9629859` |
| `modules/catalysis_data_retrieval/outputs/20260714_fe110_c2_coads/` | whitelist CCO/CO-dissociation retrieval records, hybrid ranking, and transferability review |
| `outputs/aqcat25_handoff_test_20260718_cpluso/` | first work-to-MZ73-to-work AQCat25 adsorption handoff artifacts; GPU job `732`, no VASP submission |
| `outputs/aqcat25_fe45_calibration_v1/` | 13 compatible Fe45 VASP labels, exact structures, AQCat25 predictions, empirical force gate, and jobs `733-734` exit evidence |
| `outputs/aqcat25_species_smoke_v2/` | v2 H2-derived and CH3O work-MZ73-work handoffs; GPU jobs `735-736`, no VASP submission |
| `data/` | registry schema/readme; generated SQLite files remain ignored |
| `scripts/adsorption/backfill_step12a_registry.py` | read-only remote Step 12A evidence audit and deterministic registry-batch builder; never submits calculations |
| `scripts/adsorption/build_gas_step12a_references.py` | locked 20 A/Gamma gas-reference builder for CO, H, O, OH, and C with species-appropriate spin branches |
| `scripts/adsorption/preflight_gas_references.py` | gas-reference method, spin, cell, k-point, POTCAR-order, and job-script preflight |
| `scripts/adsorption/finalize_step12a_gas_references.py` | raw-output acceptance gate and hash-bound registry batch for six references and 19 unique Step 12A adsorption energies |

Superseded NEB runs and imported packages are under `archive/`; they are not current command or method authorities.

## Historical Material

| Path | Purpose |
|---|---|
| `reports/` | explicitly requested or reviewed concise deliverables; policy in `reports/README.md` |
| `archive/` | one-off, superseded, downloaded, or historical artifacts |
| `archive/imported_packages/` | user-supplied source packages retained unchanged |
| `modules/memory_migration/` | controlled memory-migration provenance |
| `docs/07_MEMORY_INDEX.md` | migration index |
| `docs/08_HISTORICAL_RESULTS.md` | durable historical results and lessons |
| `docs/13_AGENT_ERROR_REFLECTION.md` | concise agent/process lessons |

Embedded commands in these locations are non-authoritative unless `tasks/current_task.md` explicitly promotes them.

## Exclusions

`.gitignore` excludes licensed `POTCAR`, credentials, VASP runtime output, generated databases/caches, temporary diagnostics, and large local source/model data. Do not force-add excluded material.
# Adsorption pre-screen

- `configs/adsmind_lite/iron_fts_prescreen.yaml`: machine-readable Fe(110)
  Fischer-Tropsch motif ranking and reviewed calibration profiles.
- `scripts/adsmind_lite/fts_prescreen.py`: exact-profile and feature-based FTS
  candidate ranking helpers; never submits calculations.
- `skills/fe110-adsorbate-pilot-builder/references/iron-fts-prescreen.md`:
  concise human-readable coordination-demand decision rules.

## Reviewed local Sella search

- `scripts/matris_sella_local_peak.py`: package, preflight and execute one
  reviewed local peak from a saved MatRIS path without another NEB run.
- `scripts/ml_candidate_source.py`: shared immutable candidate-path identity
  and geometry checks used by local Sella and active-learning handoff.
- `modules/transition_state_search/SELLA_LOCAL_PEAK.md`: exact request/review
  fields, deployment, bounded execution, return and validation limitations.
