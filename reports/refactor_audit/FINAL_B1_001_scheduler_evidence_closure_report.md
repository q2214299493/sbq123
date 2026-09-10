---
document_class: GENERATED_CURRENT_REPORT
as_of: '2026-09-10T10:47:43.001364+00:00'
source_version: 328cfc84458ebbf33e8ffa34af14ff6803b0dcf9
source_version_role: locked repair base; final staged source hashes below
source_branch: codex/final-b1-001-scheduler-evidence-closure
source_scope: FINAL-B1-001 scheduler identity boundary and FINAL-B2-001 alpha diagnostic summary only
evidence_kind: SOFTWARE_REPAIR_VERIFICATION
production_schema_version: UNVERIFIED
governance: docs/DOCUMENT_GOVERNANCE.md
---

# FINAL-B1-001 Scheduler Evidence Boundary Closure

**FINAL-B1-001: CLOSED in this repair scope.** Malformed job IDs fail before transport in the maintained API and CLI; stored/live scheduler identities reuse the same canonical validator. Valid numeric queries remain read-only and do not require execution authorization.

**FINAL-B2-001: CLOSED in this repair scope.** Alpha-Fe static summaries use current OUTCAR evidence; incomplete cases/references cannot produce current-valid comparison metrics. No scientific settings or arithmetic formula changed.

This is a narrow repair report, not a replacement whole-repository merge-readiness audit. The previous NOT_READY_TO_MERGE report and all historical audit reports remain unchanged. No main merge or development sync was performed. No real SSH, scheduler, VASP, MPI, GPU, production database or workbook action ran; external_scientific_actions=0.

## Locked base and isolation

- Repository: q2214299493/sbq123.
- Locked audit base: `328cfc84458ebbf33e8ffa34af14ff6803b0dcf9`, verified against the remote audit branch before clone.
- Its source parent: `9e968201ac5fc5996b1c428bf9e9dc8e81434e45`.
- Repair branch: `codex/final-b1-001-scheduler-evidence-closure`.
- Fresh isolated clone: `C:/Users/86177/AppData/Local/Temp/sbq123-final-scheduler-repair-20260910`.
- External synthetic evidence/logs/release environments: `C:/Users/86177/AppData/Local/Temp/sbq123-final-scheduler-evidence-20260910`.
- No writes or synchronization to C:/Users/86177/Desktop/work. The read-only startup state audit retained the pre-existing projection drift (one error/one review request); no review choice or state transition was applied.

## Original P1 reproduction

Before edits, both real `query_lsf_job("123; bkill 456 #")` and maintained `active_learning_cli.main` with `capture-lsf-evidence --job-id=123; bkill 456 # --output <temporary>` reached a patched subprocess transport. Each captured:

```text
["ssh", "sunboquan-codex", "bjobs", "-a", "123; bkill 456 #"]
```

Only subprocess transport was faked; no SSH or scheduler executable ran. The exact vector is remote-command argument joining: the malicious suffix becomes a second remote shell command even with local shell=False. A subsequent parse or schema failure is too late to prevent dispatch. The prior independent audit contains the inert local-shell proof; this repair freshly reproduced the vulnerable API and CLI argv before changing them.

The same pre-fix probe called the real alpha summary with an older completion followed by a new incomplete run. It produced finished=True while the canonical parser reported normal_completion=False.

## Canonical identity boundary

`query_lsf_job` now uses `require_job_id(str(job_id).strip())` before backend lookup, argv construction and subprocess. Every command/metadata reference uses the validated returned ID. The unchanged canonical owner is `scripts.ts_strategy_engine.execution_path_rules.require_job_id`; its original `[1-9][0-9]{0,19}` policy is unchanged. No second regular expression, job-ID parser, execution gate or executor was added.

`_parse_lsf_bjobs` validates the expected identity with that same owner before matching output rows. Stored evidence passes schema/backend/hash checks and this canonical identity check before a live callback can be reached. Stored identities are already canonical and are not silently normalized. `verify_lsf_evidence_live` applies the existing stored-evidence validator to the returned live evidence too, retaining backend, identity, required-state and stdout/hash consistency. No parallel planning or validation implementation exists.

SSH argument review: server_alias is obtained only from the configured backend loader (the fixed candidate configuration selects sunboquan-codex); bjobs and -a are fixed literals; job_id is canonical numeric text. Stage remains schema-validated metadata and never enters argv. A deliberately invalid stage cannot inject commands: the observed argv remains a single fixed numeric bjobs query, after which existing schema validation rejects the metadata. This review does not treat arbitrarily modified backend configuration or custom external executables as trusted user input.

## Necessary import-boundary correction

A direct import of the canonical owner into scheduler_evidence would otherwise create this dependency cycle:

```text
scheduler_evidence -> execution_path_rules -> execution_evidence -> scheduler_evidence
```

The canonical module previously mixed path/ID rules with higher-level decisions. To preserve its public validator location and keep the graph acyclic, exactly three existing decision functions were transferred without AST changes to the existing `execution_submission_rules` owner: `blocking_decision`, `progress_decision`, `dimer_progress_decision`. Their required existing imports moved with them; execution_gate only changes the import source. The path/ID validators, INITIAL_SUBMISSIONS and ScientificReadiness alias remain in their original owner. All four validators have identical ASTs to the locked base.

All imports/CLI/tests/docs were searched before the move: execution_gate was the only maintained consumer of those three helper functions, and no documented external helper API was found. Public execution_gate APIs and decision data are preserved. No lazy-import trick, compatibility executor or duplicate validator was introduced. Existing full import-graph acyclicity and architecture tests pass without changing their limits or weakening assertions. The gate remains below its existing 160-line limit.

## API and CLI malicious-ID matrix

Each row was exercised through both the maintained API and CLI. Every rejected CLI call leaves its requested output absent. The following external post-fix probe duplicates the regression matrix with only transport faked; the committed tests also cover it.

| Input (escaped where needed) | API result | API dispatches | CLI result | CLI dispatches | CLI evidence created |
|---|---|---:|---|---:|---|
| `"123; bkill 456 #"` | ValueError | 0 | ValueError | 0 | No |
| `"123 && bsub job.lsf"` | ValueError | 0 | ValueError | 0 | No |
| `"123 &#124; bkill 456"` | ValueError | 0 | ValueError | 0 | No |
| `"123\nbkill 456"` | ValueError | 0 | ValueError | 0 | No |
| `"$(bkill 456)"` | ValueError | 0 | ValueError | 0 | No |
| `"`bkill 456`"` | ValueError | 0 | ValueError | 0 | No |
| `"123 456"` | ValueError | 0 | ValueError | 0 | No |
| `"-1"` | ValueError | 0 | ValueError | 0 | No |
| `"0"` | ValueError | 0 | ValueError | 0 | No |
| `"abc"` | ValueError | 0 | ValueError | 0 | No |
| `""` | ValueError | 0 | ValueError | 0 | No |
| `" \t "` | ValueError | 0 | ValueError | 0 | No |
| `"01"` | ValueError | 0 | ValueError | 0 | No |
| `"999999999999999999999"` | ValueError | 0 | ValueError | 0 | No |
| `"\uff11\uff12\uff13"` | ValueError | 0 | ValueError | 0 | No |

Positive API cases: 1, 123, 99999999999999999999, surrounding whitespace around 123 and integer 123 (existing str/strip compatibility). Each makes exactly one fake numeric bjobs query, parses DONE and returns the existing scheduler_job_evidence schema with bound stdout hash. The valid CLI case writes the same evidence it prints, and creates no gate/authorization/reservation file. The independent post-fix probe recorded valid_query_dispatches=1 and valid_cli_dispatches=1.

Stored evidence tests mutate the ID and its stdout/hash together, so hash consistency cannot hide an invalid identity. All 15 variants are rejected before any live callback. A valid stored record triggers one legitimate fake read-only recheck; an invalid returned live identity is rejected. Parser-level identity tests use the same 15 cases. Timeout, unknown-status and configured-backend regressions remain unchanged.

## Alpha summary current-output boundary

Each static case calls the existing `parse_outcar` exactly once. finished requires current normal completion, a complete latest target, explicit current electronic convergence and no recognized fatal evidence. It never requires ionic relaxation for the static calculation. Missing files, missing convergence, newer runs/cycles, truncated cycles and fatal output remain unfinished.

Raw TOTEN, sigma-zero energy, entropy and magnetization extraction remains diagnostic and retains its existing implementation. Delta versus tetra is populated only when both the current case and tetra reference are finished and their energies exist. An incomplete tetra reference is never installed as comparison authority. abs_entropy_meV_atom is empty for an unfinished case. The comparison expression `abs((float(energy) - float(tetra_energy)) / 2 * 1000)` and entropy scaling are unchanged. No scientific_acceptance field, accepted-result promotion, energy convention or scientific threshold was introduced.

| Synthetic current-output case | finished | Delta comparison |
|---|---|---|
| Valid converged static, no ionic marker | True | Original formula preserved |
| Old completed output + newer run | False | Empty for damaged case; all deltas empty if tetra is damaged |
| Old completed output + newer electronic cycle | False | Same fail-closed rule |
| Truncated electronic cycle | False | Empty |
| Missing completion footer | False | Empty |
| Completed footer without explicit current SCF convergence | False | Empty |
| Recognized fatal output | False | Empty |
| Footer alone, empty file, or missing file | False | Empty |

All nine invalid-state variants are tested both on the tetra reference and on the non-reference case. Available raw diagnostic values remain visible, while comparison-quality fields fail closed. The valid static fixture has no ionic-convergence marker and preserves expected numeric results. Parser ownership is checked by function identity and AST inspection, with no duplicated footer regex.

## Scheduler ownership and scientific freeze

The maintained Python AST scanner covers scripts/modules/skills (232 Python files, excluding archived snapshots) and still finds one mutation authority, `scripts/neb_agent/submission.py`, at dispatch lines 464 and 544. Scheduler evidence contains no bsub/bkill construction. The formerly injectable runtime job-ID path now rejects before transport; source-token scanning alone is not used to prove this closure. Existing semantic ownership tests and added runtime API/CLI no-dispatch tests pass.

AST comparisons against the locked base preserve all three transferred decision functions, all four path/ID validators, alpha setup/check/submit/main and INCAR/KPOINTS writers, all module constants, and both comparison formulas. No config, schema, backend role, B1 reservation/executor, registry, scientific TS pipeline, VASP parser, ML promotion rule or calculation output is changed. ENCUT/KPOINTS/ISMEAR/SIGMA/EDIFF/EDIFFG/NELM/MAGMOM/ISPIN, NEB/DIMER/VFA/frequency/connectivity thresholds, reaction families and energy conventions retain their original owners and values.

All 20 historical report blobs match the locked base. No test was deleted or weakened. Four positive-fixture ID edits now use actual LSF identity syntax; all existing test assertions are unchanged.

## Exact changed files

- `scripts/convergence/setup_alpha_fe_bulk_smearing.py`
- `scripts/scheduler_evidence.py`
- `scripts/ts_strategy_engine/execution_gate.py`
- `scripts/ts_strategy_engine/execution_path_rules.py`
- `scripts/ts_strategy_engine/execution_submission_rules.py`
- `tests/test_alpha_fe_summary_current_state.py`
- `tests/test_aqcat25_path_active_learning.py`
- `tests/test_aqcat25_ts_active_learning.py`
- `tests/test_scheduler_evidence_boundary.py`
- `reports/refactor_audit/FINAL_B1_001_scheduler_evidence_closure_report.md`

The source changes are two narrow behavior fixes plus the necessary three-file dependency correction. The two new test modules add the requested regression coverage. Two existing ML test fixtures now use canonical numeric LSF IDs instead of test-label-1 or zero-padded image labels; all their assertions remain unchanged. This is the only new report.

## Executed validation

Initial development checks: Python compilation and cold scheduler/gate imports passed; new tests plus import-graph regression: 91 passed in 6.97s; expanded boundary/architecture/compatibility selection: 134 passed in 26.25s. The first full run found 13 failures (1344 passed) because old positive ML fixtures used noncanonical job IDs. Updating only their four ID literals/call arguments exposed one legacy live-state error-message mismatch (1 failed, 106 passed). The source now reuses complete evidence validation but retains the existing live-state mismatch check/message; that unchanged assertion passes. The affected ML and new boundary suites then passed 107 tests in 25.53s. The first full result is not claimed as successful; its log remains external. The following freshly logged runs are the final validation on the frozen staged source:

| Check | Actual result | Exit | Wall seconds |
|---|---|---:|---:|
| focused | 118 passed in 27.85s | 0 | 32.7 |
| ruff | All checks passed! | 0 | 0.27 |
| skill_ruff | All checks passed! | 0 | 0.23 |
| full | 1357 passed in 599.71s (0:09:59) | 0 | 602.48 |
| B1 | 260 passed in 130.27s (0:02:10) | 0 | 139.16 |
| B2 | 162 passed in 86.88s (0:01:26) | 0 | 88.95 |
| B5 | 56 passed in 30.64s | 0 | 33.93 |
| B7 | 17 passed in 1.43s | 0 | 3.56 |
| required_regressions | 164 passed in 169.57s (0:02:49) | 0 | 171.37 |
| diff_check | clean | 0 | 0.08 |
| release | {"status": "PASS", "parity": true, "wheel_files": 287} | 0 | 125.56 |

Full pytest: **1357 passed**; previous candidate: 1267; added coverage: 90 cases, with no deletions. Focused final boundary suite: **118 passed**. Full results report no failures/skips/deselections. Critical repeated groups and initial runs are not additional unique tests.

Exact commands:

```text
python -m pytest -o addopts= -q tests/test_scheduler_evidence_boundary.py tests/test_alpha_fe_summary_current_state.py tests/test_external_command_boundaries.py tests/test_execution_backends.py tests/test_aqcat25_ts_active_learning.py tests/test_aqcat25_path_active_learning.py
python -m ruff check scripts modules tests
python -m ruff check skills/fe-vasp-incar-custodian/scripts/incar_custodian.py
python -m pytest -o addopts= -q
python -m pytest -o addopts= -q tests/test_execution_lifecycle.py tests/test_neb_execution_gate.py tests/test_execution_gate_compatibility.py tests/test_execution_backends.py tests/test_gpu_execution_lifecycle.py tests/test_artifact_io.py tests/test_alpha_fe_bulk_submission.py
python -m pytest -o addopts= -q tests/test_b2_scientific_contract.py tests/test_b21_scientific_acceptance.py tests/test_ts_strategy_engine.py
python -m pytest -o addopts= -q tests/test_b5_architecture_boundaries.py tests/test_code_structure.py tests/test_repository_contracts.py
python -m pytest -o addopts= -q tests/test_b7_release.py
python -m pytest -o addopts= -q tests/test_scheduler_mutation_ownership.py tests/test_alpha_fe_bulk_submission.py tests/test_residual_parser_ownership.py tests/test_thickness_workflow_safety.py tests/test_scientific_claim_authority.py
git diff --check
python -m scripts.validate_release --source . --output C:\Users\86177\AppData\Local\Temp\sbq123-final-scheduler-evidence-20260910\final_validation\release
```

## Fresh release validation

Fresh `scripts.validate_release` passed. It exported the staged repair index, built and installed a real wheel in a clean venv, created a separate editable environment, and ran outside-repository probes with source-path environment overrides removed. Wheel/editable resources, console help, schema/migration resources, smoke behavior and explicit repository-only errors agree.

Wheel SHA-256: `b30981f4d9181142bd151b183d17e9247730d1446d9f4157eb91fe972a71ac83`; 287 members; 60 runtime resources. All 222 packaged Python members exactly match staged source bytes, including every repaired runtime module. Both smokes report scientific_acceptance=false and external_actions=0. The strict wheel allowlist and sensitive-artifact checks passed.

An additional core-wheel probe from an external directory imports the installed scheduler and CLI, rejects the malicious API/CLI ID with zero transport calls, and permits one fake numeric query. An exploratory cold import of alpha in that core-only environment returned the existing explicit CAPABILITY_UNAVAILABLE for missing ase.io through submission's NEB dependency; no source repair was made for this expected optional [neb] requirement. The normal developer tests include the existing optional dependencies. Alpha code-byte equality to the built wheel was separately verified. No package redesign or real scientific execution occurred.

## Evidence hashes

Final staged source/test hashes (also used to check no edits occurred after the final validation started):

- `scripts/convergence/setup_alpha_fe_bulk_smearing.py`: `c767cddec34ab05da7ac7bb317b1644e0aec8905513403e2928ab1470513fb26`
- `scripts/scheduler_evidence.py`: `536487510c26f8b1c028b75d8d21f564361de6dae57cc1c72a80e3b7c9ffe221`
- `scripts/ts_strategy_engine/execution_gate.py`: `792e54a335b948af980754542abbdb59ce233fb6bbf3e9f60d1be2cdff4762ae`
- `scripts/ts_strategy_engine/execution_path_rules.py`: `cfb02b4407acab3e722a0f8df601b9cf87de0e04aa494862f87a60149ae9babc`
- `scripts/ts_strategy_engine/execution_submission_rules.py`: `615fca02f6609fc55631f99ceac1238787d3a2367f9b565a93c7f1205d0a0c00`
- `tests/test_alpha_fe_summary_current_state.py`: `ba098538be7fe89cac4f65827ef622fad817a240b2586dc269230387c7e9c004`
- `tests/test_aqcat25_path_active_learning.py`: `150e839cd9a446b7fea22dcddf09a597b342cff456f6d687d95e82d27646914b`
- `tests/test_aqcat25_ts_active_learning.py`: `1bc6a042d5a0d576507640b60019330d4eadcc68112348d11d881fa2eba15b40`
- `tests/test_scheduler_evidence_boundary.py`: `5516092d54006a3b4667680038ba5196c239289f9434c408d7613f0e3e6a0d0f`

Final validation log SHA-256:
- focused: `0b6ecdb173579febb6f5146358d0672ec2813baf9f4051f3eeb8145e9656c177`
- ruff: `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18`
- skill_ruff: `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18`
- full: `6cde17c9e728812642883af8152575d7dd50162435ba07f5c40e7e7f367cb931`
- B1: `e594315e7ab48a227ddd8f3c7fba59372b640ac5567cea38d8ee09c97d39f9e9`
- B2: `bc83fab820884266b56ac3d09dd172e38961e703ec00ac00793e448f1aa412eb`
- B5: `88f30a397b452703a0536dfca561a6bd6a5ec90db02344ebd40a33fd4b9cadd3`
- B7: `f1d67230877b5e85083a069b300a604358e3bf24273624c71c52c007bd23527f`
- required_regressions: `74cd59fae3482d4b8aa3792559554cddf40472d7b013dc88619be381697adc1e`
- diff_check: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- release: `26da3062a732ffd723fa3caa204a75cb9beeedbb9265af92db84b09d20575a43`

## Closure and remaining scope

FINAL-B1-001 closure conditions are met: canonical pre-transport API/CLI rejection; no rejected evidence files; valid read-only query preserved; stored/live identity checks; one numeric syntax owner; no circular import or new scheduler executor; focused/full/release checks pass; no new P0/P1 found in the bounded repair review.

FINAL-B2-001 closure conditions are met: one OUTCAR owner; later incomplete states are unfinished; incomplete references/cases have no comparison authority; valid static summaries work; scientific values and formulas are unchanged.

Remaining demonstrated defects in this repair scope: P0=0, P1=0, P2=0, P3=0. This is not an assertion that the entire repository is bug-free or independently READY_TO_MERGE. Historical NOT_READY reports remain historical evidence; a new whole-repository verdict is not generated in this task.

Unverified production-only aspects: real SSH/backend deployment, HPC scheduler/VASP/MPI/GPU behavior, installed optional scientific environments, production DB/workbook/state and live authorization sources. New repair-commit remote CI is not queried after push because the task requires stopping immediately afterward. The existing managed projection drift is preserved without reconciliation. DEVELOPMENT_WORKSPACE_SYNC=NOT_PERFORMED; LIVE_STATE_RECONCILIATION=NOT_PERFORMED; external_scientific_actions=0.

Commit only the listed nine code/test paths and this report with message `fix: validate scheduler evidence IDs and current alpha summaries`; push only codex/final-b1-001-scheduler-evidence-closure to q2214299493/sbq123. No main merge/update or development sync. The actual repair SHA and push outcome are reported after commit; no self-referential commit SHA is embedded here.
