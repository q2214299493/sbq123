# Refactor Changeset

## Boundary

Only sections A, B, and C are review materials for this condition-closure changeset.
Sections D, E, and F are explicitly excluded. Nothing has been staged, committed,
pushed, deleted, moved, or copied from calculation/runtime trees.

## A. Refactor and condition-closure code

- `scripts/artifact_io.py`
- `scripts/convergence/common.py`
- `scripts/convergence/setup_alpha_fe_bulk_smearing.py`
- `scripts/neb_agent/remote_monitor.py`
- `scripts/neb_agent/submission.py`
- `scripts/scheduler_evidence.py`
- `scripts/ts_strategy_engine/execution_decision.py`
- `scripts/ts_strategy_engine/execution_gate.py`

## B. Regression tests

- `tests/test_alpha_fe_bulk_submission.py`
- `tests/test_artifact_io.py`
- `tests/test_config_boundaries.py`
- `tests/test_execution_gate_compatibility.py`
- `tests/test_external_command_boundaries.py`
- `tests/test_neb_remote_monitor.py`
- `tests/test_repository_contracts.py` (only the explicit `artifacts/refactor_changeset` contract hunks)
- `tests/test_neb_submission.py`

## C. Documentation and review evidence

- `README.md`
- `PROJECT_AUDIT.md`
- `REFACTOR_PLAN.md`
- `ARCHITECTURE.md`
- `DEPRECATED_CODE.md`
- `REFACTOR_REPORT.md`
- `VERIFICATION_REPORT.md`
- `SUBMISSION_RECOVERY.md`
- `UNTRACKED_FILE_INVENTORY.md`
- `CHANGESET_MANIFEST.md`
- `REFACTOR_CHANGESET.md`
- `CONDITION_CLOSURE_REPORT.md`
- `docs/14_CODE_ARCHITECTURE_GUIDE.md`
- `modules/transition_state_search/README.md`
- `scripts/README.md`

Generated review artifacts:

- `artifacts/refactor_changeset/tracked_changes.patch`
- `artifacts/refactor_changeset/untracked_source_manifest.txt`
- `artifacts/refactor_changeset/changeset_sha256.txt`

## D. Pre-existing unrelated tracked changes -- excluded

Count: **57** paths contain excluded tracked changes. `tests/test_repository_contracts.py`
is mixed provenance: only its explicit `artifacts/refactor_changeset` hunks are in B;
its other pre-existing hunks remain excluded. The other paths were present in the
frozen worktree and are not part of the independently verified allowlist:

- `AGENTS.md`
- `calculations/fe110_co_dissociation_neb_20260718/.research/tasks/01_co_dissociation.yaml`
- `calculations/fe110_co_dissociation_neb_20260718/contract/reaction.yaml`
- `calculations/fe110_co_dissociation_neb_20260718/workflow.md`
- `configs/aqcat25_ts_active_learning.schema.json`
- `configs/aqcat25_ts_active_learning.yaml`
- `configs/aqcat25_ts_domain_gate.yaml`
- `configs/neb_agent/default_thresholds.yaml`
- `configs/true_fe110_production.yaml`
- `docs/00_PROJECT_BRIEF.md`
- `docs/01_METHOD_PROTOCOL.md`
- `docs/02_CURRENT_STATE.md`
- `docs/03_DECISIONS_LOG.md`
- `docs/04_ERROR_LOG.md`
- `docs/05_FILE_INDEX.md`
- `docs/06_MODULE_MAP.md`
- `docs/10_TS_VALIDATION_PROTOCOL.md`
- `docs/13_WORK_HANDOFF.md`
- `modules/convergence_workflow/README.md`
- `modules/transition_state_search/strategy_rules.md`
- `scripts/aqcat25_ts_schema.py`
- `scripts/neb_agent/analyze_neb_outputs.py`
- `scripts/neb_agent/check_endpoints.py`
- `scripts/neb_agent/check_neb_job.sh`
- `scripts/neb_agent/diagnose_path_geometry.py`
- `scripts/neb_agent/generate_path.py`
- `scripts/neb_agent/retrieval_prior_adapter.py`
- `scripts/neb_agent/utils_report.py`
- `scripts/neb_agent/utils_vasp.py`
- `scripts/ts_strategy_engine/active_learning.py`
- `scripts/ts_strategy_engine/active_learning_cli.py`
- `scripts/ts_strategy_engine/active_learning_common.py`
- `scripts/ts_strategy_engine/active_learning_domain.py`
- `scripts/ts_strategy_engine/active_learning_label.py`
- `scripts/ts_strategy_engine/active_learning_scheduler.py`
- `scripts/ts_strategy_engine/active_learning_training.py`
- `scripts/ts_strategy_engine/cli.py`
- `scripts/ts_strategy_engine/connectivity_evidence.py`
- `scripts/ts_strategy_engine/contract.py`
- `scripts/ts_strategy_engine/dimer_analysis.py`
- `scripts/ts_strategy_engine/evidence.py`
- `scripts/ts_strategy_engine/handoff.py`
- `scripts/ts_strategy_engine/strategy.py`
- `scripts/ts_strategy_engine/workflow.py`
- `scripts/ts_validation/analyze_vfa.py`
- `scripts/ts_validation/connectivity.py`
- `scripts/ts_validation/prepare_vfa_from_ts_image.py`
- `scripts/vasp_inputs.py`
- `scripts/vasp_result_gate.py`
- `tasks/backlog.md`
- `tasks/current_task.md`
- `tests/test_aqcat25_ts_active_learning.py`
- `tests/test_neb_geometry.py`
- `tests/test_repository_contracts.py`
- `tests/test_ts_handoff.py`
- `tests/test_ts_strategy_engine.py`
- `tests/test_ts_validation.py`

## E. Unknown or unrelated untracked provenance -- excluded

Count: **23**. These non-runtime paths require a
separate provenance review and are not assumed to belong to this refactor:

- `AGENT_RULE_TS_ENDPOINT.md`
- `configs/neb_path_quality_control_v2.yaml`
- `configs/structure_purpose_routing.yaml`
- `configs/ts_connectivity_gate.yaml`
- `modules/calculation_registry/migrations/001_ts_endpoint_records.sql`
- `modules/calculation_registry/migrations/001_ts_endpoint_records_rollback.sql`
- `modules/structure_purpose_manager.py`
- `modules/ts_endpoint_database.py`
- `modules/ts_endpoint_generator.py`
- `modules/ts_endpoint_validator.py`
- `scripts/neb_agent/magnetic_continuity.py`
- `scripts/neb_agent/path_quality_cli.py`
- `scripts/neb_agent/path_quality_control.py`
- `scripts/neb_agent/pilot_validation.py`
- `scripts/ts_strategy_engine/active_learning_calibration.py`
- `scripts/ts_strategy_engine/execution_evidence.py`
- `scripts/ts_strategy_engine/execution_gate_cli.py`
- `tests/test_neb_execution_gate.py`
- `tests/test_neb_path_quality_control.py`
- `tests/test_neb_pilot_validation.py`
- `tests/test_structure_purpose_manager.py`
- `tests/test_vasp_inputs.py`
- `tests/test_vasp_result_gate.py`

## F. Calculation/runtime/generated material -- excluded

Count: **474**. The complete paths, classifications, sizes,
and hashes are in `UNTRACKED_FILE_INVENTORY.md`. They are retained in place
and are not copied into the review artifacts.

## Mechanical isolation rule

`tracked_changes.patch` contains full diffs for single-purpose tracked A/B/C files and only the named artifact-contract hunks from the mixed-provenance repository test.
`untracked_source_manifest.txt` contains path metadata and SHA-256 values only;
it does not copy file contents. The hash file binds these two artifacts and all
listed A/B/C files. No wildcard staging command was used.
