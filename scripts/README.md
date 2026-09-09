# Script Layout

Current executable code lives only under `scripts/` or a repository-backed skill.

- `document_governance.py`: read-only document classification, wording and local-link checks; the policy owner is [document governance](../docs/DOCUMENT_GOVERNANCE.md). It has no scientific acceptance authority.
- `generate_capability_readiness.py`: deterministic derived Markdown/JSON views of the module map and its explicit evidence annotations. It never queries production or upgrades scientific maturity from software tests.

- `ts_strategy_engine/`: the single V3 entry for contract/fingerprint gates,
  template retrieval, path review, NEB decisions, DIMER, frequency handoff,
  compatible final-energy barriers, and learning records. Its CLI, orchestration,
  domain rules, path evidence, registry evidence, and template storage are
  separate layers; see the owning module README.
- `ts_strategy_engine/execution_decision.py`: pure Schema-v2 decision-document
  construction. It has no I/O and cannot authorize an action; the sole
  authority remains `execution_gate.py`.
- `ts_strategy_engine/execution_evidence.py`: current evidence and authorization
  validation, including applying the validated scope to a decision through
  `bind_execution`. The gate orchestrates this boundary; it is not an executor.
- `neb_agent/`: internal endpoint/path generation, geometry, analysis, and
  hash-bound submission backend. These tools cannot decide an action;
  `submission.py` enforces the authoritative gate decision.
- `neb_agent/path_quality_control.py`: the sole scientific path-quality
  evaluator. `path_quality_service.py` is application orchestration shared by
  the thin standalone CLI, unified workflow, and pilot adapter; it owns no
  thresholds, status priority, reason-code policy, or execution authority.
- `neb_agent/submission.py`: the only gate-enforcing NEB submission/stop
  executor. It records recoverable submission attempts, treats timeout and
  unknown scheduler state as non-success, and follows `SUBMISSION_RECOVERY.md`
  before any retry.
- `neb_agent/utils_vasp.py`: authoritative streaming OUTCAR/OSZICAR electronic
  cycle parsing. Latest started and completed cycles are distinct; a newer
  incomplete cycle cannot inherit an older cycle's convergence.
- `vasp_result_gate.py`: authoritative string-valued INCAR reader and final
  electronic-state interpretation. INCAR accepts semicolons, comments, case
  variants and repeated identical tags; conflicting duplicate assignments fail.
  `final_scf_status` preserves its six-field public summary; `include_cycles=True`
  exposes explicit completeness and final-cycle evidence. Consumers with parsed
  output use `final_scf_state` instead of parsing twice. Legacy remote backfill
  sends this same parser source in memory, without a maintained remote copy.
- `scientific_validation.py`: shared finite scalar and physical-range validation;
  it defines no scientific thresholds or acceptance policies.
- `ts_strategy_engine/contract.py`: one semantic validator for raw and normalized
  contracts. Hash verification proves identity and never skips semantic checks.
- `ts_strategy_engine/fingerprint.py`: separate element-labelled chemical events,
  structural similarity and exact reusable-result identity. Planning obtains
  species from validated endpoint structures; optional contract `atom_symbols`
  must agree with them. The legacy `fingerprint_id` remains a path-binding key,
  not sufficient evidence for scientific result reuse. `strategy.py` consumes
  these events and the existing family definitions.
- `convergence/`: reusable convergence-campaign setup and summary tools.
- `adsorption/`: reusable clean-slab site generation and anchor-based adsorbate placement.
- `adsmind_lite/`: compact CLIs plus focused site detection, candidate generation,
  relaxed-state analysis, deduplication, and export modules. `core.py` is only a
  backward-compatible import facade.
- `ts_validation/`: partial-Hessian preparation, frequency evidence parsers,
  and optional hash-bound VASP bidirectional-connectivity diagnostics;
  the public workflow entry remains `scripts.ts_strategy_engine.cli`.
- `aqcat25_handoff.py`: Draft 2020-12 schema and bound-file validation for
  work-to-GPU and GPU-to-work AQCat25 transfers.
- `aqcat25_calibration.py`: compatible VASP final-force extraction and
  empirical AQCat25 force-error calibration.
- `ts_strategy_engine/active_learning_cli.py`: active-learning commands inside
  the unified TS CLI; `aqcat25_ts_active_learning.py` is a compatibility
  wrapper only. New runs use `python -m scripts.ts_strategy_engine.cli
  active-learning start`.
- `vasp_inputs.py`: builds active-learning VASP labels from the production
  parameter profile, without a second INCAR/KPOINTS configuration.
- `vasp_lsf.py` and `templates/sunboquan_vasp.lsf`: render the one shared
  Sunboquan LSF launcher; input builders do not embed scheduler shell code.
- `artifact_io.py`: shared atomic JSON and chunked SHA-256 helpers.
- `state_manager/`: immutable repository-state events, read-only freshness and
  obsolete-item audit, hash-bound proposals, Codex/user review records, and
  deterministic managed-view projection. Use the `repo-state` entry point;
  it never queries remote schedulers or performs scientific actions.
- `registry_excel_promotion.py`: request/plan/apply entry for moving accepted
  registry records into existing thesis workbooks. It is hash-bound and writes
  a SQLite-plus-JSON receipt; `registry_excel_writer.mjs` is its sole workbook
  writer and uses `@oai/artifact-tool`.
- `aqcat25_ts_schema.py`: unified Draft 2020-12 validation for active-learning
  state, scheduler evidence, force prediction, training, and fine-tune records.
- `aqcat25_ts_force_prediction.py`: MZ73 exact-structure AQCat25 force
  prediction for comparison with one accepted VASP force label.
- `aqcat25_ts_training_data.py`: build force-only TS-plus-replay training data
  and a disjoint adsorption regression database.
- `aqcat25_ts_checkpoint_validation.py`: load a fine-tuned checkpoint and reject
  non-finite predictions or held-out adsorption regression failures.
- `matris_training_exclusions.py`: build a hash-bound held-out exclusion
  manifest and reject exact-structure or rounded-geometry overlap before any
  MatRIS optimizer is constructed.
  It also owns shared dataset split isolation by calculation, source row,
  declared reaction, and permutation/translation/rotation-invariant periodic
  structure descriptors. The legacy geometry hash remains the exact artifact
  binding; the added descriptor is conservative exclusion evidence, never a
  scientific-result reuse key. Five-decimal precision is unchanged. Homometric
  descriptor collisions block splits and require review.
- `matris_training_data.py`: shared MatRIS/AQCat25 label-source validation and
  hydration. It reuses existing VASP acceptance owners, verifies current source
  files and row identities, and derives `PARSED`/`VALIDATED` state. Package and
  database builders apply the shared split check before `TRAINING_ELIGIBLE`;
  completed MatRIS receipts bind `USED_IN_MODEL` items to the output checkpoint.
  Caller-supplied eligibility flags never bypass validation. Old label caches
  without source files or calculation identity require reviewed refresh.
- `prediction_provenance.py`: typed ML prediction metadata and validation for
  CARE/GAME-Net imports and MatRIS outputs. Predictions require model/version,
  input fingerprint, source reference, timestamp, uncertainty and explicit
  training-split metadata (null when unavailable). Unknown uncertainty needs a
  reason and remains uncalibrated; it is never converted to zero uncertainty.
  CARE CSV imports carry the JSON `prediction_provenance` column. AQCat25 and
  dual-model producers emit the same candidate metadata without changing their
  standalone inference dependencies or wrapper lifecycle. Shared training-data
  preflight runs with the repository package and accessible bound source files;
  a relocated deployment must stage those dependencies and source bindings.
- `prepare_matris_finetune_request.py`: verify the active-learning decision,
  VASP label/assessment bindings, policy, base checkpoint, and held-out
  exclusion hash; write a non-executable request only after local preflight
  passes, leaving fine-tuning authorization as a separate action.
- `prepare_matris_replay_finetune_package.py`: bind current/prior TS labels,
  adsorption replay and retention labels, and frozen held-out TS labels into a
  leak-checked, review-only MatRIS energy-force fine-tuning package.
- `matris_energy_force_finetune.py`: preflight that package, run a local loss
  and checkpoint smoke test without MatRIS, or execute authorized MatRIS
  energy-force replay training and emit a non-promoted checkpoint candidate.
  A review request may require per-epoch checkpointing with strict adsorption
  retention selection; frozen TS held-out labels remain final-evaluation only.
- `offline_mlip_fusion_feasibility.py`: existing-label-only, reaction-blocked
  MatRIS/AQCat25 comparison with a convex linear baseline and a low-capacity
  conservative pair-RBF meta-model. It binds inputs and implementation hashes,
  supports fold-level resume, and cannot run inference, submit calculations,
  modify checkpoints, or promote a model.
- `aqcat25_ts_finetune_job.sh`: reviewable MZ73 force-only fine-tuning wrapper
  with checkpoint and producer-exit evidence; it never runs VASP.
- `aqcat25_gpu_job.sh`: MZ73 adsorption runner with mandatory producer
  exit-code evidence; it never submits VASP.
- `aqcat25_ml_neb.py`: manifest-driven AQCat25 ASE ordinary ML-NEB and
  conditionally enabled ML-CI-NEB executor. It writes every image, predicted
  energy/physical force, projected NEB force, spring force, reaction progress,
  adjacent RMSD, restart state, adaptive VASP-label suggestions, and a
  review-required path manifest without submitting VASP.
- `aqcat25_ml_neb_job.sh`: MZ73 Slurm wrapper for the complete-path executor;
  it validates the source handoff and preserves success/failure producer
  evidence.
- `ts_strategy_engine/ml_neb_path.py`: work-side returned-path/hash validator
  and accepted-review finalizer for the GPU Dimer-parent manifest.
- `aqcat25_mz73_env.sh`: the shared AQCat25 Python/cache environment used by
  all MZ73 GPU wrappers.
- `git_snapshot.ps1` and `init_registry.py`: repository-wide infrastructure entry points.
- `jsonl_io.py`: dependency-free JSONL object loading shared across scientific modules and repository-backed skills.

Commands and scientific gates remain owned by the relevant module README. One-off or superseded scripts belong under `archive/`, not at repository root.

### B4 registry/state ownership

- `registry_write.py`: public batch API/CLI facade; no embedded SQL.
- `registry_mutations.py`: complete batch planning, one SQL mutation path and atomic apply.
- `registry_transactions.py`: snapshot/approval bindings and durable transaction receipts.
- `registry_compatibility.py`: immutable compatibility revisions and original calculation bindings.
- `registry_acceptance.py`: persistence adapter consuming B3 evidence and existing VASP/scientific owners.
- `registry_schema.py`: explicit versioned migrations, validation and guarded rollback.
- `state_manager/job_lifecycle.py`: recorded job/workflow transition rules (not execution authority).
- `state_manager/application_log.py`: durable attempts/reservation for the existing state projection executor.

The existing `ts_strategy_engine.evidence.register_calculation_compatibility` API
is a thin compatibility facade. Scientific validation and execution remain in
their original owners. Schema initialization, batch application and Excel promotion
are explicit operations; merely opening a registry performs no migration.

## Current B5 ownership boundaries

`registry_connection.py` is the sole generic SQLite connection owner: current-schema
checks, foreign keys, commit/rollback/close and UTC timestamps. It depends only on
schema/infrastructure. New generic callers import it directly. The historical
`ts_strategy_engine.registry` names remain identity-preserving re-exports; its
final-energy constants belong to `ts_validation/barrier_values.py`, and its
compatibility hash helper belongs to `registry_compatibility.py`.

`registry_mutations.py` is application orchestration with one mutation path;
`registry_acceptance.py` and `registry_excel_promotion.py` are scientific/persistence
application adapters, not shared infrastructure. They may consume domain validation;
the connection/schema/transaction owners may not. Excel promotion consumes the pure
barrier-value validator in `ts_validation/barrier_values.py`, shared with matched
final-energy evidence. `registry_write.py` remains argument/loading/rendering only.

`catalysis_retrieval/records.py` owns whitelist record and embedding validation;
`ranking.py` owns BM25/semantic ranking; `workflow.py` owns request orchestration.
The original skill scripts retain CLI arguments, output/exit behavior and direct
re-exports. AdsMind imports the record owner normally, never a skill CLI at runtime.
Use the installed `catalysis-search` / `catalysis-validate` commands outside a checkout;
legacy skill paths remain repository facades with the same arguments.
Retrieval PASS only describes ranking; transferable evidence and scientific
acceptance remain separate gates. No new scientific capability is implied.

DIMER CLI review binding is applied by
`ts_strategy_engine.handoff.prepare_reviewed_dimer_handoff`. Learning-attempt
preflight is orchestrated by `ts_strategy_engine.workflow.start_vasp_attempt`;
it records an attempt and never submits a job. TS-workdir candidate discovery and
initialization belong to `active_learning_state.py`. The existing CLI functions
only translate arguments and render these results.

State task phases, transitions and payload interpretation belong to
`state_manager/models.py`; the event store and lifecycle application consume them
without importing each other. State timestamps retain their distinct serialized
format; they are not replaced by registry timestamps.

System support is explicit: `vasp_inputs.build_fe110_*` uses the reviewed
`true_fe110_production.yaml` profile; site detection uses
`configs/adsmind_lite/surfaces.yaml` and `site_rules.yaml`. Unknown families raise
an error; unrecognized metallic surfaces without explicit site labels return
`NEEDS_REVIEW` and no sites. General TS contract parsing does not imply support for
arbitrary catalysts. Backend restrictions remain in `execution_backends.yaml`.
See `reports/refactor_audit/B5_completion_report.md` for capability contracts and
`B5_dependency_inventory.md` for the maintained source classification.

## Release resource boundary

`runtime_resources.py` distinguishes reviewed installed resources from explicit
repository context. `release_build.py` copies only the enumerated originals in
`configs/release_resources.json` into build output. No scientific rules live in
these packaging modules. `release_smoke.py` exercises only synthetic local fixtures;
`release_environment.py` records installed dependencies/interfaces, and
`validate_release.py` builds and checks actual clean wheel/editable installations.
See [installation contract](../docs/INSTALLATION.md). Standalone remote facades
retain their existing resource inputs; this refactor does not deploy them.
