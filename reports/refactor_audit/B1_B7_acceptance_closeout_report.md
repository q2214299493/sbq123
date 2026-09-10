---
document_class: GENERATED_CURRENT_REPORT
as_of: '2026-09-10T07:05:52.204219+00:00'
source_version: 9bf950b09b965ea832148fb3ad0f44625492652e
source_tree: 1b53d984a0ccb90464e6f01cec80716b2ceccd99
source_branch: codex/ac-rerun-b1-001-execution-closure
source_scope: isolated locked candidate; software acceptance audit only
evidence_kind: SOFTWARE_ACCEPTANCE_AUDIT
production_schema_version: UNVERIFIED
governance: docs/DOCUMENT_GOVERNANCE.md
---

# B1–B7 Final Acceptance Closeout

**CODE_MERGE_READINESS = NOT_READY_TO_MERGE**
**PRODUCTION_OPERATION_READINESS = UNVERIFIED**

The four known findings independently close. One newly reproduced P1 in a maintained thickness-campaign execution template blocks whole-repository acceptance. A separate diagnostic parser P2 is nonblocking. Full tests, focused tests, fresh release and exact-candidate CI pass; those results do not override the reproduced failure. No source was repaired.

## Locked candidate and isolation

- Repository: `q2214299493/sbq123`; candidate `9bf950b09b965ea832148fb3ad0f44625492652e`; tree `1b53d984a0ccb90464e6f01cec80716b2ceccd99`.
- Candidate branch: `codex/ac-rerun-b1-001-execution-closure`; audit branch: `codex/b1-b7-final-acceptance-closeout`.
- Isolation began `2026-09-10T06:36:30.550780+00:00` (clone creation); evidence compilation `2026-09-10T07:05:52.204219+00:00`.
- OS `Windows-11-10.0.26200-SP0`; local Python `3.13.9`. Source `C:/Users/86177/AppData/Local/Temp/sbq123-closeout-20260910`.
- External programs, logs, fixtures, SQLite databases, release export and venvs: `C:/Users/86177/AppData/Local/Temp/sbq123-closeout-evidence-20260910`.
- Development directory was not tested, built, installed, reset, cleaned, checked out, pulled, overwritten or synchronized. No state sync, scientific SSH/query/job, VASP/VTST, GPU, production data change or actual POTCAR access.
- Local full/focused tests used existing Anaconda dependencies. Release wheel and editable environments were fresh and separate. Pytest also uses external system temp directories; ignored checkout caches cannot enter the tracked-file release export.

## New findings

### AC-CLOSEOUT-B1-001 — P1 OPEN (blocking)

**Maintained thickness chain advances after failed relaxation and can exit success using stale output markers**

Location: `scripts/convergence/setup_true_fe110_thickness_retest.py::chain_lsf`; lines 112, 121, 122, 128, 130, 131.

Expected: Current failed relaxation must stop the chain before copying old geometry or attempting static; failed current execution must not return success.
Observed: Exact generated shell: both fake mpirun calls return 9; static stage is still attempted, old CONTCAR copied, final shell exit 0.

Execution safety failure in a maintained two-stage scientific workflow, with an avoidable second costly stage and false process success. Block whole-repository execution acceptance even though canonical submission itself is closed.

This is not a second scheduler mutation owner, not a demonstrated execution-authorization bypass, and not proof of accepted registry science. It requires pre-existing output markers; no live job was run.

Both findings are unchanged from the preceding audit baseline; they were discovered in this closeout, not introduced by the execution repair. The exact synthetic repro code and observations are embedded in the companion JSON.

### AC-CLOSEOUT-B2-001 — P2 OPEN (nonblocking)

**Thickness campaign TOTEN regex misses valid ordinary VASP energy lines**

Location: `scripts/convergence/setup_true_fe110_thickness_retest.py::last_toten`; lines 220, 223, 228, 230.

Expected: -10.5
Observed: None

Double-escaped whitespace in a raw regex causes diagnostic/summary unavailability. It fails by omission/no-TOTEN error, not false scientific acceptance; nonblocking on its own.

No accepted scientific result was produced by this reproduction.

Both findings are unchanged from the preceding audit baseline; they were discovered in this closeout, not introduced by the execution repair. The exact synthetic repro code and observations are embedded in the companion JSON.

## History and incremental review

`origin/main` and merge-base: `5c5fed9b4a0691a893af3d03eaae10636999aa85`. Cumulative inventory: 249 paths (72 added, 177 modified, zero deleted/renamed). The JSON retains every path, not just counts.
`a24bda4fb82c325bdcc385c9b089a061ddcf7096` is an ancestor of the candidate. Fixed historical B1–B7 SHAs, the two failed audits and both repairs are all ancestors; labels below identify historical refs, while the fixed SHAs establish continuity.

| Historical label | Fixed SHA | Ancestor |
|---|---|---|
| `origin/codex/b1-execution-lifecycle` | `b1c59addbc7d7be64347db66a201dc5841404341` | True |
| `origin/codex/b2-scientific-contract` | `3d9e9070e48a6cb65d9b4c0334adb4243f36dd0c` | True |
| `origin/codex/b3-evidence-ml-governance` | `9f4332f082d4e286ce43c5a137a62ac1e30fa441` | True |
| `origin/codex/b4-registry-state-management` | `fbbb7bb26d28867d9766cc7fca84077fa54cf3d6` | True |
| `origin/codex/b5-architecture-boundaries` | `3a1bb3f461147a7dc9b5df5efca89de621d27f38` | True |
| `origin/codex/b6-documentation-data-governance` | `93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a` | True |
| `origin/codex/b7-release-environment` | `7a0b745df96de2762a6f289e9eeda1a3c298fe9d` | True |
| `first_failed_audit` | `fad1d32607723c851c457a5fb6fa85898cdc1edf` | True |
| `scientific_claim_repair` | `a050fe28b25f1fc5ee91f5e7e3fb7fc1150a2157` | True |
| `second_failed_audit` | `a24bda4fb82c325bdcc385c9b089a061ddcf7096` | True |
| `execution_repair` | `9bf950b09b965ea832148fb3ad0f44625492652e` | True |

All six historical audit/repair reports remain byte-identical to their candidate Git blobs. The preceding five also match the prior audit baseline. No historical NOT_READY result was rewritten.

Incremental review covers 11 files (4 added, 7 modified, no deletions):

- `modules/convergence_workflow/README.md` (M)
- `reports/refactor_audit/AC_RERUN_B1_001_execution_closure_report.md` (A)
- `scripts/aqcat25_calibration.py` (M)
- `scripts/convergence/setup_alpha_fe_bulk_smearing.py` (M)
- `skills/fe-vasp-incar-custodian/scripts/incar_custodian.py` (M)
- `tests/scheduler_architecture.py` (A)
- `tests/test_alpha_fe_bulk_submission.py` (M)
- `tests/test_b5_architecture_boundaries.py` (M)
- `tests/test_code_structure.py` (M)
- `tests/test_residual_parser_ownership.py` (A)
- `tests/test_scheduler_mutation_ownership.py` (A)

The alpha adapter removes its scheduler implementation and delegates to the existing owner. Calibration delegates current completion to the existing VASP parser; custodian delegates raw INCAR to the existing parser. Architecture tests replace a single literal-string check with semantic dispatch scanning without relaxing the expected owner or line limit. New/expanded tests include actual positive/concurrent/failure lifecycle and parser cases. The new scanner was independently exercised with original list-form bsub, import aliases, concatenation, append/extend, local runner and nested SSH; inert comments/examples produced no dispatch sites.
No canonical executor, authorization validator, scientific claim owner, registry schema or release policy moved/copied. Source-diff evidence is distinct from current test executions below; old report test counts are historical only.

## Four known issues

| ID | Status | Current independent evidence |
|---|---|---|
| AC-B2-001 | CLOSED | Bare/hash-bound fake summaries rejected. Current DIMER/VFA grants only APPROVE_TS_CANDIDATE. Changed scientific sources revoke old claims. Current NEB/CI-NEB connectivity retained; no new DIMER connectivity/Hessian demand. Positive real-owner persistence works; stale TS/barrier/template rows absent. |
| AC-RERUN-B1-001 | CLOSED | Real setup/check/adapter/preflight/authorization/gate/reservation pass a valid positive and concurrent case; no authority in routing manifest; stale and legacy paths reject; unknown submit outcomes never auto-resubmit. |
| AC-RERUN-B2-001 | CLOSED | Literal MAGMOM 3*2.0 retained with semicolons, whitespace, case/comments; missing value/file None; duplicate/malformed semantics match canonical owner. |
| AC-RERUN-B2-002 | CLOSED | Old completion plus newer run/cycle/truncated iteration gives normal_completion=false in actual labels; valid current final gives true. Diagnostic energy -10.5 and forces retained, never equated with accepted science. |

### Authorized execution and failure cases

The audit built synthetic bcc Fe2 inputs with the real campaign setup and check, then used the real preflight, evidence binding, authorization validator, gate, campaign adapter and canonical reservation/executor. Synthetic static review/NO_OUTPUT inputs and a clearly marked synthetic authorization file were supplied; no real user authority was read. POTCAR was inert synthetic text, not a real potential. Only terminal transport was faked; the concurrency barrier called the original exclusive-create implementation. Receipt loss additionally injected OSError at the receipt writer. No scientific predicate, gate or reservation was replaced with always-PASS.

| Scenario | Mock scheduler dispatches | Result |
|---|---:|---|
| no_manifest | 0 | PASS / NOT_RESERVED |
| routing_without_authorization | 0 | PASS / NOT_RESERVED |
| positive | 1 | PASS / SUBMITTED |
| concurrent | 1 | PASS / SUBMITTED |
| stale_INCAR | 0 | PASS / NOT_RESERVED |
| stale_KPOINTS | 0 | PASS / NOT_RESERVED |
| stale_script.lsf | 0 | PASS / NOT_RESERVED |
| stale_POTCAR.spec | 0 | PASS / NOT_RESERVED |
| stale_analysis.json | 0 | PASS / NOT_RESERVED |
| stale_synthetic-authorization.txt | 0 | PASS / NOT_RESERVED |
| timeout | 1 | PASS / UNKNOWN_NEEDS_RECONCILIATION |
| uncertain_response | 1 | PASS / UNKNOWN_NEEDS_RECONCILIATION |
| receipt_loss | 1 | PASS / UNKNOWN_NEEDS_RECONCILIATION |
| legacy_submitted.jobid | 0 | PASS / NOT_RESERVED |
| legacy_submission_attempt.json | 0 | PASS / UNKNOWN_NEEDS_RECONCILIATION |
| run_lsf | 0 | PASS / NOT_RESERVED |

Positive dispatch = 1; concurrent dispatch = 1 with one successful caller and one rejected caller; unauthorized dispatch = 0. All independent lifecycle fault scenarios together make five simulated dispatches: positive, concurrent, timeout, uncertain response and receipt loss. Repeating unknown outcomes adds zero. These are separate from **zero real external scientific actions**. Current B1 tests additionally exercise full manifest verification in both new upload and reuse modes and GPU early-failure records.

### Claims, chemistry and persistence

Direct and file-bound fabricated Grade-A booleans cannot claim a TS. A real synthetic current DIMER/VFA can claim APPROVE_TS_CANDIDATE only; it grants neither execution authority nor a final barrier. Changed source OUTCAR/POSCAR/DIMER/review/handoff invalidates an unchanged summary; cross-object DIMER/VFA fails. Independent NEB/CI-NEB cases preserve connectivity and reject changed contract, endpoint/path review and connectivity output. No DIMER connectivity or Hessian requirement was added.
The real matched-static owner persisted a synthetic compatible barrier (forward 1.0 eV, reverse 1.5 eV, reaction -0.5 eV). These are fixture values, not scientific results. Positive TS/barrier/template counts were each 1; stale-source new counts were each 0. The barrier positive is the fixture constructor’s actual owner invocation, independently queried afterward; it is not a mocked insert.
Audit-only persistence fixture mistakes are retained: duplicate reaction/result and template identities were intentionally rejected by SQLite; the second rolled back both new rows. A later expected-value arithmetic error was corrected against the fixture inputs in a fresh run. Final persistence probe exited 0. Initial errors are not represented as source bugs or successful probes.

## Scheduler and external call-site inventory

Independent AST inventory resolved imported subprocess/os aliases and listed every maintained direct sink for manual command/data-flow review; it did not copy the maintained test scanner output. Literal scheduler fragments, assignments, local runners, SSH command strings, shell, templates, skills and CI were reviewed together. One maintained scheduler mutation owner remains: `scripts/neb_agent/submission.py`. Static analysis cannot certify arbitrary computed/vendor programs.

| File/function | Line | Category | Command / final owner |
|---|---:|---|---|
| `scripts/neb_agent/submission.py::submit` | 464 | AUTHORITATIVE_EXECUTOR | SSH embedded bsub script.lsf → `scripts.neb_agent.submission._run:576` |
| `scripts/neb_agent/submission.py::stop_job` | 544 | AUTHORITATIVE_EXECUTOR | SSH bkill validated job_id → `scripts.neb_agent.submission._run:576` |
| `scripts/adsmind_lite/audit_remote_fe110_batch.py::fetch_structures` | 50 | READ_ONLY_QUERY | SSH read-only encoded structure retrieval; owner `scripts/adsmind_lite/audit_remote_fe110_batch.py` |
| `scripts/adsorption/backfill_step12a_registry.py::remote_evidence` | 234 | READ_ONLY_QUERY | SSH embedded read-only VASP evidence extraction; surrounding registry workflow is not executed; owner `scripts/adsorption/backfill_step12a_registry.py` |
| `scripts/aqcat25_ts_force_prediction_batch.py::run_batch` | 101 | UNRESOLVED_DYNAMIC_PATH | Local Python --runner; maintained shell chooses AQCat prediction script, but arbitrary external runner contents are outside candidate assurance; owner `scripts/aqcat25_ts_force_prediction_batch.py` |
| `scripts/collect_dual_model_ts_vasp_labels.py::_remote_hashes` | 49 | READ_ONLY_QUERY | SSH sha256sum only; owner `scripts/collect_dual_model_ts_vasp_labels.py` |
| `scripts/neb_agent/remote_monitor.py::run_remote_monitor` | 53 | READ_ONLY_QUERY | SSH bounded check_neb_job.sh monitor, no scheduler mutation; owner `scripts/neb_agent/remote_monitor.py` |
| `scripts/neb_agent/submission.py::_run` | 576 | AUTHORITATIVE_EXECUTOR | Canonical _run transport; submit and stop_job mutation sites separately listed; owner `scripts/neb_agent/submission.py` |
| `scripts/prepare_reviewed_neb_peak_dimer.py::main` | 65 | UNRESOLVED_DYNAMIC_PATH | Invokes archive/vtst_review_job9745217/dist.pl via Perl; helper absent from candidate, not certified merely because it is under archive; owner `scripts/prepare_reviewed_neb_peak_dimer.py` |
| `scripts/registry_excel_promotion.py::_run_writer` | 439 | NON_SCHEDULER_EXTERNAL_COMMAND | Node workbook writer; distinct reviewed database/workbook boundary, never executed here; owner `scripts/registry_excel_promotion.py` |
| `scripts/release_environment.py::inspect_install` | 44 | NON_SCHEDULER_EXTERNAL_COMMAND | Installed console help probes; owner `scripts/release_environment.py` |
| `scripts/scheduler_evidence.py::query_lsf_job` | 38 | READ_ONLY_QUERY | SSH bjobs evidence query only; never actually executed here; owner `scripts/scheduler_evidence.py` |
| `scripts/state_manager/audit.py::_git_lines` | 358 | READ_ONLY_QUERY | git status/ls-files/check-ignore repository inspection; owner `scripts/state_manager/audit.py` |
| `scripts/state_manager/audit.py::_audit_repository_items` | 380 | READ_ONLY_QUERY | git status/ls-files/check-ignore repository inspection; owner `scripts/state_manager/audit.py` |
| `scripts/state_manager/proposals.py::_validate_tracking_status` | 353 | READ_ONLY_QUERY | git tracked-file inspection; owner `scripts/state_manager/proposals.py` |
| `scripts/state_manager/stale_items.py::_tracking_status` | 17 | READ_ONLY_QUERY | git tracking/selector inspection; owner `scripts/state_manager/stale_items.py` |
| `scripts/state_manager/stale_items.py::_selector_items` | 190 | READ_ONLY_QUERY | git tracking/selector inspection; owner `scripts/state_manager/stale_items.py` |
| `scripts/validate_release.py::run` | 20 | NON_SCHEDULER_EXTERNAL_COMMAND | Local git export, pip, venv and software probes; owner `scripts/validate_release.py` |
| `scripts/validate_release.py::clean_source` | 49 | NON_SCHEDULER_EXTERNAL_COMMAND | Local git export, pip, venv and software probes; owner `scripts/validate_release.py` |

The shared sunboquan LSF template is reachable through `vasp_lsf.py`; it is a generated MPI payload, not an independent scheduler. Thickness `run_chain.lsf` payloads are reachable through their maintained generator and contain the P1 above; calling them templates does not dismiss that risk. GPU wrappers dispatch local prediction/vendor programs, not schedulers; remote vendor/runtime contents remain outside this software audit. CI runs local build/test commands. Test command snippets are TEST_FIXTURE. Tracked VASP2Kinetics archive references are inventory/migration metadata with no maintained dispatch edge found (ARCHIVED_UNREACHABLE). The absent `archive/vtst_review_job9745217/dist.pl` is different: a maintained script calls it, so it is explicitly UNRESOLVED_DYNAMIC_PATH. The JSON lists every scanned shell/template path and classification.

## B1–B7 acceptance matrix

| Package | Verdict | Evidence and scope |
|---|---|---|
| B1 | FAIL | B1 current 260 tests; independent alpha lifecycle 16 scenarios; unchanged canonical source and GPU wrappers. Current source/bundle/target/POTCAR binding, exclusive reservation, both upload manifests, cross-call competition, unknown-outcome retry rejection and GPU fail-closed pass. Reachable thickness-chain failure AC-CLOSEOUT-B1-001 remains blocking. |
| B2 | PASS_WITH_NONBLOCKING_LIMITATION | B2 current 162 tests; AC_B2_001 current 31 tests; independent parser/claim/NEB/persistence probes. Final SCF; INCAR; normalized contract semantics; finite/range/index; chemical events; DIMER/VFA identity; matched-static finite/compatibility checks pass. Residual campaign summary regex P2 remains, outside acceptance owner. |
| B3 | PASS | B3 current 68 tests; no incremental evidence/promotion policy changes. Evidence lifecycle, retrieval versus acceptance, prediction provenance, uncertainty and train/validation/test leakage rules. Synthetic model data only; no real inference/training. |
| B4 | PASS | B4 current 121 tests; independent stale TS/barrier/template insertion rejection and transaction rollback. Plan/hash/approval/fingerprint, atomic apply/rollback/idempotency, immutable revisions/events/results, transitions, explicit migration, status-only batches and reviewed_at timestamps. Temporary SQLite only. |
| B5 | PASS_WITH_NONBLOCKING_LIMITATION | B5 current 56 tests; independent source sink inventory; scanner alias/concat/SSH probes; import graph no cycles. One maintained scheduler mutation owner; alpha thin adapter; canonical authority definitions unchanged; Fe(110) module ownership retained. Two external dynamic hooks are unresolved beyond repository contents; static graph is not a formal proof. |
| B6 | PASS_WITH_NONBLOCKING_LIMITATION | B6 current 26 tests; two deterministic readiness builds match candidate JSON/Markdown; affected Markdown links valid. Authority/last-recorded distinction; supported code schema 9 distinct from unverified production schema; prediction/acceptance classification. Eight unsupported SKILL frontmatters are recorded as unsupported. Existing task mismatch/projection drift not reconciled. |
| B7 | PASS | B7 current 17 tests; fresh wheel and clean editable/wheel parity; exact candidate Ubuntu/Windows CI; LOCAL_WINDOWS_VALIDATION focused 99. Actual artifact, 60 runtime resources, 9 console entrypoints, optional scientific dependencies absent in fresh venvs, repository-only errors, mock smoke scientific_acceptance=false/external_actions=0. Production/HPC operations not verified. |

## Current validation results

| Group | Actual result | Exit |
|---|---|---|
| ruff | All checks passed! | 0 |
| skill_ruff | All checks passed! | 0 |
| full | 1181 passed in 340.52s (0:05:40) | 0 |
| focused | 99 passed in 36.97s | 0 |
| B1 | 260 passed in 123.07s (0:02:03) | 0 |
| B2 | 162 passed in 54.27s | 0 |
| AC_B2_001 | 31 passed in 22.83s | 0 |
| B3 | 68 passed in 5.72s | 0 |
| B4 | 121 passed in 12.86s | 0 |
| B5 | 56 passed in 18.58s | 0 |
| B6 | 26 passed in 1.21s | 0 |
| B7 | 17 passed in 0.81s | 0 |

Required full commands were executed exactly:

```text
python -m ruff check scripts modules tests
python -m ruff check skills/fe-vasp-incar-custodian/scripts/incar_custodian.py
python -m pytest -o addopts= -q
git diff --check
```

Required focused command:

```text
python -m pytest -o addopts= -q tests/test_alpha_fe_bulk_submission.py tests/test_residual_parser_ownership.py tests/test_incar_custodian_cli.py tests/test_aqcat25_calibration.py tests/test_scheduler_mutation_ownership.py tests/test_scientific_claim_authority.py
```

Every B1–B7 group command, UTC start, elapsed time, exit code and log digest is in JSON. Full count 1181 equals the repair reference and has no failed/skipped/disappeared tests; the preceding audit’s 1128 was an earlier candidate. Focused count 99 reflects the six files requested here (not the repair report’s differently composed 101-test focus). Overlapping reruns are not new unique tests. First independent program: 28/28 expected behaviors. Extra probes include five passing NEB/CI-NEB source-bound checks and scanner robustness, two successfully reproduced defects, and the separately corrected persistence case. Do not interpret a defect-reproduction script’s exit 0 as repository acceptance.

## Exact-candidate cross-platform CI

[GitHub Actions run 34441151519](https://github.com/q2214299493/sbq123/actions/runs/34441151519) reports head `9bf950b09b965ea832148fb3ad0f44625492652e`, status `completed`, conclusion `success`. This is the candidate’s push run, not the future audit-report commit.

| Job | ID | OS | Python from job log | Conclusion |
|---|---|---|---|
| engineering (windows-latest) | 102756284821 | Windows Server 2025 | 3.11.9 | success |
| engineering (ubuntu-latest) | 102756284911 | Ubuntu 24.04 | 3.11.16 | success |
| validate | 102756284947 | Ubuntu 24.04 | 3.11.16 | success |
| wheel (ubuntu-latest) | 102756284957 | Ubuntu 24.04 | 3.11.16 | success |
| wheel (windows-latest) | 102756284995 | Windows Server 2025 | 3.11.9 | success |

Ubuntu validate ran all 1181 tests (156.55 s). Engineering Ubuntu/Windows each ran 263 tests (23.76 s / 45.42 s). The Windows engineering list does **not** include alpha submission, residual parser or scheduler-ownership focused files. Those new cases are evidenced by **LOCAL_WINDOWS_VALIDATION**, Windows 11 / Python 3.13.9, the exact focused 99-test run above. Windows CI uses Python 3.11.9; Ubuntu CI uses 3.11.16. No workflow was modified. Exact job commands and log digests are embedded in JSON.

## Fresh release artifact

`python -m scripts.validate_release --source C:/Users/86177/AppData/Local/Temp/sbq123-closeout-20260910 --output C:/Users/86177/AppData/Local/Temp/sbq123-closeout-evidence-20260910/release` exited 0.
Wheel `sbq_catalyst_agent_workflow-0.1.0-py3-none-any.whl`; SHA-256 `ca7c529a91a34d97f2c1ed019ac70c750c087062ebc3b4bcd7081af1a6764bce`; 286 members; 60 resources.
All wheel members were inspected and are inventoried with individual digests in JSON. Alpha-Fe and calibration wheel bytes were compared to the locked candidate Git blobs and match exactly. The build exported only the clean candidate Git index via checkout-index before any new audit report existed; untracked test outputs were not build inputs.
Fresh wheel/editable venvs ran outside the repository with PYTHONPATH and PYTHONHOME stripped by the release command owner. All nine console help entrypoints exited 0; 60 config/registry-migration/retrieval-schema resources matched across installations. Optional ASE/pymatgen/Sella/ML dependencies were absent in these minimal installs; the supported core probes still passed. Repository-only operations failed explicitly with REPOSITORY_CONTEXT_REQUIRED (expected exits 1/2). Parity passed; each mock smoke returned scientific_acceptance=false, external_actions=0 and schema_version=9.
No private-key marker, real POTCAR/WAVECAR/CHGCAR, production database, model-weight file, calculation output or runtime state appeared in the reviewed wheel allowlisted members. The tracked source scan covered 1309 files / 8,214,978 bytes with no sensitive filename/key-marker hit. These are scoped artifact checks, not a proof against every possible encoded secret.

## Scientific freeze, compatibility, documentation and state

AST comparisons prove alpha CASES, write_incar, write_kpoints and summary unchanged from a24bda4. ENCUT/KPOINTS/ISMEAR/SIGMA/EDIFF/EDIFFG/NELM/MAGMOM/ISPIN/fixed-atom settings, NEB/DIMER/VFA standards, final-energy convention, registry schema, B3 promotion policy and B7 resources have no incremental scientific change. Canonical execution and claim owners are byte-identical. Current tests support unchanged behavior; the diff check establishes that no scientific setting was edited. The preserved alpha summary remains a diagnostic report, not scientific acceptance authority.

- --submit now requires a reviewed per-case manifest AND current B1 authorization; manifest is routing only.
- run.lsf -> script.lsf is an explicit reviewed byte-preserving migration; setup refuses existing run.lsf.
- POTCAR.spec records identity metadata, never includes actual potential contents.
- Canonical immutable reservation and submission_record.json replace submitted.jobid; old markers require reviewed reconciliation.
- Cases are independent canonical submissions, not an atomic multi-job transaction. Scientific input generators and energy summary convention remain unchanged.

Readiness was generated twice read-only; both objects are identical and match candidate readiness JSON and rendered Markdown. Code supports schema 9; production schema is NOT_VERIFIED_IN_B6, not inferred from code. Affected module README and repair-report links have no broken targets.
Eight SKILL frontmatters remain UNSUPPORTED_FRONTMATTER in the existing document classifier; all have no broken local link. Their operational role is routing/advice under repository module/config authority, not independent scientific or execution authority. Exact names/classifier errors are in JSON. The classifier was not altered.
Read-only repo-state audit exited 1: one managed_projection_drift at docs/06_MODULE_MAP.md#module_row:transition_state_search, one review_required, zero warnings. tasks/current_task.md records earlier Dimer monitoring, not this user-authorized isolated audit. No sync, supersede, backlog edit, task edit or historical event rewrite was performed.

## Disposition and evidence boundaries

- Four known issues: CLOSED. New open findings: P0=0, P1=1 (blocking), P2=1 (nonblocking by itself).
- Merge-blocking missing verification items: 0. Production-only/unresolved dependency/document limitations are listed separately, not mislabeled as proved source bugs.
- CODE_MERGE_READINESS: NOT_READY_TO_MERGE because AC-CLOSEOUT-B1-001 is reproduced and remains open.
- PRODUCTION_OPERATION_READINESS: UNVERIFIED. DEVELOPMENT_WORKSPACE_SYNC and LIVE_STATE_RECONCILIATION: NOT_PERFORMED. External scientific actions: 0.
- Only this Markdown and its companion JSON are task-owned tracked outputs. Old failed audits are intact. Publish the truthful audit-only commit; no merge, main update, deployment, development synchronization or follow-on repair.
The conclusion is limited to the locked candidate, inspected paths and stated software environments. It is not a guarantee of absence of other bugs. The companion JSON embeds runnable key probes, their synthetic-input descriptions, error types, expected/actual outcomes, mock dispatch counts, full inventories and log digests; local temp paths are not the only retained evidence.

Prepublication checks: git status showed only these two new reports; unstaged/staged whitespace checks and document links exited 0. A fresh remote candidate-ref query still matched the locked SHA. The final staged check is repeated before commit; the candidate ref is checked again immediately before push.
