# Complete Independent B1-B7 Acceptance Rerun

Candidate: `a050fe28b25f1fc5ee91f5e7e3fb7fc1150a2157`; tree: `5cfd613ee0d5e315848046a962733aff1300aad8`.

**CODE_MERGE_READINESS = NOT_READY_TO_MERGE**

**PRODUCTION_OPERATION_READINESS = UNVERIFIED**

One P0 blocker is independently reproduced: the maintained alpha-Fe campaign has a second, nonexclusive submission path. AC-B2-001 itself passes its independent reproduction. Full/focused software tests, fresh wheel checks and exact-candidate CI pass, but do not protect this legacy path. Two residual parser issues are nonblocking P2. No source was repaired.

## Isolation and historical evidence

Repository: `q2214299493/sbq123`; candidate branch: `codex/ac-b2-001-scientific-claim-authority`; audit branch: `codex/b1-b7-final-acceptance-rerun`.

Start: `2026-09-10T04:29:39.182801+00:00`; completion: `2026-09-10T04:48:46.748757+00:00`. OS: `Windows-11-10.0.26200-SP0`; local Python `3.13.9`; CI Python 3.11.

Isolated source: `C:\Users\86177\AppData\Local\Temp\sbq123-acceptance-rerun`. Scratch, logs, new release export, venvs and synthetic fixtures live under `C:\Users\86177\AppData\Local\Temp\b1b7-rerun-evidence` or system temporary test directories, outside `C:/Users/86177/Desktop/work`. The dirty development checkout was only inspected. No reset, clean, stash, merge, main update or state reconciliation.

Fetched candidate ref matched the expected exact SHA before creating the disposable worktree. Failed audit `fad1d32607723c851c457a5fb6fa85898cdc1edf` is the repair parent. Both original failed acceptance blobs are unchanged; the AC repair report remains unchanged. Only the two requested rerun reports are intentional tracked changes.

## Ancestry and inventory

Main and merge base: `5c5fed9b4a0691a893af3d03eaae10636999aa85`. All requested remote tips are ancestors:

| Branch | Actual SHA | Ancestor |
|---|---|---|
| `origin/codex/b1-execution-lifecycle` | `b1c59addbc7d7be64347db66a201dc5841404341` | True |
| `origin/codex/b2-scientific-contract` | `3d9e9070e48a6cb65d9b4c0334adb4243f36dd0c` | True |
| `origin/codex/b3-evidence-ml-governance` | `9f4332f082d4e286ce43c5a137a62ac1e30fa441` | True |
| `origin/codex/b4-registry-state-management` | `fbbb7bb26d28867d9766cc7fca84077fa54cf3d6` | True |
| `origin/codex/b5-architecture-boundaries` | `3a1bb3f461147a7dc9b5df5efca89de621d27f38` | True |
| `origin/codex/b6-documentation-data-governance` | `93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a` | True |
| `origin/codex/b7-release-environment` | `7a0b745df96de2762a6f289e9eeda1a3c298fe9d` | True |
| `origin/codex/b1-b7-final-acceptance` | `fad1d32607723c851c457a5fb6fa85898cdc1edf` | True |
| `origin/codex/ac-b2-001-scientific-claim-authority` | `a050fe28b25f1fc5ee91f5e7e3fb7fc1150a2157` | True |

Complete main-to-candidate commit chain (actual parents included):

```text
4a8c3bbb4c2ac6254c462f39dccaa7ebaf1c773a 5c5fed9b4a0691a893af3d03eaae10636999aa85 refactor: reserve and bind execution lifecycle
1ec8f3e787fd52353fa70419a206d764c07ae13a 4a8c3bbb4c2ac6254c462f39dccaa7ebaf1c773a docs: correct task publication target to sbq123
b90ef54a0d1a6a094c0a0a616966038be744b277 1ec8f3e787fd52353fa70419a206d764c07ae13a fix: close B1 execution lifecycle and CI contracts
b1c59addbc7d7be64347db66a201dc5841404341 b90ef54a0d1a6a094c0a0a616966038be744b277 refactor: restore pure execution decision ownership for B1.2
99b82eab15aaf22ef7dc880af54e77314eb49b53 b1c59addbc7d7be64347db66a201dc5841404341 refactor: harden scientific contracts and VASP final-state validation
3d9e9070e48a6cb65d9b4c0334adb4243f36dd0c 99b82eab15aaf22ef7dc880af54e77314eb49b53 fix: bind DIMER VFA acceptance and reject nonfinite barriers
9f4332f082d4e286ce43c5a137a62ac1e30fa441 3d9e9070e48a6cb65d9b4c0334adb4243f36dd0c refactor: harden evidence lifecycle and ML data governance
e4465aa9e1521a3b9ec3dabba40badb5f17d772a 9f4332f082d4e286ce43c5a137a62ac1e30fa441 refactor: harden registry transactions and state management
fbbb7bb26d28867d9766cc7fca84077fa54cf3d6 e4465aa9e1521a3b9ec3dabba40badb5f17d772a fix: close registry batch and compatibility review contracts
3a1bb3f461147a7dc9b5df5efca89de621d27f38 fbbb7bb26d28867d9766cc7fca84077fa54cf3d6 refactor: enforce architecture boundaries and capability ownership
93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a 3a1bb3f461147a7dc9b5df5efca89de621d27f38 refactor: establish documentation and data governance
03739665465d8548e22d154aa2a8d4209f04983c 93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a refactor: harden release packaging and cross-platform reproducibility
7a0b745df96de2762a6f289e9eeda1a3c298fe9d 03739665465d8548e22d154aa2a8d4209f04983c refactor: harden release packaging and cross-platform reproducibility
fad1d32607723c851c457a5fb6fa85898cdc1edf 7a0b745df96de2762a6f289e9eeda1a3c298fe9d audit: verify B1-B7 whole-repository acceptance
a050fe28b25f1fc5ee91f5e7e3fb7fc1150a2157 fad1d32607723c851c457a5fb6fa85898cdc1edf fix: bind TS and barrier claims to current scientific evidence
```

Inventory: **66 added, 174 modified, 0 deleted, 0 renamed**. No unexpected maintained source/test/schema/protocol/config/historical-evidence deletion. Full 240-path name/status inventory is in the [JSON companion](B1_B7_acceptance_rerun.json), `candidate.inventory`.

## Source integrity

Scanned filenames and contents of all **1303 tracked files / 7,960,966 bytes** for private keys, common tokens/credential assignments, authentication files, POTCAR/WAVECAR/CHGCAR, databases, weights/checkpoints and generated build/test clutter. No suspicious name/content match; no binary tracked file. The only file over 200 KB is `configs/public_source_snapshot.json` (368,187 bytes), a source-publication manifest, unchanged from main.

Reviewed small input structures and historical source snapshots are intentional publication material; no calculation path changed from main. Complete tracked-byte heuristic scanning cannot guarantee absence of arbitrarily encoded secrets. No private-key/POTCAR content was read or manipulated.

## Exact validation

`python -m ruff check scripts modules tests`: exit **0**, All checks passed.

`python -m pytest -o addopts= -q`: exit **0**, **1128 passed in 309.08s (0:05:09)**. Collected/executed 1128; failed 0; skipped 0. Process wall time 311.63s. Prior repaired result 1128 passes; count difference 0; no test disappearance.

`git diff --check`: exit **0**.

All focused groups ran after the complete suite:

| Group | Exact result | Exit |
|---|---|---|
| B1 | 246 passed in 118.26s (0:01:58) | 0 |
| B2 | 162 passed in 53.90s | 0 |
| AC_B2_001 | 31 passed in 20.80s | 0 |
| B3 | 68 passed in 5.27s | 0 |
| B4 | 121 passed in 11.98s | 0 |
| B5 | 56 passed in 11.08s | 0 |
| B6 | 26 passed in 1.14s | 0 |
| B7 | 17 passed in 0.78s | 0 |

Focused total: **727 passed** (group executions, not extra test definitions). Exact commands:

```text
python -m pytest -o addopts= -q tests/test_execution_lifecycle.py tests/test_neb_execution_gate.py tests/test_execution_gate_compatibility.py tests/test_execution_backends.py tests/test_gpu_execution_lifecycle.py tests/test_artifact_io.py tests/test_alpha_fe_bulk_submission.py
```

```text
python -m pytest -o addopts= -q tests/test_b2_scientific_contract.py tests/test_b21_scientific_acceptance.py tests/test_ts_strategy_engine.py
```

```text
python -m pytest -o addopts= -q tests/test_scientific_claim_authority.py
```

```text
python -m pytest -o addopts= -q tests/test_b3_evidence_governance.py tests/test_b3_ml_governance.py
```

```text
python -m pytest -o addopts= -q tests/test_registry_write.py tests/test_b4_registry_governance.py tests/test_b4_state_governance.py tests/test_registry_schema.py tests/test_state_manager.py
```

```text
python -m pytest -o addopts= -q tests/test_b5_architecture_boundaries.py tests/test_code_structure.py tests/test_repository_contracts.py
```

```text
python -m pytest -o addopts= -q tests/test_b6_governance.py
```

```text
python -m pytest -o addopts= -q tests/test_b7_release.py
```

## Independent AC-B2-001 reproduction

A separate audit program (retained verbatim in JSON `reproduction_programs`) calls real `decide_execution`, `build_decision` and `require_action`. It reuses synthetic fixture constructors and real maintained DIMER/VFA/NEB science; no scientific verifier is mocked.

The original trusted-looking boolean-only dictionary, directly and as a hash-bound fake JSON file, returns `NEEDS_CURRENT_TS_VALIDATION_EVIDENCE`; never VALIDATED_TS, TS claim false, both claim actions denied. Real fully bound DIMER evidence initially permits only APPROVE_TS_CANDIDATE without execution authorization or new connectivity requirements. SUBMIT/STOP/CONTINUE and REPORT_FINAL_BARRIER remain denied.

Old gates then reject Grade-C summary, VFA OUTCAR/POSCAR/review/handoff, DIMER final structure/analysis, and NEB contract/connectivity-branch changes. The summary remains byte-identical in each underlying-source test. **10 independent scenarios pass**. Maintained AC tests add cross-object/soft-review/custom-review/persistence cases: **31 passed**. The downstream matched-static owner alone establishes reportable barriers after current TS/result/file/job/compatibility/convention/finite checks.

## Complete acceptance matrix

| Package | Verdict | Blocking finding |
|---|---|---|
| B1: Execution Safety | FAIL | AC-RERUN-B1-001 |
| B2: Scientific Contract / VASP | PASS_WITH_NONBLOCKING_LIMITATION | None |
| AC_B2_001: Scientific Claim Closure | PASS | None |
| B3: Evidence / ML Governance | PASS_WITH_NONBLOCKING_LIMITATION | None |
| B4: Registry / State | PASS | None |
| B5: Architecture | FAIL | AC-RERUN-B1-001 |
| B6: Documentation / Data Governance | PASS_WITH_NONBLOCKING_LIMITATION | None |
| B7: Release / Environment | PASS | None |

### B1 — Execution Safety

- Inspected ScientificReadiness -> ExecutionAuthorization -> EvidenceBinding -> InputBundle -> SubmissionReservation -> SubmissionResult in the gate and canonical executor.
- Verified canonical workdir, bundle/evidence/source hashes, POTCAR/spec identity and digest/job/path checks before shell construction.
- Ran reservation concurrency, hard death/crash-after-submit, no automatic uncertain retry, stale evidence, traversal/symlink, upload/reuse full remote manifest, remote reservation and scoped stop tests.
- Reviewed AQCat25/dual-model/MatRIS bootstrap EXIT/INT/TERM/HUP guards, realpath containment and fallback failure records; executed fake-command shell regressions.
- Searched all maintained external dispatch patterns and independently reproduced the legacy campaign race.

Current owners inspected: `scripts/ts_strategy_engine/execution_gate.py`, `scripts/ts_strategy_engine/execution_evidence.py`, `scripts/neb_agent/submission.py`, `scripts/artifact_io.py`, `scripts/aqcat25_mz73_env.sh`.

Actual evidence: Canonical executor and 246 focused tests pass; separate legacy reproduction reaches two fake dispatches for one case.

Remaining limitation: Canonical B1 correctness does not cover the legacy convergence executor. No real scheduler was used.

### B2 — Scientific Contract / VASP

- Inspected explicit latest-started/latest-completed/final-target SCF semantics; tested newer incomplete cycles, NELM exhaustion, truncated and multi-ionic/appended outputs.
- Reviewed current authoritative INCAR semicolon/comment/whitespace/duplicate handling and all maintained caller matches; residual raw MAGMOM parser recorded.
- Verified raw and already-normalized contracts both reach _normalize_contract_payload; hash checks cannot replace finite, positive-kmesh/ENCUT, atom-map/index-base and required-text validation.
- Inspected chemical_events/family_event_matches and C-O/C-C tests; atom-renumbered chemical events, structure similarity and exact result identity remain distinct.
- Ran B2/B2.1, real TS persistence, cross-object DIMER/VFA, frequency-only denial, finite/nonnegative barrier and valid negative-energy regressions.
- Compared configs, protocol bodies and parameter-related code diffs against main.

Current owners inspected: `scripts/vasp_result_gate.py`, `scripts/neb_agent/utils_vasp.py`, `scripts/scientific_validation.py`, `scripts/ts_strategy_engine/contract.py`, `scripts/ts_strategy_engine/fingerprint.py`, `scripts/ts_strategy_engine/strategy.py`, `scripts/ts_validation/analyze_vfa.py`, `scripts/ts_validation/validation_pipeline.py`, `scripts/ts_strategy_engine/matched_static_evidence.py`.

Actual evidence: 162 focused tests pass. Current authoritative acceptance paths fail closed; residual metadata/raw-tag disagreements independently reproduced.

Remaining limitation: Two nonblocking P2 parser discrepancies; no accepted-science bypass demonstrated. No production scientific evidence revalidated.

### AC_B2_001 — Scientific Claim Closure

- Independently called decide_execution and build_decision with boolean-only DIMER/Grade-A summaries, including a hash-bound fake summary file: both fail closed.
- Built real synthetic DIMER and NEB fixtures via maintained scientific owners; current APPROVE_TS_CANDIDATE works with no execution authorization.
- Old require_action rejects Grade-C summary, VFA OUTCAR/POSCAR/review/handoff, DIMER final structure/analysis, NEB contract and connectivity-branch mutations.
- Confirmed underlying-source mutation revokes claims while the validation summary stays byte-identical.
- Inspected source_bindings_valid reuse and use-time gate replay, DIMER pipeline/NEB-VFA/connectivity delegation, unchanged DIMER connectivity policy and downstream matched-static owner.
- Ran real TS registration and barrier/template persistence regressions; stale gate fails before insertion and barrier booleans cannot authorize reporting.

Current owners inspected: `scripts/ts_strategy_engine/scientific_claims.py`, `scripts/ts_strategy_engine/execution_gate.py`, `scripts/ts_validation/analyze_vfa.py`, `scripts/ts_validation/validation_pipeline.py`, `scripts/ts_strategy_engine/evidence.py`.

Actual evidence: 31 maintained focused tests plus 10 independently authored scenario checks pass. Positive current TS permits only APPROVE_TS_CANDIDATE.

Remaining limitation: Synthetic sources and supplied review records; production evidence/reviewer identity outside the established evidence contract is not certified.

### B3 — Evidence / ML Governance

- Reviewed every IMPORTED -> SCHEMA_VALID -> SOURCE_VERIFIED -> CONTENT_BOUND -> REVIEWED -> TRANSFERABLE check; supplied booleans/stage flags do not promote evidence.
- Source immutable-reference/snapshot hash, extracted span/content hash, reviewer/time/subject and target compatibility are checked separately.
- Inspected embedding model/source/content provenance, finite dimensions/rectangular arrays, zero-norm rejection and overflow-safe cosine.
- Inspected model/version/input/time/uncertainty provenance, explicit unavailable uncertainty and candidate-only prediction restrictions; accepted-registry rejection tested.
- Reviewed train/validation/test source-row, calculation, reaction and permutation-invariant structure exclusions; descriptor collisions block splits rather than prove scientific equivalence.
- Ran actual evidence promotion, retrieval ranking, registry rejection, fake model producer and training-preflight paths.

Current owners inspected: `scripts/adsmind_lite/evidence_lifecycle.py`, `scripts/catalysis_retrieval/records.py`, `scripts/catalysis_retrieval/ranking.py`, `scripts/prediction_provenance.py`, `scripts/matris_training_exclusions.py`, `scripts/matris_training_data.py`, `scripts/registry_acceptance.py`.

Actual evidence: 68 focused tests pass; no automatic retrieval/prediction-to-accepted-fact route found in inspected acceptance paths.

Remaining limitation: Calibration metadata P2 recorded. No real training, inference or scientific benchmarking performed.

### B4 — Registry / State

- Reviewed complete planning in a snapshot, plan/batch hashes, database identity/fingerprint, explicit approval and BEGIN IMMEDIATE apply.
- Tested invalid input before mutation, changed plan, stale DB, transaction rollback, immutable receipts, duplicate apply and idempotent replay.
- Verified omitted rows normalizes to rows={}; status-only validate/plan/approved apply/replay succeeds and stale expectations fail.
- Verified immutable compatibility revisions, old calculation revision retention and timezone-aware review timestamps for both APIs.
- Inspected immutable event/result/file/review/TS/barrier/template guards and job transition/recovery history; ran migration, rollback and incompatible-schema checks on temporary SQLite.
- Normal open_registry (including legacy migrate=True) validates schema but does not silently migrate. State crash/receipt/rollback/event regressions use synthetic state only.

Current owners inspected: `scripts/registry_mutations.py`, `scripts/registry_transactions.py`, `scripts/registry_connection.py`, `scripts/registry_compatibility.py`, `scripts/registry_schema.py`, `scripts/state_manager/`, `modules/calculation_registry/migrations/009_registry_governance.sql`.

Actual evidence: 121 focused tests pass on temporary registry/state fixtures.

Remaining limitation: Live task reconciliation and deployed registry schema remain unverified; existing managed projection drift is recorded separately.

### B5 — Architecture

- Reconstructed AST graph of 221 script modules / 759 internal edges including function-local imports; reviewed current infrastructure/registry dependency closure and cycle tests.
- Checked no domain-to-CLI or shared-infrastructure-to-TS direction, no CLI SQL in maintained adapters, import-only facades and no new sys.path hacks.
- Verified one gate, execution authorization validator, registry connection, evidence lifecycle and resource resolver; execution_gate remains 150 lines.
- scientific_claims is a narrow application delegation boundary with no SQL/scheduler/submission/VFA parsing/DIMER scientific rules.
- Complete dispatch search and independent race disprove repository-wide sole-submit-owner assertion; the exact-string B5 test misses the legacy executor.
- Reviewed unsupported catalyst profiles, zero-incoming newly added modules against console/build/CI registrations, and all residual duplicate parser candidates.

Current owners inspected: `tests/test_b5_architecture_boundaries.py`, `scripts/ts_strategy_engine/scientific_claims.py`, `scripts/registry_connection.py`, `scripts/runtime_resources.py`, `scripts/adsmind_lite/site_detection.py`.

Actual evidence: 56 focused tests pass but the second working submit executor is independently confirmed.

Remaining limitation: Static import graphs are not proof of every dynamic route. Legacy executor and residual parser ownership need separate closure.

### B6 — Documentation / Data Governance

- Read the single DOCUMENT_GOVERNANCE authority model and distinctions among code state, dated observations, history, accepted science, predictions and unverified production.
- Verified supported code schema 9 versus NOT_VERIFIED_IN_B6 production, timestamped scheduler observations and historical filename-independent authority.
- Generated readiness twice in a fresh external source copy: byte-identical and equal to checked-in outputs.
- Verified tests/status do not promote science; kinetic_data stays Planned and downstream thermochemistry/network/kinetics/KMC/reactor/sensitivity modules stay Blocked.
- Audited data_governance classes and prediction paths; directory classification cannot establish scientific acceptance.
- Checked links in all 211 tracked Markdown files: zero broken links. All 203 classifier-supported documents were checked; seven current/reference/generated views have no wording findings.

Current owners inspected: `docs/DOCUMENT_GOVERNANCE.md`, `configs/data_governance.yaml`, `scripts/document_governance.py`, `scripts/generate_capability_readiness.py`.

Actual evidence: 26 focused tests pass; two readiness generations are byte-identical, match checked-in views and retain scientific/production separation.

Remaining limitation: Eight SKILL.md documents have skill frontmatter unsupported by this document classifier. Links were checked; classification was not marked PASS. Live state not reconciled.

### B7 — Release / Environment

- Fresh actual wheel exported from the candidate index, built and installed into a clean normal-wheel venv and separate editable venv outside the repository.
- Verified outside-repository cwd, cleared PYTHONPATH/PYTHONHOME, all nine console scripts and 60 runtime resources including schema/migration SQL and retrieval schemas.
- Verified REPOSITORY_CONTEXT_REQUIRED errors, explicit-root tools, editable/wheel parity and synthetic smoke with scientific_acceptance=false.
- Inspected every one of 286 wheel members; all 221 Python members are byte-identical to the candidate Git blobs.
- Queried exact candidate GitHub validate/Ubuntu, engineering/Windows+Ubuntu and wheel/Windows+Ubuntu jobs; all five succeeded with configured Python 3.11.

Current owners inspected: `scripts/validate_release.py`, `scripts/release_environment.py`, `scripts/release_smoke.py`, `scripts/runtime_resources.py`, `configs/release_resources.json`, `.github/workflows/state-manager.yml`.

Actual evidence: 17 focused tests pass; fresh release exit 0/PASS/parity true; all five exact-candidate CI jobs success.

Remaining limitation: Packaging includes the known legacy executor source; release success cannot remove its source-level B1 blocker or establish real HPC/GPU operation.

## Fresh release artifact and remote CI

Command: `python -m scripts.validate_release --source C:/Users/86177/AppData/Local/Temp/sbq123-acceptance-rerun --output C:/Users/86177/AppData/Local/Temp/b1b7-rerun-evidence/fresh-release`. Exit 0; PASS; parity true; process duration 69.25s.

Wheel: `sbq_catalyst_agent_workflow-0.1.0-py3-none-any.whl`; SHA-256 `540ab56281d78efe55fffd9df7804bd695c1968595eaa61951842718742cde9a`; **286 members / 60 resources / 221 Python members exactly matching candidate blobs**. Every member checked against package allowlist and excluded-artifact patterns. Registry/migration SQL and retrieval schemas present.

Nine console scripts: `capability-readiness`, `catalysis-search`, `catalysis-validate`, `document-governance`, `registry-init`, `registry-promote`, `registry-write`, `repo-state`, `ts-strategy`.

All help probes exit 0 in wheel/editable clean venvs, outside repository cwd, with PYTHONPATH/PYTHONHOME removed. Context-only calls produce REPOSITORY_CONTEXT_REQUIRED; explicit-root tools succeed. Smoke: schema 9, two synthetic inserted rows, idempotent true, scientific_acceptance false, external_actions 0.

Independent public GitHub API: run [34436758260](https://github.com/q2214299493/sbq123/actions/runs/34436758260) for exact head `a050fe28b25f1fc5ee91f5e7e3fb7fc1150a2157`, completed/success. gh CLI lacked authentication; public API succeeded. Python 3.11 verified from exact candidate workflow.

| Job | Platform | Status | Conclusion | Job ID |
|---|---|---|---|---|
| validate | ubuntu-latest | completed | success | 102743331109 |
| engineering (windows-latest) | windows-latest | completed | success | 102743331297 |
| engineering (ubuntu-latest) | ubuntu-latest | completed | success | 102743331312 |
| wheel (windows-latest) | windows-latest | completed | success | 102743331342 |
| wheel (ubuntu-latest) | ubuntu-latest | completed | success | 102743331467 |

## Scientific parameter preservation

**37 existing config files are byte-identical to main**, including production, backend, reaction-family, NEB/DIMER and frequency/connectivity policies. Changed configs only add prediction-provenance schema fields, data classification and package resource enumeration. Calculation paths are unchanged.

Method, TS validation and provenance protocol bodies are byte-identical after removing only B6 classification frontmatter. Parameter-related code diffs were inspected for ENCUT, KPOINTS/kmesh, ISMEAR, SIGMA, EDIFF/EDIFFG, NELM, MAGMOM, fixed masks, vacuum, LDIPOL, image/climb/spring policy, DIMER/frequency/connectivity thresholds, reaction families and final-energy conventions. Differences are parser/finite/current-evidence validation or owner/resource relocation. MatRIS compatibility values moved unchanged; VFA retains its threshold conjunction. Release-smoke constants are synthetic. **No unexplained scientific value change found.**

## Findings

| ID | Severity | Blocking | Finding |
|---|---|---|---|
| AC-RERUN-B1-001 | P0 | True | Maintained alpha-Fe campaign bypasses B1 and dispatches twice under concurrency |
| AC-RERUN-B2-001 | P2 | False | Custodian raw MAGMOM lookup retains a divergent INCAR parser |
| AC-RERUN-B2-002 | P2 | False | Calibration OUTCAR metadata retains historical completion booleans |

### AC-RERUN-B1-001 (P0)

**Location:** scripts/convergence/setup_alpha_fe_bulk_smearing.py:124 submit; 137-159 check/write/dispatch; 177-179 receipt/remove; main --submit

**Root cause:** A separate public submit implementation checks marker/attempt existence, then uses atomic replacement instead of exclusive reservation creation. It calls subprocess.run([bsub, run.lsf]) without the gate, execution authorization, backend restriction or input/evidence/POTCAR binding. Atomic replacement does not serialize competing submitters.

**Reproduction:** Create one temporary case/run.lsf only. Set module WORKDIR and CASES to the fixture. Replace subprocess.run with a fake returning distinct job IDs. Synchronize two threads immediately before the unchanged _write_json_atomic, after both have passed absence checks. Two concurrent real submit() calls reach fake bsub for the same case without any gate/authorization/bundle. This synchronization selects a possible race schedule; it does not replace reservation logic.

**Impact and scope:** On a configured scheduler host this maintained entry can create duplicate expensive VASP jobs and bypass the B1 contract. One caller returns; the other raises FileNotFoundError deleting the shared attempt after both dispatches. P0 denotes demonstrated duplicate external-execution risk; no real job was submitted during the audit.

**Origin:** Pre-existing in main; B2 updated its INCAR check but left this entry operational. modules/convergence_workflow/README.md lists it and tests/test_alpha_fe_bulk_submission.py exercises it; it is not archived/dead.

**Separate repair recommendation:** Separately close or route this existing campaign submission entry through the established B1 boundary, preserving scientific settings. Add fake-command concurrent/no-authorization regressions across all maintained dispatch forms. Do not add another executor.

**Why green tests missed it:** B5 counts only the exact string bsub script.lsf and misses the list [bsub, run.lsf]. Legacy tests cover sequential markers and timeout recovery but no concurrent/execution-authorization boundary. Canonical NEB executor tests remain passing.

Observed **two fake bsub dispatches** for one case and two callers, with no gate/authorization artifacts. One returned and one raised FileNotFoundError after dispatch. Runnable audit reproduction and exact outcomes are in JSON. No real scheduler action occurred.

### AC-RERUN-B2-001 (P2)

**Location:** skills/fe-vasp-incar-custodian/scripts/incar_custodian.py:46 raw_incar_value; main call at 484

**Root cause:** Independent line/equals splitting misses semicolon-separated tags after the first setting.

**Reproduction:** NELM=60; MAGMOM = 3*2.0 returns raw_incar_value(path, MAGMOM)=None; vasp_result_gate.read_incar_values(path)[MAGMOM] returns 3*2.0.

**Impact and scope:** Literal MAGMOM retention disagrees with the authoritative parser. Main INCAR loading uses pymatgen; no changed numerical spin values or accepted-science error was demonstrated. Nonblocking maintenance/format-preservation defect.

**Origin:** Pre-existing; unchanged by B1-B7/AC repair.

**Separate repair recommendation:** Use the existing INCAR owner for raw tag lookup, preserve the optional-return API, and cover semicolon/literal retention.

### AC-RERUN-B2-002 (P2)

**Location:** scripts/aqcat25_calibration.py:25 parse_final_outcar; extract_labels

**Root cause:** The force/energy extractor independently accumulates ionic_converged/normal_completion and does not reset them for a newer incomplete run.

**Reproduction:** A synthetic completed converged force/energy block followed by vasp.6 and a new incomplete Iteration 1(1) yields ionic_converged=true and normal_completion=true here. The current utils_vasp.parse_outcar owner instead reports normal_completion=false and incomplete=true.

**Impact and scope:** Direct extraction/calibration metadata can misrepresent current completion. Inspected accepted registry and active-learning/dual-model force-label paths also invoke validate_vasp_relaxation/final_scf_status, which fail closed. No accepted-result bypass is established; this is P2 rather than a claimed P1 false acceptance.

**Origin:** Pre-existing extractor; unchanged. Force/energy extraction is legitimate, but current-completion interpretation should delegate.

**Separate repair recommendation:** Preserve extraction API and delegate completion/current-cycle interpretation to the VASP owner; cover appended/truncated output through direct label extraction.

## Duplication / dead implementation / test quality

- **GENUINE_DUPLICATION**: Legacy convergence submit executor (AC-RERUN-B1-001)
- **GENUINE_DUPLICATION**: Custodian raw INCAR tag parser (AC-RERUN-B2-001)
- **GENUINE_DUPLICATION**: Calibration completion interpretation (AC-RERUN-B2-002)
- **LEGITIMATE_REVALIDATION**: Gate creation/use and persistence repeat source/identity/file/job checks at distinct trust boundaries; this is not duplicated acceptance science.
- **LEGITIMATE_REVALIDATION**: GPU bootstrap guard is mirrored so missing shared environment code still leaves failure evidence; a mirrored-guard regression checks consistency.
- **COMPATIBILITY_FACADE**: ts_strategy_engine.registry, registry_write, retrieval skill facades and preparation geometry/scope aliases delegate to one owner.
- **UNREFERENCED_REVIEW_REQUIRED**: Six new modules initially have zero static incoming edges: package __init__, retrieval CLI/validation CLI, readiness CLI, release build hook and release runner. All are resolved by package/console/pyproject/CI registrations; no newly dead module confirmed.

Additional parsers extracting different force/TOTEN/geometry quantities are distinguished from current SCF authority. Independent completion interpretation is the P2 exception above. Archived VASP2Kinetics source is historical and not selected as runtime authority. No dead-code deletion performed.

Critical tests exercise real submission/recovery, final SCF and TS persistence, evidence promotion/leakage, plan/apply/rollback/history, actual dependency graphs, readiness generation and wheel installation. The B1/B5 gap is concrete: an exact-string assertion misses the legacy list-form dispatcher and its concurrency. Passing count/helper assertions cannot prove whole-repository execution closure.

## Operational state / limitations

Read-only `python -m scripts.state_manager.cli --root . audit --phase start` exits 1: errors=1, warnings=3, review_required=4. Existing error: docs/06_MODULE_MAP.md#module_row:transition_state_search projection drift. Three warnings concern other temporary worktree ownership. Known live task reconciliation remains STATE_RECONCILIATION_REQUIRED; no current task chosen, event superseded, projection synced or history written. This operational issue alone does not decide code readiness.

Production registry deployment, scheduler status, credentials, real VASP/VTST/GPU/training and scientific performance remain UNVERIFIED. Git/API and pip are permitted non-scientific network actions. Scientific fixtures/SQLite writes are temporary. **external_scientific_actions = 0**.

## Completeness and final decision

All packages, full/focused tests, independent AC reproduction, history/source/parameter/governance checks, fresh wheel and exact-candidate CI were completed despite the blocker. No row fails because the audit stopped early. Eight skill-frontmatter classifications are explicitly unsupported, with links still checked; they are not falsely marked PASS.

Only the two requested rerun reports are intentional tracked changes. The original failed audit and repair report remain unchanged. JSON contains the same verdicts and evidence, complete commit/path inventory, source graph, test commands, CI jobs, wheel/resources and reproductions. No source repair, merge or main update.

```text
candidate_sha=a050fe28b25f1fc5ee91f5e7e3fb7fc1150a2157
full_pytest=1128 passed in 309.08s; failed=0; skipped=0
ruff=PASS
remote_ci=SUCCESS (5/5 exact-candidate jobs)
p0_count=1
p1_count=0
code_merge_readiness=NOT_READY_TO_MERGE
production_operation_readiness=UNVERIFIED
external_scientific_actions=0
```
