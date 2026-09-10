---
document_class: GENERATED_CURRENT_REPORT
as_of: '2026-09-10T05:24:49.964373+00:00'
as_of_scope: Local software validation of this bounded repair, not live scientific
  observation
source_scope: Publication base plus task-owned files identified by hashes below; synthetic
  execution only
source_version: a24bda4fb82c325bdcc385c9b089a061ddcf7096
source_version_role: Repair base commit; source_files_sha256 binds subsequent task
  changes
source_branch: codex/ac-rerun-b1-001-execution-closure
evidence_kind: DERIVED_SOFTWARE_AUDIT
production_schema_version: NOT_VERIFIED_IN_B6
source_files_sha256:
  modules/convergence_workflow/README.md: d6353bdd837a2a8293c83189165c3a82a81b4144c04e5153793df06eef16cc53
  scripts/aqcat25_calibration.py: 56ac45732f317d725d0a85940a0f245cb141ceb4fa73d06297f838b5094b330a
  scripts/convergence/setup_alpha_fe_bulk_smearing.py: 52823f2b854e7b7458ce866991eecf102351a6292e2ce812424bc6708b282cac
  skills/fe-vasp-incar-custodian/scripts/incar_custodian.py: f953157c5ee9b3ee5191636e52404557d446c5ec570bce67520c75f0b9cc1624
  tests/scheduler_architecture.py: b028559bf0d72c4c3b954eceafcb20e53aabfdf39fff3ce7910d113d8f62f74a
  tests/test_alpha_fe_bulk_submission.py: f0a4a2ea9e628fc4216c1ce1ddf55de9929f084bbb4ba07160ace99726909997
  tests/test_b5_architecture_boundaries.py: 3ccffeaa3846467eaa9e61f86f81f459896d90b5c4a120a9c316ad0d529c0735
  tests/test_code_structure.py: 9a911cc46b3ecac9b2ae984075fa19a3213f8cc7bdad7ea477df4dff7786a66a
  tests/test_residual_parser_ownership.py: 78da6db71691f081995a63853ffe2a9d1f76f40a2a3cd20804adb834b6de5801
  tests/test_scheduler_mutation_ownership.py: 05a05c0fdc2ac540a84bbbc3f9e896d5511e4bf7b0bc43ede8f03d1ac0d2ef43
---

# AC-RERUN-B1-001 Execution Closure and Residual Parser Cleanup

Date: 2026-09-10. Scope: the identified execution P0 and the two named P2 parser
ownership defects only. Software closure: PASS. No production scientific
acceptance, live scheduler operation or operational state reconciliation is claimed.

Development source `C:/Users/86177/Desktop/work` was preserved. Changes and tests
ran in isolated worktree `C:/Users/86177/AppData/Local/Temp/sbq123-execution-closure`.
Base: `codex/b1-b7-final-acceptance-rerun`,
`a24bda4fb82c325bdcc385c9b089a061ddcf7096`.
Publication target: `https://github.com/q2214299493/sbq123.git`, branch
`codex/ac-rerun-b1-001-execution-closure`. No merge, main update, force push or B8.

## Findings and status

| Finding | Before | After |
|---|---|---|
| AC-RERUN-B1-001 | P0: two maintained scheduler mutation owners; alpha race dispatches twice | CLOSED: one owner, canonical exclusive reservation; adapter concurrency dispatches once |
| AC-RERUN-B2-001 | P2: independent raw INCAR parser loses semicolon MAGMOM | CLOSED: direct delegation to `scripts.vasp_result_gate.read_incar_values` |
| AC-RERUN-B2-002 | P2: calibration accumulates historical completion markers | CLOSED: completion metadata from `scripts.neb_agent.utils_vasp.parse_outcar` |

Remaining known P0: 0. Remaining known P1: 0. The two named P2 findings: 0 open.
No new P2/P3 finding identified in this bounded repair. Prior nonblocking
operational/document-classification limitations are retained below; this does not
replace the historical whole-repository acceptance reports.

## Original P0 reproduction before source edits

On the exact base, two threads called the real alpha `submit()` for one temporary
case containing only a synthetic `run.lsf`. Neither authorization nor gate evidence
was supplied. Only the external subprocess call was replaced by a fake returning
`Job <101>` / `Job <102>`. A barrier placed at the entry to the original private
write function synchronized both callers after their absence checks. The original
replace-based writes were then serialized solely to avoid Windows file-sharing
contention; a second barrier released both callers only after both writes finished.
This is a valid race schedule of the unchanged algorithm, not a replacement lock
in production. Each thread still independently dispatched.

Result: **2 fake scheduler dispatches for 1 case**, one normal return, one
`FileNotFoundError` removing the already-removed attempt after dispatch. The latter
does not undo the duplicate scheduler calls. An initial unconstrained harness run
hit Windows `os.replace` sharing contention and only dispatched once; the controlled
schedule above reproduced the logical race deterministically before source edits.

Characterization core (executed against the unmodified base):

```python
barrier = threading.Barrier(2)
after_write = threading.Barrier(2)
write_lock = threading.Lock()
original_write = alpha._write_json_atomic

def synchronize_before_write(*args, **kwargs):
    barrier.wait(timeout=10)  # both callers have passed attempt.exists()
    with write_lock:
        result = original_write(*args, **kwargs)  # actual base os.replace writer
    after_write.wait(timeout=10)
    return result

alpha._write_json_atomic = synchronize_before_write
# alpha.subprocess.run is a counting fake; two pool workers call alpha.submit().
# Observed argv twice: ["bsub", "run.lsf"]. No real scheduler was contacted.
```

## Canonical adapter and compatibility

`setup_alpha_fe_bulk_smearing.submit(submission_manifest=None)` and `--submit`
remain public compatibility entry points. Missing manifest explicitly raises
`CANONICAL_EXECUTION_AUTHORIZATION_REQUIRED`. A non-empty JSON object selects
known campaign case labels and supplies absolute workdir/decision paths, host,
remote directory, POTCAR source/hash and action. The adapter validates routing
shape and campaign identity, then directly calls `submission.submit(**arguments)`.
It never manufactures evidence or authorization and has no scheduler subprocess.
The supported static action is `SUBMIT_DIAGNOSTIC_VASP`.

The existing B1 gate checks current action, workdir identity, bundle hash, evidence
hash, authorization source, target and POTCAR binding. Its exclusive
`write_json_exclusive` remains the linearization point. Its remote reservation,
canonical path checks, staging, complete final manifest verification, submission
and receipt code are byte-identical to base. Both new upload and reuse semantics
are covered by the unchanged B1 lifecycle tests. ScientificReadiness,
ExecutionAuthorization, EvidenceBinding, InputBundle, SubmissionReservation and
SubmissionResult are unchanged.

The old campaign private JSON/text atomic writers, marker-success parsing,
job-ID parser, scheduler invocation, timeout/retry handling and attempt deletion
were removed. Searches found their maintained callers only in the old campaign
tests; same-named unrelated state-manager helpers were preserved. The default
campaign cases, numerical setup and summary remain intact.

New setup writes one `script.lsf` with identical source LSF bytes and adds a
`POTCAR.spec` containing only the source SHA-256. It retains the existing local
input-copy behavior and does not alter potential bytes. All setup testing used
synthetic text, never real POTCAR. An existing `run.lsf` stops setup for explicit
reviewed migration instead of producing independently mutable LSF copies. Existing
runtime directories were not migrated. `--check` checks the canonical names.
The module README documents these intentional input-name/receipt compatibility
changes and the per-case handoff format.

Legacy `submitted.jobid` is a reconciliation blocker, not authorization. A legacy
attempt is rejected by the canonical reservation check. Neither is silently
deleted or translated into success. Completed canonical receipts block repeat
submission; uncertain outcomes retain `UNKNOWN_NEEDS_RECONCILIATION` and never
authorize retry. Cases are independent, not an atomic multi-case transaction.

## Regression evidence

The adapter tests call the real campaign adapter, gate, preflight, current evidence
validation and canonical executor. Only transport/scheduler calls and the specified
receipt-loss fault are faked; all authorization documents and structures are
explicit temporary test fixtures. No scientific validator is replaced with PASS.

| Scenario | Observed behavior |
|---|---|
| Two adapter callers synchronized at canonical reservation | one success, one reservation-exists rejection; dispatch count 1 |
| No manifest | explicit authorization-required error; dispatch 0; NOT_RESERVED |
| Routing manifest plus readiness-only decision, no execution authority | PermissionError, dispatch 0; NOT_RESERVED |
| Changed INCAR, KPOINTS, script.lsf, POTCAR.spec, analysis or approval | rejection before dispatch; count 0 |
| Successful reviewed handoff | job 321 fake receipt matches retained canonical reservation and bundle hash |
| Receipt write lost after dispatch | UNKNOWN; reservation bytes unchanged; second call denied; total dispatch 1 |
| Timeout, rejected command, missing scheduler job ID | UNKNOWN; second call denied; total dispatch 1 |
| Legacy job marker or attempt | rejection, marker bytes retained, dispatch 0 |
| Missing decision/script or malformed/wrong case/workdir routing | rejection before dispatch; count 0 |

Two previous test assertions intentionally changed: successful submission no longer
deletes its reservation, and `submitted.jobid` is no longer the successful receipt.
These were the unsafe legacy contract, not scientific behavior to preserve.
The setup test now asserts unchanged LSF bytes under `script.lsf`, hash-only spec,
exact complete INCAR values, exact KPOINTS, copied synthetic POSCAR/POTCAR bytes
and successful canonical input check.

The parser regressions cover semicolon/multiple tags, whitespace, case, comments,
literal `3*2.0`, missing tag/file/None and canonical duplicate/malformed rules.
Calibration tests cover later run headers, newer incomplete cycles, truncated
iteration headers, valid final completion, preserved latest force/TOTEN extraction
and missing force/energy errors. Retained diagnostic arrays never imply current
completion or scientific acceptance. All inspected accepted-registry and ML label
consumers retain their existing scientific gates.

## Complete scheduler-dispatch inventory

Scanned all maintained Python under scripts/modules/skills and searched source,
tests, shell scripts/templates and CI YAML for subprocess.run/Popen, os.system/
os.popen, shell=True, bsub/bkill/sbatch/scancel/qsub/qdel and SSH forms. The semantic
AST scan includes import aliases, command lists/strings, assignment fragments,
concatenation, append/extend, function-return commands, local runners and nested
SSH shell commands. It found **231 maintained Python files and exactly one owner**:

| Mutation | Actual dispatch site | Owner |
|---|---|---|
| bsub after full remote bundle verification | `scripts/neb_agent/submission.py:464` (command fragment at 462) | AUTHORITATIVE_EXECUTOR |
| bkill after reviewed stop authorization | `scripts/neb_agent/submission.py:544` | AUTHORITATIVE_EXECUTOR |

`submission.py:576` is the shared subprocess transport, not another semantic
executor. Its calls at 443/596 prepare or verify remote state, and 534 queries
bjobs; these do not create another scheduler mutation owner. No sbatch/scancel/
qsub/qdel dispatch exists in maintained source. No maintained shell/CI scheduler
mutation was found. Shell templates that only describe jobs are SHELL_TEMPLATE,
not additional submission owners. The pre-repair alpha site at base line 158 was
LEGACY_EXECUTOR and is removed, not allowlisted or hidden as historical material.

Every broad search-hit file and its line numbers is listed below. Non-scheduler
subprocesses use an explicit additional classification rather than being
mislabelled as read-only scheduler queries.

| Search-hit path | Lines | Classification |
|---|---|---|
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/src/runner/base_runner.py` | 87 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_analysis.py` | 148 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_catkinas_generator.py` | 341 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_foundation.py` | 155 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_kinetic_dataset.py` | 187 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_result_parser.py` | 180 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_runner.py` | 189 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_validator.py` | 246 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_vasp_parser.py` | 216 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_workflow.py` | 127, 153 | ARCHIVED/HISTORICAL |
| `modules/state_handoff/archive/2026-08-07/repository-items-d365620c27afc7c752614a67/VASP2Kinetics/tests/test_zacros_cli.py` | 76 | ARCHIVED/HISTORICAL |
| `scripts/adsmind_lite/audit_remote_fe110_batch.py` | 50, 51 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/adsorption/backfill_step12a_registry.py` | 234, 235 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/adsorption/finalize_step12a_gas_references.py` | 261 | ARCHIVED/HISTORICAL command-description metadata; no dispatch |
| `scripts/adsorption/register_step12a_gas_reference_submission.py` | 89 | ARCHIVED/HISTORICAL command-description metadata; no dispatch |
| `scripts/adsorption/register_step12a_oh_restart.py` | 52, 62 | ARCHIVED/HISTORICAL command-description metadata; no dispatch |
| `scripts/aqcat25_ts_force_prediction_batch.py` | 101 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/collect_dual_model_ts_vasp_labels.py` | 49, 50 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/neb_agent/remote_monitor.py` | 53, 54 | READ_ONLY_SCHEDULER_QUERY (monitor also reads calculation files) |
| `scripts/neb_agent/submission.py` | 105, 443, 450, 462, 464, 534, 544, 576, 596 | AUTHORITATIVE_EXECUTOR (mixed transport, verification, query and mutation) |
| `scripts/prepare_reviewed_neb_peak_dimer.py` | 65 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/registry_excel_promotion.py` | 439 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/release_environment.py` | 44 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/scheduler_evidence.py` | 36, 38, 65 | READ_ONLY_SCHEDULER_QUERY (monitor also reads calculation files) |
| `scripts/state_manager/audit.py` | 358, 380 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/state_manager/proposals.py` | 353 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/state_manager/stale_items.py` | 17, 190 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `scripts/validate_release.py` | 20, 49 | NON_SCHEDULER_EXTERNAL_COMMAND (details below) |
| `tests/scheduler_architecture.py` | 13, 14, 15 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_adsmind_prescreen.py` | 144 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_alpha_fe_bulk_submission.py` | 52, 138 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_aqcat25_path_active_learning.py` | 283, 285 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_aqcat25_ts_active_learning.py` | 255, 257 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_b21_scientific_acceptance.py` | 43 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_b2_scientific_contract.py` | 319 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_b4_state_governance.py` | 95 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_b7_release.py` | 123, 125 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_execution_backends.py` | 93 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_execution_lifecycle.py` | 170, 197, 226, 245, 253, 268, 270, 305, 332, 335, 411, 418, 454, 459 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_external_command_boundaries.py` | 39, 67, 71 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_gpu_execution_lifecycle.py` | 140, 219, 292 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_incar_custodian_cli.py` | 16 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_mlip_same_structure_benchmark.py` | 53 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_neb_execution_gate.py` | 196, 198, 261, 263 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_neb_pilot_validation.py` | 20, 21 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_neb_remote_monitor.py` | 44, 59 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_neb_submission.py` | 359, 381, 385 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_scheduler_mutation_ownership.py` | 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 34, 35, 36, 37 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_state_manager.py` | 1588 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |
| `tests/test_ts_validation.py` | 76 | TEST_FAKE (fixtures, static assertions or isolated local subprocess tests) |

Non-scheduler maintained subprocess review (all 17 direct subprocess sites,
including the canonical transport and two scheduler-query sites above):

| File/site | Actual non-scheduler responsibility |
|---|---|
| audit_remote_fe110_batch.py:50 | SSH read-only structure/base64 collection |
| backfill_step12a_registry.py:234 | SSH read-only Python calculation audit; no dispatch in transmitted source |
| aqcat25_ts_force_prediction_batch.py:101 | validated per-structure Python prediction runner; not run in this task |
| collect_dual_model_ts_vasp_labels.py:49 | SSH sha256sum identity reads |
| prepare_reviewed_neb_peak_dimer.py:65 | local Perl dist.pl geometry distance calculation; no scheduler |
| registry_excel_promotion.py:439 | local Node workbook writer with plan; no scheduler, not run against production |
| release_environment.py:44 | isolated installed CLI --help |
| state_manager/audit.py:358,380 | local git read-only inspection/check-ignore |
| state_manager/proposals.py:353 | local git ls-files |
| state_manager/stale_items.py:17,190 | local git ls-files |
| validate_release.py:20,49 | local pip/venv/probe runner and git checkout-index for disposable release validation |

The broader mutation guard replaces both former exact-string checks in B5 and
code-structure tests. There is no convergence scope exemption. Separate fixtures
prove alternate dispatch forms are detected and inert templates/read-only bjobs
queries are permitted. Tests and archives are classified separately; no unsafe
legacy production implementation was retained as a test helper.
The new guard was also run against the actual alpha source retrieved from the
base commit and correctly identified its legacy dispatch at line 158.

This is a conservative static source audit, not a proof about arbitrary dynamic
code, external user-supplied executable bodies or a compromised interpreter.

## Exact validation

- `python -m ruff check scripts modules tests`: exit 0, All checks passed.
- `python -m pytest -o addopts= -q`: exit 0, **1181 passed in 343.48s (0:05:43)**; failed 0, skipped 0.
- Initial final focused closure suite: exit 0, **101 passed in 26.49s**.

Focused command (before the full suite):

```text
python -m pytest -o addopts= -q tests/test_alpha_fe_bulk_submission.py tests/test_residual_parser_ownership.py tests/test_incar_custodian_cli.py tests/test_aqcat25_calibration.py tests/test_scheduler_mutation_ownership.py tests/test_code_structure.py tests/test_b5_architecture_boundaries.py
```

During test development, one new test incorrectly expected ValueError instead
of the established gate's PermissionError for absent authorization. The assertion
was corrected to require PermissionError and its refusal message; production
behavior was not altered. Ruff also prompted splitting the test-only source-binding
collector from dispatch analysis; no limits were changed.

Required groups rerun after the full suite:

| Group | Result | Exit |
|---|---|---|
| B1 | 275 passed in 125.78s (0:02:05) | 0 |
| B2 | 221 passed in 81.44s (0:01:21) | 0 |
| B5 | 74 passed in 17.37s | 0 |
| B7 | 17 passed in 0.76s | 0 |

B1:

```text
python -m pytest -o addopts= -q tests/test_execution_lifecycle.py tests/test_neb_execution_gate.py tests/test_execution_gate_compatibility.py tests/test_execution_backends.py tests/test_gpu_execution_lifecycle.py tests/test_artifact_io.py tests/test_alpha_fe_bulk_submission.py tests/test_neb_submission.py
```

B2:

```text
python -m pytest -o addopts= -q tests/test_b2_scientific_contract.py tests/test_b21_scientific_acceptance.py tests/test_ts_strategy_engine.py tests/test_scientific_claim_authority.py tests/test_residual_parser_ownership.py tests/test_aqcat25_calibration.py tests/test_incar_custodian_cli.py
```

B5:

```text
python -m pytest -o addopts= -q tests/test_b5_architecture_boundaries.py tests/test_code_structure.py tests/test_repository_contracts.py tests/test_scheduler_mutation_ownership.py
```

B7:

```text
python -m pytest -o addopts= -q tests/test_b7_release.py
```

Fresh release command (exit 0):

```text
python -m scripts.validate_release --source . --output C:/Users/86177/AppData/Local/Temp/sbq123-execution-closure-release-20260910
```

Release: **PASS**, clean indexed source, editable/wheel parity true; both smoke
records have external_actions=0 and scientific_acceptance=false. Built actual wheel
`sbq_catalyst_agent_workflow-0.1.0-py3-none-any.whl`, 286 members,
SHA-256 `6642a14beeb5f5edc8c233056f304cbbdacf750ac896ba25b00983a5bf2d9de4`. Sensitive-artifact exclusion checks passed,
excluded_artifacts is empty. Index contained the repaired source/tests and README
before the build; this final report is the only later documentation addition.
The wheel's alpha campaign and calibration module bytes were independently
compared with the repaired working source and matched exactly.

`git diff --cached --check` passed. No full/focused suite assertion or architecture
limit was weakened. Existing B1 core test definitions were retained.
`python -m ruff check skills/fe-vasp-incar-custodian/scripts/incar_custodian.py`
also exited 0 (the required Ruff command does not include skills).

## Scientific freeze and unchanged evidence

AST comparison with the exact base confirms alpha `write_incar`, `write_kpoints`
and `summary` are identical. The case definitions, scientific thresholds,
VASP/NEB/DIMER/VFA/TS logic, chemistry, registry schemas, production data and GPU
wrappers were not changed. No actual POTCAR, model weights, calculation output or
private key was inspected/copied/modified. Production scientific actions = 0.

Byte-for-byte equality with base was verified for the five required historical
reports and the canonical executor:

| Unchanged path | SHA-256 |
|---|---|
| `reports/refactor_audit/B1_B7_acceptance_report.md` | `8c6efae9463aae72ed72cdf2c86c5433593d49e23de3f804bac6cf1be6a6998f` |
| `reports/refactor_audit/B1_B7_acceptance.json` | `8cd82df6d1340e74f442327ef76bdb9c9289196ef193982e13130bf75095f64a` |
| `reports/refactor_audit/AC_B2_001_repair_report.md` | `9b71b6ab110b743db79277c4c2dedb7fd094893d79090777209df724e4683939` |
| `reports/refactor_audit/B1_B7_acceptance_rerun_report.md` | `312751d2b9f7fb9cc9299c36822c29a15b493e6c1bbdae222ea13f9b3d8868be` |
| `reports/refactor_audit/B1_B7_acceptance_rerun.json` | `a1427d96a8d7b560eccee24272b313430ff4cf3e8e21ddee17b02867c43a3419` |
| `scripts/neb_agent/submission.py` | `fe8f4095b23f571046c6615eb1b1b9ebb10be3d8669a53d76a62ab9437f64dbf` |

## Exact task-owned changed files

- `modules/convergence_workflow/README.md`
- `reports/refactor_audit/AC_RERUN_B1_001_execution_closure_report.md`
- `scripts/aqcat25_calibration.py`
- `scripts/convergence/setup_alpha_fe_bulk_smearing.py`
- `skills/fe-vasp-incar-custodian/scripts/incar_custodian.py`
- `tests/scheduler_architecture.py`
- `tests/test_alpha_fe_bulk_submission.py`
- `tests/test_b5_architecture_boundaries.py`
- `tests/test_code_structure.py`
- `tests/test_residual_parser_ownership.py`
- `tests/test_scheduler_mutation_ownership.py`

## Remaining uncertainties and operational boundary

No real scheduler, SSH query, VASP/VTST, GPU inference/training, production registry
or workbook operation was performed. Remote backend behavior, queue policy,
deployed schemas and scientific performance remain production-only uncertainties.
The before/after dispatch counts are simulated external actions, not real jobs.

Startup read-only repo-state audit exited 1 with errors=1, warnings=4,
review_required=5: existing transition_state_search managed projection drift and
temporary worktree ownership warnings. No task chosen, state reconciled, event
rewritten or projection synchronized. Eight prior unsupported skill-frontmatter
classifications and other earlier documented operational limitations were not
part of this repair; historical verdicts remain intact.

Publication is limited to this task's branch and listed files with commit message
`fix: route legacy convergence submission through canonical execution authority`.
After successful push, stop; no further refactor, acceptance expansion or merge.

```text
p0_original_reproduced=true (2 fake dispatches)
authoritative_executor=scripts/neb_agent/submission.py
maintained_scheduler_mutation_owners=1
alpha_concurrency_dispatch_count=1
alpha_no_authorization_dispatch_count=0
p2_incar_parser=CLOSED
p2_outcar_completion=CLOSED
remaining_p0=0
remaining_p1=0
external_scientific_actions=0
```
