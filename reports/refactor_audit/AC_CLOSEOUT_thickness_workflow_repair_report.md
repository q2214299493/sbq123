---
document_class: GENERATED_CURRENT_REPORT
as_of: '2026-09-10T08:24:28.820389+00:00'
source_version: fae4339f7f91b52c13f4b993c9791e7110f13249
source_version_role: locked repair base; final source hashes below
source_branch: codex/ac-closeout-thickness-workflow
source_scope: thickness payload and diagnostic energy repair only
evidence_kind: SOFTWARE_REPAIR_VERIFICATION
production_schema_version: UNVERIFIED
governance: docs/DOCUMENT_GOVERNANCE.md
---

# AC-CLOSEOUT Thickness Workflow Repair

**AC-CLOSEOUT-B1-001: CLOSED within the repaired workflow and tested Bash environment.**
**AC-CLOSEOUT-B2-001: CLOSED through the real extractor and summary paths.**

This report does not declare whole-repository READY_TO_MERGE. Independent acceptance remains a separate task. The previous NOT_READY_TO_MERGE closeout and every earlier report remain unchanged. Actual Linux execution of the repaired payload is pending the new commit’s CI at publication; local results are Windows/Git Bash, not Linux or HPC evidence.

## Base, isolation and exact changes

- Repository: `https://github.com/q2214299493/sbq123.git`.
- Locked base: `fae4339f7f91b52c13f4b993c9791e7110f13249`; tree `ee509d718b7e08936411c9d7459b64700e181b02`.
- Base branch `codex/b1-b7-final-acceptance-closeout` matched the remote before cloning; new branch `codex/ac-closeout-thickness-workflow` did not pre-exist.
- Independent clone: `C:/Users/86177/AppData/Local/Temp/sbq123-thickness-repair-20260910`. All logs, synthesized jobs, databases, release export, wheels and venvs are outside the development directory under `C:/Users/86177/AppData/Local/Temp/sbq123-thickness-evidence-20260910` or pytest system temp directories.
- Local OS `Windows-11-10.0.26200-SP0`, Python `3.13.9`; generated shell executed with Git Bash at `C:/Program Files/Git/bin/bash.exe`.
- No reset/clean/stash/checkout/pull/file replacement in the real development directory, no main update/merge, HPC deployment, actual potential access, database/workbook mutation, GPU/VASP/MPI computation or scientific network operation.
- All 17 existing refactor-audit report files match their pre-task SHA-256 hashes. The supplied independent ZIP was supplemental evidence; the repository closeout JSON provided the original programs/results.

Task-owned changed files:

- `modules/convergence_workflow/README.md`
- `scripts/convergence/common.py`
- `scripts/convergence/setup_true_fe110_thickness_retest.py`
- `scripts/convergence/thickness_stage.py`
- `tests/test_convergence_common.py`
- `tests/test_thickness_workflow_safety.py`
- `reports/refactor_audit/AC_CLOSEOUT_thickness_workflow_repair_report.md`

The generator owns setup and one shared Bash template used by chain_lsf/static_lsf. The new thickness_stage module only checks inputs/results and publishes the validated structure; it has no subprocess or scheduler API. It delegates parsing to existing owners. common.extract_toten owns numeric extraction. summarize remains diagnostic. No CI/resource-policy/schema change or parallel workflow engine was introduced.

## Original defects reproduced before modification

The unmodified base functions were AST-extracted, preserving chain_lsf’s original returned text and last_toten’s code. Only `source` and `mpirun` were replaced by inert Bash functions in a fresh external directory. Old relax/static OUTCAR markers and old CONTCAR were synthesized; no real potential or structure was copied.
- Base source SHA-256: `f3381741f679603105db8c6a2c9e53614ea7955e5e349f3e224eb806ff4e539d`.
- Exact old shell SHA-256: `a0d70d364e7a092eed8be3a72f195345d67ba1d9e186aac8fa26068615bd0722`.
- Both fake MPI calls returned 9. Observed: two calls, static entered, old CONTCAR copied, chain exit 0.
- Ordinary `free  energy   TOTEN  =       -10.50000000 eV` yielded None rather than -10.5.
The supplied Linux /bin/sh and /bin/bash supplementary evidence matches that old blob; it is not counted as Linux verification of this repair.
P1 root cause: MPI return codes were discarded, then cumulative grep markers and cp/grep statuses controlled the chain. P2 root cause: a raw regex escaped its whitespace classes twice; the shared extractor also needed complete signed/exponent-token validation.

## Final shell and stage contract

Both actual setup-generated scripts declare `/bin/bash`; POSIX sh is not claimed. Defaults remain initialization `/home_gkx/env/intel/intel2016.sh`, VASP `$HOME/soft/vasp.5.4.1/bin/vasp_std`, NP=32, NP_PER_NODE=32, OMP_NUM_THREADS=1 and existing RAW resource semantics. Explicit selectors THICKNESS_ENV_SCRIPT, THICKNESS_VASP, THICKNESS_MPI and THICKNESS_PYTHON are paths/command names, not eval fragments. Missing explicit dependencies never fall back silently.
The initialization script must exist and return success. Its legacy environment is not subjected to implicit nounset/errexit. Python and its stage module, MPI and VASP are checked before calculation; hosts must be nonempty valid tokens. Machinefile creation, stage cd and output redirection errors fail explicitly. No grep fallback exists.
An exclusive `mkdir .thickness-attempt` is local payload ownership, not a scheduler reservation or authorization. It is never deleted: concurrent/repeated invocations fail, including after success. A missing final record means UNKNOWN_NEEDS_REVIEW; there is no automatic rerun. A final record contains stage, original exit code and scientific_acceptance=false. SIGINT/TERM/HUP stop downstream progression; hard kills can leave only the blocking attempt directory.
Both stage directories are inspected before the first MPI call and each stage checks inputs again immediately before launch. Existing calculation outputs, symlinks and stale output logs are rejected without truncating or moving them. Static’s setup POSCAR remains a permitted input. Setup checks the entire campaign before any write, including payload and B1 attempt/receipt markers; input-only repetition remains byte-identical. No B1 marker is modified.
Every MPI call captures its original status directly. Exit 9 stays exit 9; validation failure is 65, unavailable dependency 69, invalid hosts 64, cd failure 72, existing attempt 73 and failed final record write 74 if no earlier failure exists. Other environment/I/O return codes remain nonzero. Traps never replace a prior failure with success.
OUTCAR stage interpretation delegates to neb_agent.utils_vasp.parse_outcar. Both modes require current normal completion, final-cycle completeness, explicit electronic convergence and no recognized fatal evidence. Relaxation additionally needs current ionic convergence. Static remains NSW=0/IBRION=-1 without an ionic-relaxation requirement. No NELM value or convergence threshold is guessed or added.
Handoff reparses the current CONTCAR using the existing POSCAR owner, validates finite structure data and Fe atom/cell/Selective Dynamics consistency, checks contained nonsymlink paths, writes a same-directory temporary file, fsyncs and atomically publishes it. Source/replace failure prevents static; only the unpublished temporary file is removed on error. A current structure identical to its original input passes and is copied byte-for-byte.

## Actual generated-shell fault matrix

All cases use real chain_lsf/static_lsf or setup-written scripts. Fake MPI never executes its VASP argument. Fault injection affects dependencies or terminal I/O only, without replacing scientific guards with always-PASS.

| Case | Fake calls | Observed result |
|---|---:|---|
| Missing/failed initialization; missing MPI/VASP/Python/stage module; empty/blank/invalid hosts | 0 | Nonzero, FAILED record; initialization return 17 preserved |
| Old OUTCAR/CONTCAR/vasp.out, including dirty static alone | 0 | Reject before any calculation/redirection; old bytes preserved |
| Relaxation return 9 | 1 | Exit 9, no static or handoff |
| Relaxation return 0 but missing/incomplete output, absent SCF/ionic evidence, truncated/new cycle/new run, fatal marker | 1 | Reject, no static |
| Missing/empty/unparseable CONTCAR; injected atomic replacement failure | 1 | Reject, target input unchanged; no temporary handoff left |
| Machinefile creation, redirection or stage cd failure; standalone input disappears after preflight | 0 | Nonzero, no calculation |
| Static return 9 (chain / standalone) | 2 / 1 | Exit 9, FAILED |
| Static return 0 without current completion/SCF, truncated/new cycle/new run/fatal output | 2 / 1 | Nonzero, FAILED |
| Complete chain and unchanged-but-current CONTCAR | 2 | Exit 0, exact handoff bytes, scientific_acceptance=false |
| Complete standalone static/bulk, without ionic marker | 1 | Exit 0, scientific_acceptance=false |
| Two payload callers in one directory | 2 total | One exit 0, other 73; only one output owner |
| Repeat after completed payload | 0 additional | Reject; all prior files unchanged |
| TERM / INT / HUP during relaxation | 1 each | Exit 143 / 130 / 129; no static, FAILED |
| Final record cannot be written | 1 static | Process failure 9 preserved; otherwise exit 74, no successful record |
| Symlinked stage/input escape | 0 | Reject; outside bytes unchanged |
| Setup discovers an old run in final bulk destination | 0 | Entire campaign unchanged; no partial overwrite |

TERM is in the focused pytest suite. INT/HUP were additionally run with the same Payload fixture and fake MPI `kill -INT "$PPID"` / `kill -HUP "$PPID"`, returning 130/129 with one fake relaxation call each. These are local controlled signals, not scheduler/job operations.

## TOTEN and real summary

last_toten delegates to common.extract_toten. The shared owner recognizes the complete last record, supports signed E/e exponents and irregular whitespace, calls finite_number, and rejects invalid/NaN/Inf/overflow tokens. An invalid final record cannot fall back to an earlier value. Missing file/no record returns None; legitimate negative DFT energies remain negative. Numeric extraction itself grants no completion or scientific acceptance.
Real setup produced all layer and bulk structures for summarize tests. A synthetic bulk total -10 eV gives -5 eV/atom; each slab total was -5*natoms+2 eV. The computed surface excess equals `2/(2*area)*EV_A2_TO_J_M2` from each actual cell. The original bulk/2, two-surface factor, cell cross-product area, TOTEN convention and 16.02176634 conversion remain unchanged.
Missing slab energy gives null TOTEN/surface excess. A later incomplete cycle gives INCOMPLETE_OR_FAILED and null surface excess, retaining only diagnostic energy. Missing/incomplete bulk or malformed/nonfinite energy raises before replacing an existing summary. Every summary row explicitly carries scientific_acceptance=false; no registry/TS/fact promotion was added.

## Similar reachable paths and scope

| Path | Disposition |
|---|---|
| setup_true_fe110_thickness_retest.chain_lsf and static_lsf | Both share the repaired template; actual setup outputs tested |
| modules/convergence_workflow/inputs/fe110_true_facet_thickness_20260627/{layers_4..8,bulk_reference}/*.lsf | Historical generated input artifacts retained byte-for-byte. Their legacy control flow is not safe for new/repeated execution; README requires new directories/regeneration or separately reviewed recovery. No historical evidence rewrite |
| scripts/templates/sunboquan_vasp.lsf via vasp_lsf.py | Single MPI payload with MPI as final command; no chained old-marker decision. Separate VASP/VTST/backend scope preserved, not certified for all early-environment failures |
| scripts/adsorption/gas_vasp_common.py JOB_SCRIPT | Single MPI gas-reference payload; different POTCAR-link/setup boundary. No second stage/old-footer override; not changed or globally declared safe |
| GPU wrapper scripts | Previously owned GPU execution lifecycle; no thickness relaxation/static handoff. Existing B1 regression retained |
| grep-based diagnostic readers / check_neb_job.sh | Read-only observations, not this payload’s execution authority; no unrelated parser refactor |

This finite review distinguishes scheduler mutation from scheduler-launched payloads. Canonical submission remains the sole scheduler mutation owner. Preserving historical scripts means deployment/recovery must actually use the new generated payload; no deployed copy was updated automatically.

## Scientific and architecture freeze

AST/value comparisons passed for `LATTICE_A`, `LAYERS`, `VACUUM_A`, `RELAX_MESH`, `STATIC_MESH`, `EV_A2_TO_J_M2`, `incar_relax`, `incar_static`, `write_kpoints`, `layer_indices`, `build_slab`, `validate`, `surface_excess_formula`.
All 34 non-LSF generated input/metadata files match the base byte-for-byte (all INCAR, POSCAR, KPOINTS and campaign metadata).
This covers lattice 2.8665, layers 4–8, vacuum 15, 3x3 Fe(110), bottom two fixed layers/18 Fe, relax 5x5x1, static 7x7x1, bulk 21x21x21, ENCUT 400, EDIFF 1E-6 and all existing INCAR values. Only payload/control and diagnostic validity behavior changed.
Byte comparisons retain B1 submission/gate/authorization, repaired alpha adapter, AC-B2 scientific claims, shared VASP/INCAR/finite owners, registry schema and B7 resource policy. No scientific threshold, compatibility branch, production database, model weight, real POTCAR or output changed.

## Current validation

Collection: 1267; full passed: 1267; failed: 0; skipped: 0; deselected: 0. Base reference 1181 -> 1267: 86 new cases, not repeated executions counted as new tests.

| Group | Actual result | Exit | Wall seconds |
|---|---|---:|---:|
| focused | 89 passed in 142.25s (0:02:22) | 0 | 151.59 |
| ruff | All checks passed! | 0 | 1.39 |
| full | 1267 passed in 668.99s (0:11:08) | 0 | 673.3 |
| B1 | 278 passed in 197.90s (0:03:17) | 0 | 199.79 |
| B2 | 162 passed in 101.88s (0:01:41) | 0 | 103.7 |
| AC_B2_001 | 31 passed in 34.45s | 0 | 39.17 |
| B4 | 121 passed in 20.15s | 0 | 21.61 |
| B5 | 56 passed in 24.40s | 0 | 27.36 |
| B6 | 26 passed in 2.52s | 0 | 4.53 |
| B7 | 17 passed in 1.15s | 0 | 3.02 |

Exact executed commands:

```text
python -m pytest -o addopts= -q tests/test_thickness_workflow_safety.py tests/test_convergence_common.py tests/test_true_fe110_thickness.py
python -m ruff check scripts modules tests
python -m pytest -o addopts= -q
python -m pytest -o addopts= -q tests/test_execution_lifecycle.py tests/test_neb_execution_gate.py tests/test_execution_gate_compatibility.py tests/test_execution_backends.py tests/test_gpu_execution_lifecycle.py tests/test_artifact_io.py tests/test_alpha_fe_bulk_submission.py tests/test_scheduler_mutation_ownership.py
python -m pytest -o addopts= -q tests/test_b2_scientific_contract.py tests/test_b21_scientific_acceptance.py tests/test_ts_strategy_engine.py
python -m pytest -o addopts= -q tests/test_scientific_claim_authority.py
python -m pytest -o addopts= -q tests/test_registry_write.py tests/test_b4_registry_governance.py tests/test_b4_state_governance.py tests/test_registry_schema.py tests/test_state_manager.py
python -m pytest -o addopts= -q tests/test_b5_architecture_boundaries.py tests/test_code_structure.py tests/test_repository_contracts.py
python -m pytest -o addopts= -q tests/test_b6_governance.py
python -m pytest -o addopts= -q tests/test_b7_release.py
python -m pytest --collect-only -q
git diff --check
```

The final focused run is 89 tests, on the final source. Earlier 73/82/85 development runs are not the final evidence: Windows subprocess decoding warnings in the first run were fixed by explicit UTF-8; the final run has no warnings. The 85-test pass overlapped addition of four host-input cases and was superseded by the final 89-test run. Final source/test modifications finished before the full-suite process started. No runtime source changed after the release export.

### Platform boundary

LOCAL_WINDOWS_VALIDATION: Windows 11, Python 3.13.9, Git Bash. Both generated script kinds also passed `bash -n`. No usable local WSL/Linux distribution is installed. Linux repair execution is **NOT_EXECUTED_LOCALLY / CI_PENDING at publication**. The unchanged Ubuntu validate job runs the complete repository suite, which collects the new shell tests; the fixture explicitly fails on Linux if Bash is missing rather than silently skipping. Windows without Bash may skip payload tests while independent Python/parser/setup/summary tests still run. No current Linux result is inferred from the older ZIP or Git Bash.
The repair commit’s remote CI status is PENDING until queried after publication. This is a verification gap, not a reproduced source defect or a fabricated successful Linux run.

## New release and normal-install execution

`python -m scripts.validate_release --source . --output C:/Users/86177/AppData/Local/Temp/sbq123-thickness-evidence-20260910/release` exited 0.
Wheel `sbq_catalyst_agent_workflow-0.1.0-py3-none-any.whl`; SHA-256 `6d07afd60a06ea61c01485b37c6bfe7cb6dd5c2f40eba44a57051ab9c7abd853`; members 287; runtime resources 60.
A fresh tracked-index export, fresh normal wheel and editable venvs, outside cwd, all console entrypoints, runtime resources, explicit repository-only errors and installation parity passed. Both mock smokes report scientific_acceptance=false/external_actions=0. The new helper is ordinary package Python discovered by the existing B7 owner, so no duplicate resource list/config was introduced.
After normal wheel installation, real setup-generated payloads were run from an external cwd with PYTHONPATH/PYTHONHOME removed and THICKNESS_PYTHON pointing into that venv. The actual imported helper path was inside wheel-venv/site-packages. The stage path required no ASE/pymatgen/Sella/ML dependency. Generator setup still requires the documented optional ASE dependency in its generation environment.

| Installed payload | Mode | Exit | Fake calls |
|---|---|---:|---:|
| chain | valid | 0 | 2 |
| static | valid | 0 | 1 |
| chain | exit9 | 9 | 1 |
| static | exit9 | 9 | 1 |
| chain | old | 65 | 0 |
| static | missing | 65 | 1 |

Packaged source matches both final tested files and their staged Git bytes:

- `scripts/convergence/common.py`: `83ba5439d0d50ecee248ddacae0bc2f66d6d8eaf55119a3d774c57ef5f01d720`
- `scripts/convergence/setup_true_fe110_thickness_retest.py`: `4f2f06361b85b922ea443ed11a462789a64e58e6fd81f5c12ac887289091c8cd`
- `scripts/convergence/thickness_stage.py`: `e74d1be3251dca6f4cebf9e385001dedcfe495bfeb55cd2cf4a2d19cdce0885e`

All wheel members passed the existing strict source/resource allowlist and excluded-artifact checks; no real calculation output, model, potential, credential or database was added. Only this repair report is newly tracked audit documentation; temporary fixtures/logs/venvs/wheels remain external.

## Reproducible commands and evidence retention

The committed tests are executable durable reproductions, not merely references to a local scratch path. Run the exact focused command above with `tests/test_thickness_workflow_safety.py::test_generated_payload_positive_and_reentry`, `::test_relaxation_failure_stops_handoff`, `::test_static_failure_never_completes`, `::test_atomic_handoff_failure_does_not_enter_static`, and `::test_summary_uses_real_structures_formula_and_current_state` to inspect the actual setup/chain/static/handoff/summary behavior.
For the old P1, obtain the base function via `git show fae4339f7f91b52c13f4b993c9791e7110f13249:scripts/convergence/setup_true_fe110_thickness_retest.py`, AST-extract only chain_lsf/last_toten, and execute its unchanged shell in a synthetic directory with Bash source(){ return 0; } and mpirun(){ record-call; return 9; }. The exact base/shell hashes and observed results above bind that reproduction. Do not run the real vendor initialization or VASP arguments.
Current test logs (stored externally) and their SHA-256 digests:

- focused: `1c016e8eb79077c5ad8a5a582931847569ab33e67fb5e8ddf8c79fe5262199d4`; started `2026-09-10T08:06:52.211876+00:00`.
- ruff: `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18`; started `2026-09-10T08:06:18.060519+00:00`.
- full: `f8b906c8b8d5387aaddb5a5d87c74a44873a4f64c17b01c8acd78ecc7b2edf71`; started `2026-09-10T08:06:19.452138+00:00`.
- B1: `e9455a5ea3b7660029c6d651cbce02c9b740fd61b8fa52a2e3b27b6b85971780`; started `2026-09-10T08:17:32.758718+00:00`.
- B2: `c2d8e379f66e6f76bc786518355a59cea98677a88f254d795b83c051271e81a7`; started `2026-09-10T08:20:52.545380+00:00`.
- AC_B2_001: `41269335f7e97978182913c4198ac6a2cfc593068903998c42fe79b43cd8d50b`; started `2026-09-10T08:22:36.251147+00:00`.
- B4: `0be4dd5220b3cc81b25a3759e47d15025b1dc1cdc3117ccb17dda1e92c476b8c`; started `2026-09-10T08:23:15.426646+00:00`.
- B5: `520d08eb83188dd5a577b7c88a4a569c57a097ef402034e6e3af5c14c6142ea1`; started `2026-09-10T08:23:37.042445+00:00`.
- B6: `9dfe504a167662fe7fcbc3dbdb779f5053105a1b1127bef537384c839a0bdbe8`; started `2026-09-10T08:24:04.406599+00:00`.
- B7: `4b92679994b705dc327607e71a7c0b35696064e4fed6704efb6fd13906af72d6`; started `2026-09-10T08:24:08.941121+00:00`.

## Compatibility, gaps and disposition

- Existing input-only setup works; previously run directories now refuse before writes. Existing outputs/attempts are never automatically removed, relocated or reinterpreted as fresh evidence. Copy/recover scientifically useful inputs only through a separately authorized review into a new workspace.
- Bash plus an installed core Python package is a new explicit payload deployment prerequisite. THICKNESS_* selectors are documented; no HPC environment or deployed legacy script was modified. Python failures do not fall back to grep.
- Known repaired-scope defects remaining: none demonstrated. Required pending platform evidence: repaired-commit Linux CI. Real HPC environment, filesystem behavior, MPI signal propagation and scheduler integration remain production-only unverified; tests use inert processes and temporary files.
- Read-only startup repo-state audit observed the existing managed projection drift (one error/one review request at transition_state_search in docs/06_MODULE_MAP.md). The last-recorded task-current Dimer monitoring conflict is preserved. No sync, supersede, state event or backlog rewrite.
- AC-CLOSEOUT-B1-001 and AC-CLOSEOUT-B2-001 are closed for this repair scope by the current local software evidence; whole-repository acceptance is not asserted. All previous NOT_READY_TO_MERGE reports remain intact.
- DEVELOPMENT_WORKSPACE_SYNC=NOT_PERFORMED; PRODUCTION_DEPLOYMENT=NOT_PERFORMED; external_scientific_actions=0. Fake calculation counts in the matrices are not real external actions.
- Publish only the task-owned changes on codex/ac-closeout-thickness-workflow; no merge, main update or automatic next audit/optimization.
