---
document_class: GENERATED_CURRENT_REPORT
as_of: '2026-09-10T09:30:03.836409+00:00'
source_version: 9e968201ac5fc5996b1c428bf9e9dc8e81434e45
source_version_role: exact locked candidate
source_branch: codex/final-merge-readiness-confirmation
source_scope: independent final merge-readiness confirmation only
evidence_kind: SOFTWARE_ACCEPTANCE_AUDIT
production_schema_version: UNVERIFIED
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Final Merge Readiness Confirmation

**CODE_MERGE_READINESS = NOT_READY_TO_MERGE**

A newly reproduced P1 (`FINAL-B1-001`) allows the nominally read-only scheduler-evidence API/CLI to execute an injected remote shell command outside the authoritative execution gate. Green existing tests/CI do not close this defect. No source repair was made.

**PRODUCTION_OPERATION_READINESS = UNVERIFIED**. Development sync and live state reconciliation were NOT_PERFORMED; external_scientific_actions=0. Do not merge this candidate on the basis of the passing checks below.

## Candidate and history

Repository: q2214299493/sbq123. Candidate branch: codex/ac-closeout-thickness-workflow.
Candidate SHA: `9e968201ac5fc5996b1c428bf9e9dc8e81434e45`; tree: `9a497120e39769865f24c520bd5a6d2dc01a60cb`.
A fresh GitHub clone was created at `C:/Users/86177/AppData/Local/Temp/sbq123-final-readiness-20260910`. The candidate branch was checked against the locked SHA before checkout; the audit branch starts directly at that SHA. The development directory was not modified or synchronized.

Each fixed SHA below was extracted from the prior closeout report and independently tested with `git merge-base --is-ancestor SHA 9e968201ac5fc5996b1c428bf9e9dc8e81434e45` (exit 0). Both historical failed audits and their subsequent repairs remain in the chain.

| Historical milestone | Fixed SHA | Ancestor |
|---|---|---|
| origin/codex/b1-execution-lifecycle | `b1c59addbc7d7be64347db66a201dc5841404341` | True |
| origin/codex/b2-scientific-contract | `3d9e9070e48a6cb65d9b4c0334adb4243f36dd0c` | True |
| origin/codex/b3-evidence-ml-governance | `9f4332f082d4e286ce43c5a137a62ac1e30fa441` | True |
| origin/codex/b4-registry-state-management | `fbbb7bb26d28867d9766cc7fca84077fa54cf3d6` | True |
| origin/codex/b5-architecture-boundaries | `3a1bb3f461147a7dc9b5df5efca89de621d27f38` | True |
| origin/codex/b6-documentation-data-governance | `93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a` | True |
| origin/codex/b7-release-environment | `7a0b745df96de2762a6f289e9eeda1a3c298fe9d` | True |
| first_failed_audit | `fad1d32607723c851c457a5fb6fa85898cdc1edf` | True |
| scientific_claim_repair | `a050fe28b25f1fc5ee91f5e7e3fb7fc1150a2157` | True |
| second_failed_audit | `a24bda4fb82c325bdcc385c9b089a061ddcf7096` | True |
| execution_repair | `9bf950b09b965ea832148fb3ad0f44625492652e` | True |
| previous_closeout | `fae4339f7f91b52c13f4b993c9791e7110f13249` | True |
| thickness_repair | `9e968201ac5fc5996b1c428bf9e9dc8e81434e45` | True |

All 17 pre-thickness audit blobs are unchanged across the thickness repair; all 18 report blobs present at this locked candidate remain unchanged in this audit. Only the two requested report paths are added.

## New findings

### FINAL-B1-001 — P1, OPEN, merge blocking

- `scripts/scheduler_evidence.py:31-38`: `query_lsf_job` coerces/strips job_id and only rejects an empty string before `subprocess.run`.
- `scripts/ts_strategy_engine/active_learning_cli.py:168-171,256-259`: the public `capture-lsf-evidence --job-id` route accepts that text and calls the same owner without an execution gate.
- The captured argv for synthetic input `123; bkill 456 #` was `['ssh', 'sunboquan-codex', 'bjobs', '-a', '123; bkill 456 #']`.
- OpenSSH combines command arguments with spaces before remote execution; local `shell=False` does not quote the remote command. This behavior is specified by the [OpenSSH manual](https://man.openbsd.org/ssh).
- The independent reproduction patched only the subprocess transport to capture argv. It then ran a local Bash simulation with `bjobs` and `bkill` defined as inert printing functions. Output was `FAKE_QUERY` followed by `FAKE_MUTATION:456`, exit 0. No SSH or scheduler executable ran. The same argv was reached via the maintained CLI. No authorization, reservation or gate call occurred.
- A later subprocess error, output parser or schema rejection cannot undo an already dispatched command. Impact includes gate-bypassing job termination or submission under the existing SSH identity.

The JSON embeds the complete external reproduction program and captured result. Source-origin assertions tie imports to the isolated candidate. Follow-up repair should reuse the canonical job-ID validator before transport construction and add API/CLI no-dispatch tests; this audit did not implement it.

### FINAL-B2-001 — P2, OPEN, nonblocking diagnostic limitation

`setup_alpha_fe_bulk_smearing.summary` still checks historical `General timing and accounting` anywhere in OUTCAR. A synthetic old completed run followed by a new incomplete cycle produced CSV `finished=True` while the canonical `parse_outcar` returned `normal_completion=False`. Existing numeric deltas can also be displayed without current convergence. No maintained consumer promoting this diagnostic CSV into scientific acceptance, registry approval or scheduler authorization was found. Historical provenance references to a 2026-06-23 CSV are not current executable consumers. Keep the flag out of final scientific interpretation; separate follow-up required. No report/data was overwritten outside fresh synthetic fixtures.

Open counts: P0=0, P1=1, P2=1, P3=0. Previously named P0/P1 blockers remaining open=0; newly discovered P0=0/P1=1. No claim of bug-free software or absolute safety.

## Independently rechecked known blockers

The maintained tests were read before execution and call the real scientific validators, canonical submitter and generated Bash payloads. They fake external transport/VASP/MPI and inject terminal I/O failures only; scientific gates are not replaced with unconditional PASS.

| Issue | Status | Current evidence |
|---|---|---|
| AC-B2-001 | CLOSED | test_scientific_claim_authority.py: fake Grade-A/True rejected at Python/CLI; stale summaries and underlying DIMER/VFA/NEB data revoke old actions; barrier booleans rejected; positive real owner fixtures pass |
| AC-RERUN-B1-001 | CLOSED | test_alpha_fe_bulk_submission.py: actual adapter -> canonical submit; no authorization 0 dispatches; concurrent callers exactly 1; uncertain receipt/timeout/missing ID/rejection does not retry |
| AC-RERUN-B2-001 | CLOSED | test_residual_parser_ownership.py: raw_incar_value delegates read_incar_values; semicolon MAGMOM literal 3*2.0 retained |
| AC-RERUN-B2-002 | CLOSED | test_residual_parser_ownership.py: parse_final_outcar delegates parse_outcar; old completed output plus newer incomplete cycle is not complete |
| AC-CLOSEOUT-B1-001 | CLOSED | test_thickness_workflow_safety.py: real generated chain/static scripts; relax error 9 stops static; old output rejected; static error propagated; positive complete and scientific_acceptance=false; fresh installed-wheel payload probes agree |
| AC-CLOSEOUT-B2-001 | CLOSED | test_convergence_common.py and test_thickness_workflow_safety.py: signed/exponent TOTEN; malformed/nonfinite rejected; incomplete bulk refused; incomplete slab surface excess null; no scientific promotion |

## Scheduler ownership scan

232 maintained Python files were AST-scanned under scripts/modules/skills. Import aliases, subprocess.run/Popen/call/check_call/check_output, os.system/popen, command variables, concatenation, append/extend and local runner propagation were considered. All 17 resolved external subprocess sinks were manually classified; non-process optimizer.run methods and archived VASP2Kinetics runners were separated. All tracked shell/PowerShell/batch/LSF paths were inventoried; literal scheduler-token search yielded only four lines in submission.py (two comments and two command constructions).

The existing literal/AST test reports only `scripts/neb_agent/submission.py`, with dispatch call sites at lines 464 (bsub through remote verification) and 544 (bkill). Additional inert alias/extend/concatenation probes pass. **That static result is insufficient:** user-controlled job ID supplies a command not present as a source literal. Effective mutation-capable paths include submission.py and scheduler_evidence.py. The required single authoritative scheduler mutation boundary therefore FAILS.

Read-only structure/label/monitor SSH queries, Git inventory commands, release build/install commands, and the reviewed Node workbook writer are distinct from intended scheduler mutation. Arbitrary externally supplied runner/writer/script bodies and missing historical dist.pl are outside source certification; they were not executed. The discovered scheduler_evidence defect is concrete maintained CLI behavior, not dismissed as an external-code limitation.

Generated thickness/GPU payloads run calculations but do not submit scheduler jobs. Six old thickness LSF input artifacts are historical and explicitly disallowed for fresh reuse by the current README. Templates/comments alone were not counted as executed scheduler mutations.

## Current validation

Every command below was run anew in the isolated candidate with UTF-8 output and logs outside the checkout. Local environment: Windows 11, Python 3.13.9, Git Bash. Tests use disposable databases/files and fake scientific execution. No source/test/config changed to obtain these results.

| Check | Exact result | Exit | Wall seconds |
|---|---|---:|---:|
| ruff | All checks passed! | 0 | 1.01 |
| skill_ruff | All checks passed! | 0 | 0.16 |
| full | 1267 passed in 488.79s (0:08:08) | 0 | 491.51 |
| focused_final | 183 passed in 145.98s (0:02:25) | 0 | 159.5 |
| B1 | 260 passed in 189.61s (0:03:09) | 0 | 193.91 |
| B2 | 162 passed in 73.16s (0:01:13) | 0 | 76.79 |
| AC_B2_001 | 31 passed in 28.34s | 0 | 31.44 |
| B3 | 68 passed in 8.01s | 0 | 18.25 |
| B4 | 121 passed in 15.54s | 0 | 16.64 |
| B5 | 56 passed in 17.08s | 0 | 18.23 |
| B6 | 26 passed in 1.98s | 0 | 3.42 |
| B7 | 17 passed in 0.83s | 0 | 1.76 |
| diff_check |  | 0 | 0.07 |
| release | {"status": "PASS", "parity": true, "wheel_files": 287} | 0 | 96.91 |

Exact commands:

```text
python -m ruff check scripts modules tests
python -m ruff check skills/fe-vasp-incar-custodian/scripts/incar_custodian.py
python -m pytest -o addopts= -q
python -m pytest -o addopts= -q tests/test_thickness_workflow_safety.py tests/test_convergence_common.py tests/test_true_fe110_thickness.py tests/test_alpha_fe_bulk_submission.py tests/test_scheduler_mutation_ownership.py tests/test_scientific_claim_authority.py tests/test_residual_parser_ownership.py tests/test_aqcat25_calibration.py
python -m pytest -o addopts= -q tests/test_execution_lifecycle.py tests/test_neb_execution_gate.py tests/test_execution_gate_compatibility.py tests/test_execution_backends.py tests/test_gpu_execution_lifecycle.py tests/test_artifact_io.py tests/test_alpha_fe_bulk_submission.py
python -m pytest -o addopts= -q tests/test_b2_scientific_contract.py tests/test_b21_scientific_acceptance.py tests/test_ts_strategy_engine.py
python -m pytest -o addopts= -q tests/test_scientific_claim_authority.py
python -m pytest -o addopts= -q tests/test_b3_evidence_governance.py tests/test_b3_ml_governance.py
python -m pytest -o addopts= -q tests/test_registry_write.py tests/test_b4_registry_governance.py tests/test_b4_state_governance.py tests/test_registry_schema.py tests/test_state_manager.py
python -m pytest -o addopts= -q tests/test_b5_architecture_boundaries.py tests/test_code_structure.py tests/test_repository_contracts.py
python -m pytest -o addopts= -q tests/test_b6_governance.py
python -m pytest -o addopts= -q tests/test_b7_release.py
git diff --check
python -m scripts.validate_release --source C:\Users\86177\AppData\Local\Temp\sbq123-final-readiness-20260910 --output C:\Users\86177\AppData\Local\Temp\sbq123-final-readiness-evidence-20260910\release
```

Full count: 1267, compared with the previous thickness repair's 1267; delta 0, no test removals or additions. The earlier pre-repair 1181 is not the comparison candidate. All full-suite tests passed, with no skips/deselections reported. Focused and repeated critical groups are separate runs, not extra unique test counts. B1-B7 group command selections are exactly those recorded in the prior closeout JSON.

## Fresh release and installed execution

The release validator exported the tracked candidate index, built a real wheel, created clean normal/editable virtual environments, and executed probes outside repository cwd with PYTHONPATH/PYTHONHOME removed. Runtime resources, migration SQL, retrieval schemas, explicit REPOSITORY_CONTEXT_REQUIRED failures and editable/wheel parity passed.

Wheel SHA-256: `078279726674c973251c12b0e759bf79068551152b6823bad02553928d077521`. Members: 287; resources: 60; console entrypoints: 9. All 222 packaged Python members exactly equal candidate Git blob bytes, including alpha-Fe, thickness generator/helper/common and calibration. Installed-resource bytes match source; both smokes record scientific_acceptance=false and external_actions=0.

Six additional fresh normal-wheel payload probes used the real setup-generated scripts from external directories and the installed thickness helper (site-packages, no source path injection). Valid chain/static exited 0 with 2/1 fake calls; failing chain/static exited 9 with 1/1 fake calls; old chain output failed 65 before calculation; missing static output failed 65 after one fake call. Every final record retained scientific_acceptance=false. No ASE/pymatgen/Sella is required by the installed stage helper; generation uses the documented optional ASE dependency.

Tracked filename/private-key-header scanning found no excluded sensitive artifacts among 1314 tracked files and no files above 10 MB. The fresh wheel additionally passed the strict Python/resource allowlist and excluded-artifact checks. This is bounded artifact verification, not an absolute secret-detection guarantee.

## Exact-candidate remote CI

Direct GitHub run [34455339742](https://github.com/q2214299493/sbq123/actions/runs/34455339742): exact head `9e968201ac5fc5996b1c428bf9e9dc8e81434e45`, completed/success. Job logs were fetched independently; OS/Python below come from those jobs, not assumed from local execution. No CI from the report commit or another candidate was substituted.

| Job | Job ID | Platform | Python | Result |
|---|---:|---|---|---|
| wheel (windows-latest) | 102800303376 | windows-latest | 3.11.9 | completed/success |
| wheel (ubuntu-latest) | 102800303668 | ubuntu-latest | 3.11.16 | completed/success |
| engineering (windows-latest) | 102800303762 | windows-latest | 3.11.9 | completed/success |
| validate | 102800303768 | ubuntu-latest | 3.11.16 | completed/success |
| engineering (ubuntu-latest) | 102800303921 | ubuntu-latest | 3.11.16 | completed/success |

The Ubuntu validate log reports 1267 passed; both engineering jobs report 263 passed; both wheel jobs report PASS/parity true/287 members. Windows runner logs identify Windows Server 2025; Ubuntu logs identify Ubuntu 24.04. These results close the previous repair report's pending Linux/Windows CI gap. Historical reports are not rewritten.

## Scientific freeze

The repair diff from fae4339f7f91b52c13f4b993c9791e7110f13249 is exactly seven paths: one module README, one repair report, common.py, the thickness generator, new thickness_stage.py and two test files. AST comparison preserves LATTICE_A, LAYERS, VACUUM_A, RELAX_MESH, STATIC_MESH, EV_A2_TO_J_M2, INCAR builders, kpoint writer, layer grouping, slab builder, validation and the surface-excess formula. Executing only the old/current input generators in separate fresh temporary directories produced 34 identical non-LSF input/metadata files.

This includes lattice 2.8665, layers 4-8, vacuum 15, relax 5x5x1, static 7x7x1, bulk 21x21x21, ENCUT 400, EDIFF 1E-6, all EDIFFG/ISMEAR/SIGMA/NELM/MAGMOM/ISPIN values as originally emitted, and bottom two fixed layers/18 atoms. NEB/DIMER/VFA policy, reaction families, registry schema and all other configuration files are outside that diff and unchanged. No unexplained scientific parameter change was found. This audit itself changes no scientific or executable content.

## B1-B7 final matrix

| Area | Verdict | Basis |
|---|---|---|
| B1 Execution Safety | FAIL | Required regression group passes, but new FINAL-B1-001 bypasses scheduler mutation authority. |
| B2 Scientific Contract / VASP | PASS_WITH_NONBLOCKING_LIMITATION | Critical scientific validators and known blockers pass. Diagnostic-only FINAL-B2-001 remains P2. |
| B3 Evidence / ML Governance | PASS_WITH_NONBLOCKING_LIMITATION | B3 evidence/ML regression group passes. Acquisition through scheduler query inherits FINAL-B1-001; overall merge remains blocked. |
| B4 Registry / State | PASS | Critical transactions/schema/state regressions pass on temporary data; not production reconciliation. |
| B5 Architecture | FAIL | Maintained tests pass, but static owner scanner misses runtime job-ID remote-shell injection. |
| B6 Documentation / Data Governance | PASS_WITH_NONBLOCKING_LIMITATION | B6 tests pass; existing historical task/projection drift remain documented source-publication limitations; the prior audit recorded eight unclassified SKILL frontmatters. |
| B7 Release / Environment | PASS | Fresh wheel/editable/outside-source/resource probes and five exact-candidate CI jobs pass. |
| AC-B2-001 | PASS | test_scientific_claim_authority.py: fake Grade-A/True rejected at Python/CLI; stale summaries and underlying DIMER/VFA/NEB data revoke old actions; barrier booleans rejected; positive real owner fixtures pass |
| AC-RERUN-B1-001 | PASS | test_alpha_fe_bulk_submission.py: actual adapter -> canonical submit; no authorization 0 dispatches; concurrent callers exactly 1; uncertain receipt/timeout/missing ID/rejection does not retry |
| AC-CLOSEOUT thickness workflow | PASS | Both closeout defects independently closed for regenerated payloads and diagnostic extraction; historical scripts unchanged. |

## Remaining boundaries

- No real SSH/scheduler/VASP/MPI/GPU/production DB/workbook actions. HPC deployment, vendor environment, network filesystem atomicity and MPI signal forwarding unverified.
- Explicit user-supplied --runner/monitor script/writer and absent archived dist.pl contents are not certified. Reviewed maintained implementations are enumerated; arbitrary external code is outside this finite audit.
- Read-only startup audit: one existing managed_projection_drift error and one review request for docs/06_MODULE_MAP.md transition_state_search. Historical Dimer task is not current live state. Preserved without sync/reconciliation.
- Six retained 20260627 thickness .lsf artifacts were not rewritten. They must not be reused as repaired payloads; current module README requires a new directory and regeneration/reviewed recovery.
- Local Windows 11/Python 3.13.9/Git Bash; exact-candidate CI supplies Ubuntu/Python 3.11.16 and Windows Server 2025/Python 3.11.9 evidence. No local native Linux claim.

The existing state-manager review request is preserved as a last-recorded publication-state limitation; no current HPC state is inferred. No review choice was submitted and no sync command was run. The concrete P1, rather than an unperformed production deployment, blocks code merge readiness. Required software verification completed; merge-blocking verification gaps=0, demonstrated merge-blocking defects=1.

## Publication scope

Only FINAL_merge_readiness_report.md and FINAL_merge_readiness.json are intentional tracked outputs, on codex/final-merge-readiness-confirmation based directly on the locked candidate. Before commit: status, unstaged diff check and staged diff check; stage only these two files. Preserve every previous report. No merge, no main update, no development sync, no production action. The final response records the actual audit commit and push outcome; a future repair is not started by this audit.
