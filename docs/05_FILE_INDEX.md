---
document_class: CURRENT_REFERENCE
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: CURRENT_CODE_STATE_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

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

## Fe110 REICO pilot300 proposal — 2026-10-21

- `docs/reviews/fe110_reico_pilot300_20261021/README.md`: scope, staged 300-configuration pilot design, C2/C3 correctness and fully accounted performance review, conditional expansion and execution boundaries.
- `docs/reviews/fe110_reico_pilot300_20261021/pilot_spec.json`: review-only structured draft; no existing runner consumes it and it grants no execution authority.
- `docs/reviews/fe110_reico_pilot300_20261021/source_inventory.json`: SHA256-bound source inventory and actual read-only metadata checks; scientific input files are referenced but not included in the publication bundle.

## Fe110 REICO geometry first step - 2026-10-22

- scripts/adsorption/reico_random_geometry.py: deterministic CPU-only off-equilibrium C/O/H sampling on the hash-bound Fe45 slab,whole-family splits,collision guards,immutable outputs and bounded resume.
- configs/fe110_reico_pilot/geometry_v1.json: pairwise draft distances,coordinate ranges,seed,family budgets and preassigned partitions.
- tests/test_reico_random_geometry.py:19 focused geometry/provenance/resume/failure tests without scientific compute.
- docs/reviews/fe110_reico_geometry_step1_20261022/: review and independent readback facts;99 candidates,one failed family,no GPU/DFT/training.
- calculations/fe110_reico_pilot300_20261022/geometry_v1/: primary-workspace-only raw inputs,299 family artifacts,immutable summaries and preview;not copied into the source-release branch.

## Fe110 REICO six DFT probes - 2026-10-22

- scripts/adsorption/reico_probe_batch.py: six training-family geometry probes and canonical fixed-geometry VASP input preparation;no upload/submission/model call.
- tests/test_reico_probe_batch.py: deterministic composition/geometry selection,heldout exclusion,underfill and invalid-descriptor checks;with existing builder tests16 pass.
- docs/reviews/fe110_reico_probe6_20261022/README.md: actual six jobs,queue snapshot,label-admission and model-comparison boundaries,registry and sync outcome.
- docs/reviews/fe110_reico_probe6_20261022/user_authorization.md: immutable record of the accepted workflow and bounded six-probe scope,referenced by all six execution gates.
- docs/reviews/fe110_reico_probe6_20261022/input_review.json and execution_status.json: numeric input/gate hashes and actual submission/scheduler/registry snapshot;no DFT accuracy claim.
- calculations/fe110_reico_pilot300_20261022/probe6_v1/: local-only six input bundles,source selection,canonical gates/receipts,LSF raw evidence and registry batch/plan/approval/receipt.

## Fe110 REICO six-probe force review - 2026-10-22

- scripts/adsorption/reico_probe_review.py and tests/test_reico_probe_review.py: exact static coordinate/raw-force/SCF/magnetic checks and separately grouped directional/relative-force diagnostics;no scientific-job executor.
- docs/reviews/fe110_reico_probe6_20261022/force_review.md,force_review.json,force_comparison_authorization.md: current results,source hashes,limits and literal user scope. Earlier execution_status.json remains the submission-stage snapshot.
- calculations/fe110_reico_pilot300_20261022/probe6_v1/checks/20261022T084625Z/: local-only raw48-file collection,scheduler evidence,reviewed E/F/moments,12 prediction outputs,device/exit proofs and reviewed completion registry transaction.

## Fe110 REICO six short trajectories - 2026-10-22

- scripts/adsorption/reico_sampling.py and tests/test_reico_sampling.py: bounded sampling scope,geometry/fixed-layer/step guards,per-frame preservation and restart;called only through the native hash-bound runtime.
- archive/fe110_reico_sampling6_20261022/review.py: one-off114-frame return review and six static input preparations;never submits.
- docs/reviews/fe110_reico_sampling6_20261022/: literal authorization,current run/selection evidence and numerical status.
- calculations/fe110_reico_pilot300_20261022/sampling6_v1/: local-only request/producer/device/114rawframe artifacts,113guard-valid frames,six submitted DFT input/gate/receipt bundles (LSF9919076-9919081) and reviewed metadata-only registry transactions.

- archive/fe110_reico_sampling6_20261022/submit.py and tests/test_reico_sampled_submission.py: exact-scope canonical submission binding;new DFT authorization and submission checkpoint in docs/reviews/fe110_reico_sampling6_20261022/.

## Fe110 REICO292 sampling and DFT preparation — 2026-10-22

- scripts/adsorption/reico_sampling.py: separate hash-bound geometry-only source mode,preserving original family partitions without invented DFT references.
- scripts/adsorption/reico_selection.py: geometry-only family selection,periodic/equal-element deduplication,and preserved existing labels.
- archive/fe110_reico_sampling93_20261022/{prepare,review,prepare_labels}.py: exact93-family package,raw-return audit/292selection,and280unsubmitted static inputs. Existing dispatch.py and its original prepare.py import dependency are included for standalone source replay.
- tests/test_reico_unlabeled_sampling.py,test_reico_selection.py,test_reico_prepare_labels.py: scope/source integrity,split isolation,vector-RMSD/permutation checks,static-branch invariants and isolated preparation resume tests.
- docs/reviews/fe110_reico_sampling93_20261022/: user authority,current results and limits;raw/checkpoint/selection/input/registry artifacts are local-only under calculations/fe110_reico_pilot300_20261022/sampling93_v1/.

## Fe110 REICO280 authorized submission checkpoint — 2026-10-23

- archive/fe110_reico_sampling93_20261022/submit.py:exact280scope/source/POTCAR binding,per-job canonical execution gates and bounded submission tranches;successful receipts reused,unknown reservations never retried.
- archive/fe110_reico_sampling93_20261022/submission_review.py:strict full or explicit partial receipt/LSF checkpoints and metadata-only registry plans;never submits or automatically approves a registry plan.
- archive/fe110_reico_sampling93_20261022/inspect_submission_limit.py:read-only Python3.6 remote metadata diagnostic;its broad hash sweep timed out. Successful short bjobs/ps fallback evidence is retained separately.
- tests/test_reico_labels280_submission.py and test_reico_labels280_review.py:scope/source/gate integrity,tranche boundaries,receipt reuse,unknown-state refusal,and truthful partial checkpoints.
- docs/reviews/fe110_reico_sampling93_20261022/{dft_submission_authorization.md,dft_submission_status.json}:literal280job authority and actual204submitted/76outstanding status. execution_status.json links this checkpoint.
- calculations/fe110_reico_pilot300_20261022/sampling93_v1/dft_inputs_v1/:local-only frozen280inputs/gates,204receipts,7protectedunknowns,initial_submission_checkpoint.json,minimal_submission_limit_reconciliation.json,submission_failure_review.json,remaining_submission_plan.json,and reviewed3881INSERT registry transaction.


## Fe110 C3 source recovery — 2026-10-23

- `docs/reviews/fe110_c3_source_recovery_20261023/README.md`: verified recovery of9629858/9629859;both80steps,SCFconverged,but0.860795/0.565336eV/A andCO+C2H2 fragmentation;no stable intact-C3 anchor.
- `calculations/fe110_c3_existing_recovery_20261023/collection_v1/`: immutable remote/local file hashes,original outputs,v2 force-coordinate checks and160-frame diagnostic. No new scientific execution.

## Fe110 C3 targeted input preparation — 2026-10-23

- archive/fe110_c3_targeted_relaxation_20261023/prepare.py:local-only two-source geometry review,canonical screening input generation,custodian and submission-preflight checks;rejects existing output roots.
- scripts/vasp_inputs.py and scripts/adsorption/preflight_fe110_adsorption.py:explicit80step screening and local-moment options plus C3H2O support;production defaults unchanged.
- tests/test_fe110_adsorption_screening.py:stage/budget/physical-method/magnetic-output rejection and unified-gate regressions.
- docs/reviews/fe110_c3_targeted_relaxation_20261023/:review,exact small input snapshots,hash inventory,cost references and validation;no POTCAR contents or actual submission.

## Fe110 stratified training coverage — 2026-10-23

- scripts/adsorption/reico_chemical_environments.py:exact equal-element graph canonicalization,Fe-neighbor counts and joint geometric strata.
- scripts/adsorption/reico_stratified_audit.py and configs/fe110_reico_pilot/stratified_audit_v1.json:read-only training/cache analysis,composition-local SOAP,missing-type representatives and radius sensitivity.
- tests/test_reico_stratified_audit.py:permutation invariance,graph/coordination coupling,composition isolation,reserved-data refusal and cache-only policy.
- archive/fe110_reico_stratified_audit_20261023/verify.py:real-frame SOAP/NumPy/contact/count verification and8example sensitivity check.
- docs/reviews/fe110_reico_stratified_audit_20261023/:review,canonical result snapshots and validation receipts;full1597frame table/cache remain local.

## Fe110 DFT label QC and force coverage — 2026-10-23

- archive/fe110_reico_label_qc_20261023/{collect,review,verify}.py:exactDONE readonly collection,raw-static revalidation,train-only analysis and independent real-pair verification.
- scripts/adsorption/reico_force_coverage.py and configs/fe110_reico_pilot/force_qc_v1.json:raw-force bins,periodic equal-element correspondence and vector force differences;no reserved adaptive analysis or force-based deletion.
- tests/test_reico_force_coverage.py:force/source/partition boundaries and numberedEDIFF-after-energy regression.
- docs/reviews/fe110_reico_label_qc_20261023/:raw-scheduler checkpoint,QCmetadata,training statistics and reproducible validation;raw VASP/forces remain local.

- calculations/fe110_reico_pilot300_20261022/status_lowforce_check_20261023_v1/checkpoint_summary.json:read-only125DONE checkpoint,4incremental staticQC,10_B intactC2H3 source recheck,and458frame historicalC3 force/chemistry search;local runtime evidence,no newDFT.

- docs/reviews/fe110_10b_lowforce_20261023/:six-frameSCF/force/magnetic-tier/full-symmetry isolation review and validation receipts. Local candidate data:calculations/fe110_reico_pilot300_20261022/10b_lowforce_review_20261023_v1/force_supplement.json;existing frozen training packages unchanged.
- archive/fe110_10b_lowforce_20261023/:bounded read-only collector,exact legacy-owner snapshots,and independent force-supplement reviewer;tests/test_10b_lowforce_review.py.

- docs/reviews/fe110_combined_force_package_20261023/:366/78/53data-only package review,16quarantined sources,magnetic tiers,isolation,independent DB/source verification and validation receipts.
- calculations/fe110_reico_pilot300_20261022/combined_force_package_20261023_v2/training_manifest.json:current local force-only data manifest;train/dev DBs and full package_inventory.json colocated. V1is preserved failed summary checkpoint.
- archive/fe110_combined_force_package_20261023/ and configs/fe110_reico_pilot/combined_force_package_v1.json:bounded local assembler/verifier and frozen source configuration;tests/test_combined_force_package.py.

- docs/reviews/fe110_joint_coverage_20261023/:366frame joint force/environment audit,current and conditional missing-type lists,fixed-threshold SOAP comparisons and validation receipts.
- calculations/fe110_reico_pilot300_20261022/joint_coverage_20261023_v3/:local fulltraining/pool environments,1043DFTforcepairs,254newSOAPcache entries,bindings and checkpoints;original366package unchanged.
- scripts/adsorption/reico_joint_coverage.py;archive/fe110_joint_coverage_20261023/;configs/fe110_reico_pilot/joint_coverage_v1.json;tests/test_reico_joint_coverage.py:training-only joint diagnostics,bounded local runner and independent count/SOAP/permutation/conditional verification.

- docs/reviews/fe110_reico_followup_20261024/:19newstaticQC checkpoint,378frame training-only coverage projection,two paused C3sources,two isolated geometrybackups andvalidation receipts.
- calculations/fe110_reico_pilot300_20261022/followup_20261024_v2/:114collectedrawfiles,19QCrows,156combinedlabelrecords,378frame auditview andcandidategeometries;v1retains initialnetwork failure,no sourcepackage mutation.
- archive/fe110_reico_followup_20261024/;configs/fe110_reico_pilot/followup_20261024_v1.json;tests/test_reico_followup_20261024.py:exact receipt-backed collection,resume-safe failed-snapshot guard,nativeQC,isolated auditupdate andreal-label verification.

- docs/reviews/fe110_reico_remaining_20261024/:original-batch and16-case human authorizations,76new-job checkpoint,280logical success receipts,registry/test/evidence digests.
- calculations/fe110_reico_pilot300_20261022/remaining_submission_20261024_v1/:native read-only checkpoints,serial progress,preserved unknown attempts,new16workdirs/gates/receipts,resolution mapping,exact76-job scheduler snapshot and applied registryv2.
- archive/fe110_reico_remaining_20261024/ and tests/test_reico_remaining_submission_20261024.py:bounded original-scope continuation,human-confirmed fresh attempts,idempotency barriers and final verification/registry planning.

- docs/reviews/fe110_completed_label_qc_20261024/:84-label batch QC checkpoint,82PASS/2exceptions,62isolated trainlabels,force ranges,test counts and native evidence hashes.
- calculations/fe110_reico_pilot300_20261022/completed_label_qc_20261024_v1/:five batch receipts,504raw VASP files,per-labelQC,cumulative240labels,62eligible traincandidates,9018comparison isolation and reviewed/applied registry evidence;local only.
- archive/fe110_completed_label_qc_20261024/;configs/fe110_reico_pilot/completed_label_qc_20261024_v1.json;tests/test_completed_label_qc_20261024.py:receipt-directory-aware incremental collection,nativeQC,partition/magnetic quarantine,isolation,verification and registry planning.

- docs/reviews/fe110_joint_update_20261024/:440frame jointcoverage comparison,229classified residual types,68fixedSOAP exceedances,forcebins and independent verification/evidence digests.
- calculations/fe110_reico_pilot300_20261022/joint_update_20261024_v1/:new440auditview,per-joint force tables,229groups,training-poolSOAPscores,cache/input/output bindings and45-label geometry-only conditional projection(excludes2quarantines);local force arrays only.
- archive/fe110_joint_update_20261024/;configs/fe110_reico_pilot/joint_update_20261024_v1.json;tests/test_joint_update_20261024.py:PASS-only merge,bound cache reuse,quarantine-aware gap classification,raw-force andSOAP verification.

- docs/reviews/fe110_train45_review_20261024/:exact45train snapshot,16PASS/isolated labels,13-gap conditional contribution,remaining29and review/test/registry evidence digests.
- calculations/fe110_reico_pilot300_20261022/train45_review_20261024_v1/:original smoke and clean-main bindings,96raw VASP files,16caseQC,cumulative256labels,2557-comparison isolation,candidate contribution and applied registry receipt;local only.
- archive/fe110_train45_review_20261024/;configs/fe110_reico_pilot/train45_review_20261024_v1.json;tests/test_train45_review_20261024.py:exact training-only scope,priority without deletion,nativeQC reuse,isolation,registry planning and dual-checkout real-label verification.Historical process.py remains immutable;active entry is process_main.py.

- docs/reviews/fe110_train29_review_20261024/:exact29job checkpoint,one C3H2O PASSlabel,additional gap contribution,native registry and dual-checkout validation evidence hashes.
- calculations/fe110_reico_pilot300_20261022/train29_review_20261024_v1/:six collected rawfiles,one caseQC,cumulative257records,210-comparison isolation,28remainingjobs and native registry receipts;local only.
- archive/fe110_train29_review_20261024/;configs/fe110_reico_pilot/train29_review_20261024_v1.json;tests/test_train29_review_20261024.py:hash-bound incremental29scope,nativeQC reuse,isolation/conditional contribution,registry planning and real-label replay.

- docs/reviews/fe110_train28_review_20261024/:exact28job checkpoint,fiveC3H2O PASSlabels,four incremental types,registry and dual-checkout validation hashes.
- calculations/fe110_reico_pilot300_20261022/train28_review_20261024_v1/:30rawfiles,fivecaseQC,cumulative262records,1050-comparison isolation,23remainingjobs and native registry receipts;local only.
- archive/fe110_train28_review_20261024/;configs/fe110_reico_pilot/train28_review_20261024_v1.json;tests/test_train28_review_20261024.py:configured receipt-backed recovery,nativeQC,isolation,contribution without double-counting,registry planning and raw-label replay.

- docs/reviews/fe110_final30_qc_20261025/:final30PASS,complete292-label totals,training-only isolation and conditional coverage,registry/validation hashes;no raw force arrays.
- calculations/fe110_reico_pilot300_20261022/final30_qc_20261025_v1/:frozen30DONE snapshot,20/10batch receipts,180rawfiles,30caseQC,292cumulative labels,23isolated traincandidates and native registry receipts;local only.
- archive/fe110_final30_qc_20261025/;configs/fe110_reico_pilot/final30_qc_20261025_v1.json;tests/test_final30_qc_20261025.py:mixed-partition physicalQC,native scientific gates,isolation,conditional contribution,registry planning and30-label replay.

- docs/reviews/fe110_joint_update_20261025/:485frame coverage review,complete189-type residual catalog,fourSOAPoutliers,force-source/magnetic boundaries and verification hashes.
- calculations/fe110_reico_pilot300_20261022/joint_update_20261025_v1/:bound45candidate merge,reused isolation/cache evidence,485auditview,jointforce tables,189nativegroups,1597SOAPscores and dual-checkout verification;local force arrays only.
- archive/fe110_joint_update_20261025/;configs/fe110_reico_pilot/joint_update_20261025_v1.json;tests/test_joint_update_20261025.py:isolated PASS merge,fixed-threshold coverage with native owners,raw-force/magnetic preservation and independent SOAP/count verification.

- docs/reviews/fe110_targeted_shortlist_20261025/:five non-executable source/review proposals,per-object gap and use conditions,geometry table,label-budget boundary and verification hashes.
- calculations/fe110_reico_pilot300_20261022/targeted_shortlist_20261025_v1/:five independent geometry audits,source/geometry binding,910-comparison isolation,shortlist,retained initial path-alias replay failure and dual-checkout verification;no DFT inputs or new labels.
- archive/fe110_targeted_shortlist_20261025/;configs/fe110_reico_pilot/targeted_shortlist_20261025_v1.json;tests/test_targeted_shortlist_20261025.py:labelled target-graph source selection,reserved/magnetic/fragment exclusions and independent POSCAR replay.
