# B1 Completion Report — B1.1 CI and GPU lifecycle closure

Repository: C:/Users/86177/Desktop/work (Git worktree used for clean release validation).
GitHub: https://github.com/q2214299493/sbq123
Branch: codex/b1-execution-lifecycle
B1.1 baseline: 1ec8f3e787fd52353fa70419a206d764c07ae13a
Date: 2026-09-09, Asia/Shanghai.

## Scope and status

B1-01 through B1-05 are closed within the tested execution-safety scope. B2 was not started. Final full-suite and focused-suite validation both exited 0; production-only limitations remain explicit below.

The baseline GitHub run failed with 608 passed and two failures: the 160-line gate boundary contract and root-level audit-output clutter. The follow-up also closes the previously deferred B1-05 wrapper preamble problem. The existing architecture contracts and root allowlist were not changed.

| B0 issue | B1.1 closure status and disposition |
| --- | --- |
| B1-01 — Authorization/evidence binding | Closed. Original scoped authorization, canonical workdir identity, action/target, bundle/evidence/source hashes and POTCAR binding retained. Gate validation is unchanged. |
| B1-02 — Paths and digests | Closed. Existing VASP checks retained; GPU wrappers now validate canonical containment, helper/input/output/runtime/cache/vendor/checkpoint paths where used, and supplied source digests. |
| B1-03 — Submission race and recovery | Closed. Existing immutable local/remote reservations, at-most-one cooperating submitter, retained receipts and UNKNOWN_NEEDS_RECONCILIATION recovery retained. No automatic resubmission. |
| B1-04 — Upload integrity | Closed. The same complete remote manifest verification immediately precedes bsub for new and reused uploads. No change to this executor in B1.1. |
| B1-05 — GPU wrapper preamble failures | Closed. Explicit fail-closed bootstrap and wrapper records now cover early setup and later execution/receipt failures across the nine static wrappers and generated MatRIS wrapper. |

## Exact B1.1 task-owned files

| File | Change |
| --- | --- |
| scripts/ts_strategy_engine/execution_gate.py | Import decision projection from its owner; remain a 149-line authoritative orchestration/validation boundary. |
| scripts/ts_strategy_engine/execution_decision.py | Own ScientificReadiness and the unchanged bind_execution projection that assembles decision metadata and execution flags. |
| scripts/ts_strategy_engine/execution_path_rules.py | Preserve ScientificReadiness through a compatibility re-export; scientific rules unchanged. |
| scripts/aqcat25_mz73_env.sh | Shared canonical path and digest checks, explicitly installed lifecycle traps, dependency-free failure records and validated environment setup. |
| scripts/aqcat25_gpu_job.sh | Install protection before required inputs; canonical handoff/calibration/output checks and fail-closed setup. |
| scripts/aqcat25_ml_neb_job.sh | Early protection; canonical handoff/checkpoint/output checks; retain driver-owned scientific success artifacts. |
| scripts/aqcat25_ts_finetune_job.sh | Early protection; canonical manifest/base-checkpoint checks and digest validation; preserve training parameters. |
| scripts/aqcat25_ts_force_prediction_batch_job.sh | Early protection and canonical batch/output validation. |
| scripts/dual_model_ml_neb_job.sh | Early protection, canonical request/vendor/checkpoint/output checks, vendor failures recorded. |
| scripts/dual_model_ts_force_prediction_batch_job.sh | Early protection and canonical runtime/vendor/checkpoint/output checks. |
| scripts/dual_model_ts_force_prediction_batch_job_v2.sh | Same protection before setup/vendor/artifact-writer/GPU-availability preflight; existing resource thresholds preserved. |
| scripts/matris_finetune_speed_benchmark_job.sh | Early protection, MZ73 guard, canonical paths/cache checks and Python/vendor/output preflight. |
| scripts/mlip_same_structure_benchmark_job.sh | Early protection, MZ73 guard and canonical benchmark/runtime/checkpoint/vendor/output checks; backend whitelist retained. |
| scripts/prepare_matris_remote_finetune_bundle.py | Render the existing MatRIS job with the shared protection; ship/hash-bind the helper in the bundle; validate remote path spelling and quote shell values. No alternate executor. |
| tests/test_gpu_execution_lifecycle.py | 137 CPU-only shell cases and regression checks for the ten wrapper surfaces, including generated-script rendering. |
| reports/refactor_audit/full_coverage_report.md | Relocated from refactor_audit/full_coverage_report.md; updated task-owned location references and linked this closure report. B0 findings remain a historical snapshot. |
| reports/refactor_audit/B1_completion_report.md | Relocated from refactor_audit/B1_completion_report.md and updated for B1.1. |

No AGENTS.md, architecture-test limit, root allowlist, scientific threshold, VASP parameter, TS acceptance rule, production database, calculation output, POTCAR or real model-weight file was changed in B1.1. Unrelated dirty-worktree changes were excluded from publication and validation.

## Thin gate and compatibility

ScientificReadiness is now a decision data object owned by execution_decision.py and re-exported through execution_path_rules.py. ExecutionAuthorization and EvidenceBinding retain their existing owner and implementation in execution_evidence.py. The gate delegates only output projection to the decision owner; it still selects the priority-ordered result, recomputes decisions and enforces actions.

AST comparisons against the B1 baseline confirmed unchanged implementations of decide_execution, require_action, validate_decision, blocking_decision, progress_decision, require_execution_authorization and validated_ts. The moved projection has the same AST body, with only its function name changed from _bind_execution to bind_execution. The original public gate signatures, action names, scientific eligibility and source-binding behavior remain intact. There is one authorization validator and one VASP submission executor.

The existing test_ts_engine_layers_do_not_recombine contract remains <=160 lines; the gate is 149 lines. No line-limit increase, mechanical compression or validation removal was used. The existing test_root_contains_no_executable_or_download_clutter contract remains unchanged. Both B0/B1 reports now reside under the already-approved reports/ area.

## GPU execution failure contract

Every wrapper installs a dependency-free bootstrap guard before resolving its helper or expanding required environment variables. The helper is resolved canonically within /home/sbq/sbq before sourcing. If it is missing or cannot be resolved, the guard emits a failed execution JSON record to stderr and attempts a write-once bootstrap record in the physical working directory when that directory is inside the boundary.

Once loaded, aqcat25_mz73_env.sh owns the shared lifecycle:

1. Install EXIT and catchable-signal handling explicitly for the job; loading the environment helper alone installs no job traps.
2. Require the existing MZ73 backend and a valid Slurm job ID before execution.
3. Validate canonical containment before setup or payload invocation. A textual prefix cannot hide a parent traversal or symlink escape.
4. Refuse missing/non-executable Python, missing vendor/support files, setup/output creation errors and invalid supplied digests before the payload where applicable.
5. On nonzero exit, emit a JSON record with status=failed, nonzero exit_code and evidence_class=producer_process_only_not_scheduler_accounting. Reporting does not depend on the ML Python, an imported artifact writer or initialized caches.
6. Prefer the contract's EXIT_RECORD path when available; otherwise use a unique producer_exit_record.failure.<job>.<pid>.json beside outputs or in the boundary-contained physical working directory. noclobber prevents overwriting earlier evidence.
7. Preserve the original nonzero exit status. The existing normal producer/receipt writers retain their formats and success ownership. Failed receipt writing can no longer be hidden by a later exit 0 in the MatRIS wrappers.

If no allowed directory is writable, stderr still carries the failed execution record for the scheduler log. The wrapper does not claim that a file exists, infer scheduler EXIT/DONE, or claim scientific acceptance. A consumer lacking its required current file/hash evidence must remain UNKNOWN; the failure log is not a substitute for accepted scientific results.

The small bootstrap segment is mirrored from the existing environment owner's marked block because it must operate even when that file is absent. A test checks every static/generated wrapper against that exact block. All post-bootstrap validation and failure serialization are shared; there is no second maintained canonical-path validator per wrapper.

The generated MatRIS bundle includes the shared helper in its bound code manifest. Existing deployed static wrappers must be updated together with the matching environment helper. An incompatible/missing helper fails closed.

## Validation

Validation was performed on the clean Git worktree for the specified GitHub branch, based on 1ec8f3e, not against unrelated unpublished modifications in the desktop checkout. Local runtime: Windows, Python 3.13.9 and Git Bash. GitHub's workflow uses Ubuntu and Python 3.11. Both use the repository's unmodified validation commands.

### Complete repository validation — exact CI commands

    python -m ruff check scripts modules tests
    python -m pytest -o addopts= -q

Final Ruff result: All checks passed, exit 0.
Final complete pytest result: 747 passed in 221.70s (0:03:41), exit 0.

Intermediate results were superseded by the final runs above and below, after adding standalone-helper compatibility and generated-MatRIS cache-containment coverage.

### Focused B1 regression

    python -m pytest -o addopts= -q tests/test_artifact_io.py tests/test_execution_lifecycle.py tests/test_gpu_execution_lifecycle.py tests/test_neb_submission.py tests/test_neb_execution_gate.py tests/test_execution_gate_compatibility.py tests/test_execution_backends.py tests/test_neb_path_quality_control.py tests/test_ts_handoff.py tests/test_ts_strategy_engine.py tests/test_ts_strategy_learning.py tests/test_code_structure.py tests/test_repository_contracts.py

Final focused result: 353 passed in 141.61s (0:02:21), exit 0.

The focused run covers original B1 reservations, concurrent submitters, hard process death, stale evidence, tampered inputs, new/reused upload verification, POTCAR identity and scoped stop authorization, plus the architecture/root-contract regressions and GPU failure matrix.

New shell evidence covers missing job/input/helper/Python/vendor, output creation failures, malformed digests, traversal and symlink escape, cache escape, missing canonicalizer, payload failure, TERM interruption, receipt-writer failure, preservation of existing records, normal fake-payload paths and side-effect-free standalone helper sourcing. The wrappers themselves and the generated MatRIS shell were parsed with Bash. Fake Python, hostname and GPU-query commands and temporary boundary copies were used; no GPU job, remote submission or scientific computation was launched.

Scoped git diff --check passed. Configurations, data and calculation directories have no B1.1 diff. Reports were inspected for current paths and validation results. State projections were not synchronized because the active scientific task/state is unrelated to this source-only closure.

## Remaining production-only uncertainties

- Real MZ73/Slurm deployment, helper distribution, remote filesystem semantics and installed vendor/Python environments were not exercised. They require a separately authorized deployment check; none was performed here.
- SIGKILL, power loss and total loss of writable storage/log transport cannot be handled by a Bash EXIT trap. Missing terminal evidence remains UNKNOWN and must not authorize retry or scientific acceptance.
- Filesystem containment checks and adjacent submission checks assume cooperating writers. Concurrent privileged filesystem mutation is not an immutable-snapshot guarantee.
- Scheduler acceptance with a lost response still requires human reconciliation. B1 intentionally provides no automatic resubmission, reservation expiry or inference that a missing queue entry means submission never occurred.

B2 remains outside this change. No additional scientific acceptance or production-calculation claim is made.
