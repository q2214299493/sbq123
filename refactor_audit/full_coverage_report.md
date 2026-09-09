# Phase B0 — Full Repository Coverage Audit

- **Repository:** C:\Users\86177\Desktop\work
- **Audit date:** 2026-09-09, Asia/Shanghai.
- **Branch / HEAD:** refactor/v2-architecture-repair / 3a4c23f3bae8da264323fea75d6fe593ca562845.
- **Baseline:** actual dirty working tree, not HEAD, the GitHub release, or historical refactor reports. Initial Git status contained 66 modified and 286 untracked entries; an untracked directory entry can represent many files.
- **Authorized output:** this report only. No source modification, refactoring, deletion, renaming, commits, remote commands, production database access, or scientific jobs.
- **Disposition:** B0 inspection completed. This is **not a release PASS or scientific acceptance**.

## A. Repository overview

### Scope and method

Read AGENTS.md, tasks/current_task.md, docs/02_CURRENT_STATE.md, docs/06_MODULE_MAP.md, modules/README.md, module ownership/gate documentation, and the existing refactor_audit material. Used the VASP workflow router to identify scientific owners without executing their workflows.

Inspection combined whole-repository metadata classification, AST parsing, a static import graph, entrypoint/duplicate extraction, targeted implementation and test review, configuration/schema validation, shell/PowerShell/JavaScript inspection, and synthetic in-memory negative probes. The appendix lists every active Python file in the static scan.

**Coverage means inspection coverage. No statement, branch, or runtime test-coverage percentage was measured.** All active files received static screening; risk-relevant functions received deeper manual review. This does not mean every branch of every function or every third-party dependency was manually audited. Findings identify their evidence level.

| Active Python area | Files parsed | Source lines | Function/method definitions | Test definitions |
|---|---:|---:|---:|---:|
| scripts/ | 193 | 43,327 | 1,273 | 0 |
| modules/, excluding nested archive | 6 | 166 | 8 | 0 |
| Repository skills/ | 4 | 943 | 45 | 0 |
| tests/ | 63 | 17,332 | 679 | 495 |
| **Total** | **266** | **61,768** | **2,005** | **495** |

The 495 test definitions are not executed cases; parametrization changes case counts. The scan found 91 Python main guards, plus three packaged CLI entries in pyproject.toml:16: repo-state, registry-promote, registry-write.

| Additional surface | Inspection | Boundary |
|---|---|---|
| Configuration / skill configuration | 40 YAML and 7 JSON documents parsed; 7 schema definitions meta-validated | Syntax and schema-definition validation, not all production instances |
| CI | Entire .github/workflows/state-manager.yml | Linux/Python 3.11, editable install, Ruff, pytest; no new CI run checked |
| Shell / PowerShell / JS | 11 shell scripts, git_snapshot.ps1, registry_excel_writer.mjs | Static inspection; no job execution or workbook writes |
| Database | SQL schema, migrations, connection/batch/promotion code, endpoint extension | No real SQLite database opened or migrated |
| Templates | INCAR report template; VASP/LSF builders; adsorption geometry and TS strategy templates | Historical examples are not newly accepted results |
| calculations/ | 182 code-like files inventoried and pattern-scanned; Python syntax checked; relevant writers sampled | No large VASP outputs or live calculations inspected |
| outputs/ | Broader filesystem scan found 83 code-like files including JS; Python syntax checked; roles sampled | Generated deliverables/copied runners are not active source authority |
| scientific-problem-compiler/ | Own package/CLI/README boundary reviewed; 93 code-like files scanned; Python syntax checked | Independent project, not fully behavior-audited or merged into work |
| Archives/environments | Classified from existing inventory and nested-archive inventory | Third-party and historical copies excluded from active remediation |

The ignore-aware rg inventory found 846 files in scripts/modules/skills/configs/tests/.github, including archived material. Its 334 Python files include 68 beneath modules/state_handoff/archive; excluding these yields 266 active-scope files. Ignore-aware and broader filesystem counts intentionally have different denominators.

The existing repository_inventory.csv has 47,965 rows, including 37,213 root-archive files, 869 .venv-refactor files and 5,117 calculation files. It is a historical metadata snapshot, not the current active-source denominator.

### Verification actually performed

| Check | Result |
|---|---|
| repo-state audit --phase start | Exit 0, zero errors; three warnings/review-required classifications: .venv-refactor, refactor_audit, scientific-problem-compiler outside root contract |
| Active Python AST | 266/266 parsed, zero syntax errors |
| Resolved static import graph | 761 directed edges; one multi-module strongly connected component |
| Configuration / schema | 40 YAML + 7 JSON parsed; seven schemas meta-validated; zero errors |
| Negative probes | Source-level behaviors in E/F/G reproduced in memory with python -B; no persistent writes |
| Existing Ruff baseline | Says “All checks passed!”; historical artifact, not a fresh lint run |
| Existing pytest baseline | Four collection errors; not a passing test run |
| Fresh pytest/Ruff/full integration suite | Not run for this documentation-only audit |
| Remote/runtime/scientific verification | Not run |
| State synchronization | Not run because it can update managed files, conflicting with “only produce the audit report” |

Early inspection helpers hit Windows decoding/output-size issues; compact inventory/configuration checks were rerun successfully. No validation success is inferred from a truncated pipeline or failed helper.

### Classification

Every issue has a primary B1–B7 workstream. Cross-cutting effects are noted, without duplicating issue counts.

| Workstream | Meaning |
|---|---|
| B1 Execution | Authorization, remote execution, upload integrity, submission/recovery |
| B2 Scientific Contract | Reaction identity, convergence, compatibility, TS acceptance |
| B3 Evidence and ML Data | Provenance, retrieval trust, model labels, learning/retry evidence |
| B4 Registry | Persistence, accepted records, transactions, migrations, Excel |
| B5 Architecture Boundary | Ownership, dependencies, adapters, duplicate implementations |
| B6 Documentation/Data Governance | Authority, current state, audit provenance, source classification |
| B7 Release Environment | Packaging, dependencies, platforms, reproducible baseline |

Evidence: **P** = in-memory probe; **S** = source/control-flow observation; **R** = integration/fault-injection confirmation still needed. Severity describes potential impact, not proof existing scientific results were affected.

## B. Module ownership map

Statuses are from docs/06_MODULE_MAP.md, not fresh scientific assessments.

| Owner / status | Implementation and inputs | Required boundary/output | Findings |
|---|---|---|---|
| catalysis_data_retrieval / Active | Repository retrieval skill, allowlist, record/image schemas, adsorption evidence gate | Whitelist first; controlled journal fallback; reviewed motif provenance only | B3-01–02 |
| convergence_workflow / Active | scripts/convergence, true_fe110_production.yaml | Compatible branch; five-layer production policy locked | B2-01, B2-03 |
| fe_convergence_baseline / Active | Module validator and preserved bulk package | Bulk evidence cannot automatically switch production slab | B6-01 |
| adsorption_workflow / Active | scripts/adsorption, vasp_inputs, result and promotion gates | Validated geometry, compatible references, traceable final energies | B2-01, B3-01, B4-03 |
| adsmind_lite / Active | scripts/adsmind_lite, site/prescreen/adsorbate rules | Candidate generation/deduplication, no global-minimum or DFT claim | B3-01, B5-03 |
| transition_state_search / Active | scripts/ts_strategy_engine; neb_agent numerical backend | Endpoint → contract → reviewed path → NEB/CI-NEB → optional DIMER; sole execution gate | B1-01–05, B2-01–04 |
| TS endpoint subsystem / TS owner | scripts/ts_endpoint; five modules compatibility aliases | Stable product reuse, atom identity, purpose, explicit DB extension | B2-02, B5-02, B5-05 |
| DIMER / TS owner | Dimer/path gates, analysis, reviewed preparation scripts, preflight | Force/curvature/geometry gates and bound review; no automatic TS acceptance | B2-01, B2-04 |
| ts_vibrational_validation / Active | scripts/ts_validation, frequency gate/protocols | Bound saddle/mode/scope; method-specific acceptance; separate thermochemistry gate | B2-04 |
| Local learning / TS owner | strategy_learning, learning_evidence/store, templates | Immutable reviewed outcomes; no scientific/execution authority | B3-03, B5-02 |
| GPU/ML branch / TS + adsorption owners | AQCat25/dual-model/MatRIS, handoffs, labels/training/exclusions | GPU candidates return through work; VASP force labels are not final energies | B1-05, B2-01, B3-03 |
| incar_custodian / Active | Repository skill and profile mapping | Advice after geometry/path/mode gates; no duplicate parameter authority | B5-04–05, B7-02 |
| calculation_registry / Active | SQL v8, registry_schema/write, TS evidence, Excel writer | Scientific owners accept; storage preserves provenance/idempotency | B4-01–04, B5-02 |
| state_handoff / Active | scripts/state_manager, events, policy/schema, projections | Governance only; live files retain scientific authority | B5-01, B6-01 |
| git_versioning / Active | git_snapshot.ps1, ignore/attribute rules | Only authorized task-owned commits/pushes | B6-02, B7-02 |
| memory_migration / Completed | Handoff documentation and archives | No reconstruction of live scientific state from memory | B6-01–02 |
| kinetic_data / Planned | Module contract and registry/provenance inputs | Validated kinetics dataset; no implementation inferred from a README | B6-01 |
| thermochemistry / Blocked | Frequencies, conditions, low-mode prerequisites | Own validation required for free energies | B2-04, B6-01 |
| reaction_network / Blocked | Species/site/TS/free-energy contracts | Balanced mechanism; no invented missing reaction data | B6-01 |
| baseline_mkm / Blocked | CATKINAS mapping and contract | Requires validated kinetics; example execution is not acceptance | B6-01, B7-02 |
| coverage_mkm / Blocked | Baseline plus interaction model | No invented coverage model | B6-01 |
| surface_kmc / Blocked | Zacros, lattice/event contract | Validated lattice/events/rates required | B6-01, B7-02 |
| reactor_simulation / Blocked | Reactor definition and validated rates | Transport/reactor assumptions need evidence | B6-01 |
| sensitivity_uncertainty / Blocked | Valid model and uncertainty inputs | No invented confidence intervals | B6-01 |
| Independent SPC | Own pyproject, spc CLI, domain packs/tests | Planning/export only; independent ownership | B6-02 |

No scripts→modules or scripts→tests production edge was found by the static resolver. Historical aliases point toward scripts.ts_endpoint as documented. Dynamic imports, shell commands and string-loaded plugin APIs are not fully represented.

## C. Dependency problems

### B5-01 — Persistence imports lifecycle policy [Medium, S]

scripts/state_manager/lifecycle.py:11 imports EventStore; store.py:122 imports ALLOWED_TRANSITIONS/effective_phase inside _validate_task_transition. This is the single detected import cycle. The local reverse import avoids demonstrating an import-time crash, but storage depends on a higher-level policy and becomes harder to test independently.

Later extract only the small pure lifecycle contract or use an explicit validation boundary. Preserve hashes, supersession, review and acceptance semantics.

### B5-02 — Cross-cutting registry infrastructure is located in the TS domain [Medium, S]

registry_write.py:11 imports scripts.ts_strategy_engine.registry.open_registry; Excel and endpoint persistence use the same TS utility. transition_state_search/README.md:632 calls it the SQLite utility owner, while the module map assigns cross-cutting registry ownership elsewhere.

Sharing one connection utility is beneficial; its namespace/ownership is inverted. Later move neutral connection/version/transaction primitives after characterization, without recreating competing persistence or acceptance layers.

### B5-03 — Optional adsorption output is required by implementation [Medium, P/S]

adsmind_lite/plan_adsorption_candidates.py:56 makes --output optional; line 98 unconditionally calls artifact_io.write_json(args.output, plan). artifact_io.py:71 dereferences path.parent.

Probe: write_json(None, {}) raises AttributeError before writing. A valid stdout-only CLI reaches a failure after planning. Add an actual CLI regression for omitted output, not only planning-function tests.

### B5-04 — Large orchestrators obscure boundary review [Medium, S]

dual_model_ml_neb.py has 1,993 lines; offline_mlip_fusion_feasibility.py 1,354; mlip_same_structure_benchmark.py 1,295; matris_energy_force_finetune.py 990; state projections 957. They combine substantial orchestration, artifact construction and policy checks.

Size is not itself a defect or a reason to rewrite. It identifies where later extractions need entrypoint/evidence-equivalence tests. Separate I/O and pure checks only after B1–B4 behavior is fixed and frozen.

## D. Duplicate logic list

### B5-05 — Semantic duplication and compatibility wrappers [Medium/Low, S; deletion eligibility unconfirmed]

| Logic / locations | Assessment | Constraint |
|---|---|---|
| OUTCAR: neb_agent/utils_vasp.py:67, aqcat25_calibration.py:25, adsorption/analyze_fe110_ch_h_relaxation.py:17 | Different completion/force/energy projections; potential semantic drift | Preserve evaluation boundaries, TOTEN, complete force-block selection, streaming |
| INCAR: vasp_result_gate.py:10, dimer_analysis.py:15, custodian raw_incar_value:46; vasp_inputs and gas_vasp_common renderers | Multiple readers/renderers, not automatically interchangeable | Characterize comments/repeated keys/compact assignments/numeric notation/stage overrides |
| Structure: neb_agent/utils_structure.py:30, AQCat25 symbol reader, ASE adsmind reader | Full cell/flags vs symbol-only vs ASE contracts | Do not consolidate through a lossy parser |
| _sha256: dimer_gate_common.py:18 and ml_neb_path.py:230 | Exact AST body duplicate | Low-risk future shared primitive; preserve hex/type checks |
| Destination checks: active_learning_path_common.py:12 and active_learning_handoff.py:18 | Similar empty-destination policy | Define resumability first, see B3-03 |
| Atomic writes: state_manager/proposals.py:226 and artifact_io.py:70 | Similar mechanism, different formats/lifecycle needs | Preserve fsync, same-directory temp file and rollback behavior |
| Production/test _structure_ref helpers | Exact body match | A mirrored helper is not a second production authority; avoid implementation-derived test expectations |
| Five endpoint aliases; active_learning.py facade; neb_agent/utils_report.py | Intentional compatibility re-exports | Preserve until callers and migration are established |
| Restart/crop/split CLIs | Similar file-copy scaffolding, different scientific input semantics | Preserve provenance, contiguous image and atom-map requirements |

**Dead-code candidates:** supplied Vulture findings are mostly 60% confidence. _incar_nelm, proposal_preview and event_map deserve caller review, but are not proven dead. VASP builders, endpoint APIs, ASE callbacks (get_removed_dof/index_shuffle/todict), dataclass fields and row_factory assignments have framework/public contracts. No deletion is justified by Vulture or this audit.

## E. Potential bugs

### B1-01 — Initial submission authorization lacks mandatory source binding [High, P/S]

execution_path_rules.py:191–211 accepts NO_OUTPUT, path_reviewed=True and preflight.passed=True, returning an initial submission action without source_bindings_valid. execution_gate.py:106 recomputes the same rules. submission.py:348–362 verifies current bundle integrity, but not the truth of a self-asserted path/geometry review.

Probe: decide_execution with empty geometry/thresholds, analysis.status=NO_OUTPUT, path_reviewed=True and passed ordinary_neb preflight returns READY_FOR_ORDINARY_NEB_SUBMISSION and SUBMIT_VASP, with empty bindings; validate_decision accepts it.

No job was submitted. The defect is a review claim entering the authoritative gate as booleans instead of current reviewed evidence. Protect both public gate and actual executor.

### B1-02 — Remote path traversal and unchecked POTCAR digest interpolation [High, P/S]

submission.py:25 permits dots/slashes in its ~/sbq prefix regex. Probe: ~/sbq/../../outside/job matches. The containment claim at line 349 is therefore stronger than its check.

Separately, potcar_sha256 is interpolated directly into the remote shell at line 373 without require_sha256 validation here. The supplied digest is not part of the local preflight bundle at lines 67–81.

Risks: resolved-root escape, malformed digest reaching shell parsing, and a checksum-valid POTCAR differing from the reviewed identity. No remote symlink/injection experiment was performed. Later enforce canonical paths, exact digest syntax and reviewed POTCAR binding before any I/O.

### B1-03 — Submission idempotency has a concurrency window [High, R]

submission.py:338–347 checks record/attempt existence; lines 377–387 create the unresolved marker later via an overwrite-capable atomic writer. No exclusive reservation spans those operations.

Two callers, especially with reuse_uploaded=True, can both pass the check before either creates the marker. Existing sequential retry tests do not establish concurrent exactly-once behavior. Use an exclusive attempt claim while preserving unresolved-outcome recovery. No scheduler concurrency test was run.

### B1-04 — Fresh uploads lack remote manifest revalidation [High, R]

submission.py:366–370 verifies remote hashes only for reuse_uploaded. The fresh path copies files, then checks POTCAR and input non-emptiness before bsub. Staging copy at lines 485–496 occurs after local hashing.

Mutation during staging or after upload can diverge from the authorized bundle. This is a race/integrity risk, not an observed transfer failure. Test and require equivalent exact-manifest validation on both branches immediately before execution.

### B1-05 — GPU preamble failures may omit producer records [Medium, S/R]

GPU wrappers expand required environment variables, validate roots, source helpers and check vendors before later exit-record handling. Examples: dual_model_ml_neb_job.sh:15–40, aqcat25_ml_neb_job.sh:15–29, dual_model_ts_force_prediction_batch_job_v2.sh:15–45.

Setup failure, interruption or output-directory failure may bypass record creation. Missing records must remain UNKNOWN. Prefix-only /home/sbq/sbq/* checks also need canonical containment. Verify with a CPU shell harness and fake commands, not GPU jobs.

### B4-01 — Workbook, receipt and SQLite are not one recoverable transaction [High, S/R]

registry_excel_promotion.py:481–500 inserts a DB row, writes a JSON receipt, then replaces the workbook. open_registry commits afterward (ts_strategy_engine/registry.py:53–56). Failure handling removes only the temporary workbook.

A failed replacement may leave an orphan receipt; a failed commit after replacement may leave a changed workbook/receipt without its DB row. A crash has similar windows. Workbook hash checking at line 454 is not a lock through replacement. build_plan rejects existing receipts at line 367, potentially obstructing retry.

Later define a recoverable journal/reconciliation protocol; preserve original data. No real workbook/DB was touched.

### B4-02 — Status-only registry manifest passes validation then fails planning [Medium, P]

registry_write.py:77–84 accepts omitted rows if workflow_status_changes is nonempty; _plan_with_connection accesses batch["rows"] at line 201.

Probe: a valid status-only manifest passes validation, then _plan_with_connection(None, batch) raises KeyError 'rows' before any connection use. The accepted public shape and implementation disagree.

### B4-03 — Generic registry transport does not verify scientific acceptance [High, S/R]

registry_write.py:17–25 permits results/reviews/files/compatibility rows; lines 195–247 check columns/required keys/idempotency; lines 256–315 accept a caller confirmation hash and insert data. It does not itself revalidate source contents, method compatibility or scientific acceptance.

This is a trust-boundary risk, not a claim generic insertion is inherently wrong: persistence is deliberately transport, and acceptance is owned elsewhere. Generated batches can nevertheless carry accepted_* flags and review strings without proving they came through that owner. Later require owner-validated manifests for accepted-result operations while preserving legitimate backfill/status transport.

### B4-04 — Migration failure can leave committed intermediate versions [Medium, S/R]

registry_schema.py:253–276 commits each version step; final required-column/FK checks occur at lines 277–286. open_registry(migrate=True) can trigger this before TS writes.

Stepwise migration may support recovery, but is not whole-chain rollback. Test failure at each step and late validation using fixtures/copies, and document restart/backup semantics. Do not migrate the real database to validate a refactor.

## F. AI reliability risks

### B3-01 — Adsorption READY/target-match claims are self-attested [High, P/S]

adsmind_lite/evidence_gate.py:47–48 trusts exact_surface_match/exact_adsorbate_match booleans; the whitelist branch does not invoke the retrieval allowlist validator. Line 56 can use source ID "unidentified". Line 80 sets build_ready from the truthiness of reviewed_structure_template.

Probe: a nonempty string naming a nonexistent template yields READY. This proves planner overstatement, not downstream construction or VASP acceptance.

An assistant can supply plausible flags, unverified sources or missing templates and receive a stronger status than evidence supports. Bind target identities, validated retrieval records and reviewed template contents. Preserve energy_import_allowed=False and global_minimum_claim=False.

### B3-02 — Source manifests silently omit missing requested files [Medium, P]

artifact_io.py:38–41 filters requested paths by is_file(); lines 44–54 validate only surviving entries.

Probe: one existing file plus one nonexistent file yields a one-entry manifest that validates true. Callers that separately enforce required roles may be safe; the helper alone does not prove completeness. Distinguish optional-source collection from binding every required source.

### B3-03 — Partial ML label preparation is preserved but not resumable in place [Medium, S/R]

active_learning_path_labels.py:107 requires an empty destination. Lines 114–129 retain partial directories on failure and leave state unadvanced. active_learning_path_common.py:12–15 rejects that nonempty destination on retry.

Preserving diagnostics is correct; “retry-safe” is weaker than resumable. A later-image failure requires a new destination or manual recovery. Test fail-on-image-N and resume without deletion/overwrite or accepting partial output.

### Valid safeguards to preserve

Learning uses exact key/type validation, finite nonnegative costs, source-hashed observation pointers, immutable events, explicit reviewed outcome revisions and template-backed ts_validated status. It separates hypotheses from confirmed root causes and sets automatic_submission=False/authorizes_training=False.

Do not replace these with narrative summaries or a single PASS flag. A producer/reviewer string is not independent proof of authorship or review; retain explicit trust boundaries and cross-artifact identity checks.

## G. Scientific workflow risks

### B2-01 — Final SCF status can inherit an earlier convergence marker [High, P/S]

neb_agent/utils_vasp.py accumulates electronic_convergence_reached across all OUTCAR lines with OR. vasp_result_gate.py:49–63 lets it override final OSZICAR evaluation. The choice completed or current also prefers an earlier completed evaluation over a newly running tail.

Probe: final iteration 200, NELM=200, delta_e=1 eV, EDIFF=1e-5, plus an earlier OUTCAR EDIFF marker returns electronically_converged=True.

Callers include DIMER analysis and VASP force-label collection (dimer_analysis.py:96; collect_dual_model_ts_vasp_labels.py:161–168). This does not prove an existing accepted calculation is wrong. Bind convergence to the final relevant evaluation and distinguish unfinished tails, rotations, ionic steps and normal termination.

### B2-02 — Rehashed normalized contracts bypass semantic validation [High, P]

contract.py:59–74 returns normalized input after checking required field presence and self-consistent hashes. Raw normalization separately checks reaction indices against the atom map at lines 263–272.

Probe: normalize a valid two-atom contract, replace reaction_atoms with [999], recompute contract_sha256; _verified_normalized_contract accepts it.

Hashes prove content integrity against supplied digests, not scientific validity. Enforce equivalent atom-map/index/identity/compatibility/coordinate rules through both entrypoints without accidentally renormalizing indices twice.

### B2-03 — Numeric/domain validation is incomplete [High, P/S]

contract.py:185–203 checks mesh length, not positive components; ENCUT is only cast; _nonempty_text turns None into "None". Comparison-only constraints do not reject NaN. matched_static_evidence.py:109–110 requires non-null eV data but not finiteness; barrier_values:141–150 only rejects negative barriers.

Probes: compatibility accepts ENCUT=-1, mesh [0,-1,1], material=None→"none"; energies [0, Infinity, 1] return infinite barriers; canonical_json emits NaN rather than rejecting it.

No accepted DB record was inserted. Enforce finite/domain-valid values at ingestion and accepted-energy boundaries; never fill absent evidence with numeric defaults.

### B2-04 — Validation pipeline can combine unrelated DIMER/VFA summaries [High, P/S]

validation_pipeline.py:43–83 loads two independent summaries; _dimer_gate/_vfa_gate inspect fields but do not verify common saddle/contract/atom-map/compatibility identity. Lines 107–114 emit TS_ACCEPTED and scientifically_validated_ts=True. Soft review at lines 142–165 is accepted by decision text without the stricter handoff's binding checks.

Probe: DIMER saddle hash A and VFA saddle hash B, with otherwise passing summary fields, yield TS_ACCEPTED and scientifically_validated_ts=True.

This can mislead downstream automation. It does not prove record_ts_validation, with its additional evidence gates, accepts the same data. Bind actual source identity before scientific acceptance. A missing requested topology file also must not silently establish a single-step path.

### Scientific invariants to preserve

- Active true Fe(110) five-layer branch, atom order, Selective Dynamics, magnetism and final-energy convention remain unchanged.
- Converged production TOTEN at ISMEAR=1/SIGMA=0.20 eV is distinguished from legacy 0.10 eV statics and separately validated gas references.
- Path-stage validity, pilot success, low force and negative curvature alone are not final TS validity.
- **Current approved DIMER policy does not require downhill connectivity for DIMER-plus-target-imaginary-mode acceptance. This choice is not flagged as a bug.** Fix source binding without imposing a new scientific method.
- Frequency scope, optional threshold grading, TS acceptance and kinetic/thermochemical readiness must remain distinct.
- AQCat25/MatRIS/Sella outputs are candidate predictions. Exact-structure VASP force labels remain force_label_only_not_reportable_final_energy.
- MatRIS exclusions compare exact/rounded geometry; successful templates require Grade-A/barrier evidence and transfer strategy, not external coordinates/energies.
- Blocked MKM/KMC/reactor modules remain blocked; documentation-only plans are not implemented production workflows.

## H. Missing tests

### B7-01 — No verified current test/release baseline [High, S/R]

baseline_pytest.txt records four collection errors involving tests.test_ml_sella_candidate, tests.test_dual_model_ml_neb and the modules namespace. tests/conftest.py:7–16 adds leaf source directories; pyproject packages scripts only. Invocation mode, editable installation and namespace/environment shadowing may explain the failures; exact root cause was not established by a fresh collection run.

Baseline files do not bind command, interpreter, dependencies, exit status and dirty source hash together. Historical Ruff PASS is not test success. Establish a reproducible baseline before comparing refactor outcomes.

### B7-02 — Deployment/environment boundaries are insufficiently exercised [Medium, S/R]

CI is Ubuntu/Python 3.11 with editable installation. Package discovery includes scripts only; defaults locate external-to-package configs/SQL/skills (registry_schema.py:7–8 and vasp_inputs). Excel needs a separately supplied Node/artifact-tool runtime. No root lockfile was found.

A checkout may be the intended deployment contract; a relocatable wheel is not proven. Declare supported invocation/platform/runtime/resource contracts, then test those. Do not invent universal platform or standalone wheel requirements.

### Decisive missing regressions/integration tests

Rows identify scenarios not found in the bounded relevant-test review, not proof of zero transitive coverage.

| Workstream / issues | Existing tests inspected | Missing scenario |
|---|---|---|
| B1-01 | NEB execution gate/submission | Initial action with absent/forged/stale source evidence, through gate and actual executor |
| B1-02 | External command/backend/submission | Traversal/symlink escape, malformed digest, wrong reviewed POTCAR identity |
| B1-03 | Sequential unresolved/failure/success submission | Concurrent callers, only one mocked bsub; lost-response recovery |
| B1-04 | Manifest-only upload | Mutation during staging and fresh-upload remote mismatch |
| B1-05 | Wrapper source/timeout checks | Missing env/helper/vendor, mkdir failure, record-write failure, interruption |
| B2-01 | Result gate/streaming/VFA | Earlier EDIFF then NELM exhaustion, unfinished tail, appended/truncated output, DIMER evaluation semantics |
| B2-02 | Contract/strategy | Rehashed invalid normalized contract; duplicate/out-of-range atom map and contradictory events |
| B2-03 | Compatibility/strategy | NaN/Infinity, nonpositive mesh/ENCUT, null identity, accepted-energy rejection |
| B2-04 | Pipeline/VFA | Cross-saddle/contract VFA, stale scope/mode/soft review, missing topology |
| B3-01 | Evidence gate/prescreen | Missing/wrong template, wrong target behind flags, source outside allowlist |
| B3-02 | Artifact I/O | Missing required input among valid sources; optional-source semantics |
| B3-03 | Active-learning/path | Fail image N and resume in place without destructive cleanup |
| B4-01 | Excel plan/writer timeout | Small synthetic workbook integration; receipt/replace/commit failures, concurrency, recovery |
| B4-02 | Registry write | Omitted rows in status-only input; explicit empty rows and multiple transitions |
| B4-03 | Registry/schema/TS evidence | Self-authored accepted flags cannot bypass owner validation |
| B4-04 | Registry schema/endpoint migration | Every migration failure point, late FK failure, restart/backup contract |
| B5-01–02 | State manager/endpoint | Isolated storage policy and neutral registry imports; preserve legacy APIs |
| B5-03 | Prescreen functions | CLI without --output; stdout and exit-status behavior |
| B5-04–05 | Existing module tests | Parser/adapter characterization before extraction; framework callbacks preserved |
| B6-01–02 | Repository/state contracts | Coherent current projections; dirty-tree audit attribution; correct inventory denominator |
| B7-01–02 | Package test/Linux CI | Supported invocation/namespace reproduction, declared platform/resources, Node writer |

Static analysis found **80 scripts files without a direct resolved test import**. Some have facade/subprocess/conftest coverage; this is not “80 untested files.” Prioritize real entrypoint tests for reviewed NEB/DIMER helpers, label collection/held-out preparation, adsorption planning, restart/crop/split and environment adapters.

## I. Recommended refactor order

No item below has been executed.

1. **B7 baseline prerequisite:** freeze task-owned source hashes and record actual supported interpreter/install/invocation and collection result. HEAD alone is insufficient.
2. **B1 Execution:** close authorization, path/digest, fresh-upload and concurrency/recovery gaps. Preserve sole execution authority.
3. **B2 Scientific Contract:** final-evaluation convergence, normalized semantic checks, finite quantities and DIMER/VFA binding; freeze negative fixtures and scientific invariants.
4. **B3 Evidence and ML Data:** bind retrieval/templates/required sources and recover partial label preparation; keep prediction/stage/accepted science separate.
5. **B4 Registry:** accepted-result transport contract, recoverable Excel/DB update, status-only manifests and migration/idempotency tests.
6. **B5 Architecture Boundary:** remove state cycle, relocate neutral registry utilities, then deduplicate/extract large parsers/orchestrators under characterization tests.
7. **B6 Documentation/Data Governance:** reconcile authoritative current projections and audit provenance; classify archives/SPC/generated files without incidental deletion/moves.
8. **B7 release completion:** validate supported clean-checkout/platform/Node/runtime contracts and bind exact results to repaired source.

### B6-01 — Current documents mix ages and contradictory projections [Medium, S]

docs/02_CURRENT_STATE.md has a 2026-08-27 header, later schema-v8 notes, and a registry subsection still describing migration through v7/older counts. Next Actions keep jobs 9622414/9622444 out of the workbook while later text describes all 19 unique Step-12A states as promoted. tasks/current_task.md says no active task; the module map still directs Dimer 9746548 monitoring from an explicitly old checkpoint.

These are documentation discrepancies, not live queue facts. Reconcile from authoritative events/files when separately authorized. Do not silently change managed state during B0.

### B6-02 — Existing audit provenance mixes environment/archive/generated files [Medium, S]

python_files.txt has 15,469 lines starting with .venv-refactor dependencies; repository_tree.txt has 113,931 lines; the CSV is archive-dominated; Vulture includes archived VASP2Kinetics. final_b0_git_status.txtcd has the same size/displayed content as final_b0_git_status.txt and is unexplained, not authorized for deletion.

Working source, installed source, releases, generated runners, independent SPC and historical code need explicit classification. Historical “FINAL”/“PASS” filenames and Git status do not establish current coverage. Keep raw evidence; later bind compact command/source/environment manifests.

### B0 closure and uncertainty

No current VASP result, TS, barrier, workbook, registry row or model was scientifically revalidated. Source defects do not prove existing scientific corruption. Scientific constants and acceptance policies were not changed.

Unverified: runtime coverage, real scheduler behavior, shell failures, concurrent submissions, Excel/SQLite crash recovery, package relocation, GPU/training behavior and scientific validity. These remain assigned to the matrix above.

A suspected learning default-path error was checked and **rejected**: parents[2] of learning_store.py is the repository root; DEFAULT_DATABASE is work/data/project_registry.sqlite3. It is not a finding.


## Appendix 1. Complete active Python static-scan ledger

Each row was AST-parsed and included in import/entrypoint/duplicate screening. Lines and definitions are inspection metrics, not execution coverage. Deeper review targets are cited in findings above.

### scripts/

| File | Lines | Function/method definitions |
|---|---:|---:|
| scripts/__init__.py | 1 | 0 |
| scripts/adsmind_lite/__init__.py | 1 | 0 |
| scripts/adsmind_lite/adsmind_common.py | 93 | 10 |
| scripts/adsmind_lite/analyze_relaxed_adsorption.py | 36 | 2 |
| scripts/adsmind_lite/audit_remote_fe110_batch.py | 175 | 7 |
| scripts/adsmind_lite/candidate_export.py | 36 | 1 |
| scripts/adsmind_lite/candidate_generation.py | 276 | 10 |
| scripts/adsmind_lite/core.py | 27 | 0 |
| scripts/adsmind_lite/deduplicate_adsorption_states.py | 30 | 2 |
| scripts/adsmind_lite/detect_surface_sites.py | 43 | 2 |
| scripts/adsmind_lite/evidence_gate.py | 113 | 6 |
| scripts/adsmind_lite/export_vasp_ready.py | 42 | 2 |
| scripts/adsmind_lite/fts_prescreen.py | 205 | 10 |
| scripts/adsmind_lite/generate_adsorption_candidates.py | 37 | 2 |
| scripts/adsmind_lite/plan_adsorption_candidates.py | 114 | 2 |
| scripts/adsmind_lite/prescreen.py | 145 | 3 |
| scripts/adsmind_lite/relaxed_analysis.py | 447 | 21 |
| scripts/adsmind_lite/site_detection.py | 377 | 12 |
| scripts/adsmind_lite/state_deduplication.py | 94 | 6 |
| scripts/adsmind_lite/validate_candidates.py | 35 | 2 |
| scripts/adsorption/__init__.py | 1 | 0 |
| scripts/adsorption/analyze_fe110_ch_h_relaxation.py | 204 | 5 |
| scripts/adsorption/backfill_step12a_registry.py | 587 | 7 |
| scripts/adsorption/build_fe110_adsorption.py | 433 | 23 |
| scripts/adsorption/build_fe110_c2_coads.py | 125 | 6 |
| scripts/adsorption/build_fe110_care_isomers.py | 281 | 10 |
| scripts/adsorption/build_fe110_ch_h_coads.py | 240 | 9 |
| scripts/adsorption/build_gas_cho_chxo.py | 77 | 6 |
| scripts/adsorption/build_gas_h2_chx.py | 101 | 3 |
| scripts/adsorption/build_gas_oxygenated_isomers.py | 89 | 5 |
| scripts/adsorption/build_gas_step12a_references.py | 72 | 2 |
| scripts/adsorption/c2_coads_catalog.py | 177 | 3 |
| scripts/adsorption/c2_coads_geometry.py | 214 | 12 |
| scripts/adsorption/finalize_step12a_gas_references.py | 570 | 8 |
| scripts/adsorption/gas_vasp_common.py | 126 | 7 |
| scripts/adsorption/preflight_fe110_adsorption.py | 127 | 3 |
| scripts/adsorption/preflight_gas_references.py | 131 | 5 |
| scripts/adsorption/register_step12a_gas_reference_submission.py | 209 | 2 |
| scripts/adsorption/register_step12a_oh_restart.py | 166 | 2 |
| scripts/adsorption/render_fe110_ch_h_candidates.py | 75 | 2 |
| scripts/aqcat25_calibration.py | 239 | 6 |
| scripts/aqcat25_handoff.py | 207 | 9 |
| scripts/aqcat25_ml_neb.py | 740 | 30 |
| scripts/aqcat25_ml_path_committee.py | 254 | 5 |
| scripts/aqcat25_ts_active_learning.py | 11 | 0 |
| scripts/aqcat25_ts_checkpoint_validation.py | 112 | 3 |
| scripts/aqcat25_ts_force_prediction_batch.py | 171 | 4 |
| scripts/aqcat25_ts_force_prediction.py | 97 | 2 |
| scripts/aqcat25_ts_schema.py | 83 | 4 |
| scripts/aqcat25_ts_training_data.py | 108 | 4 |
| scripts/artifact_io.py | 95 | 11 |
| scripts/assess_dual_model_ts_heldout_errors.py | 187 | 3 |
| scripts/assess_dual_model_ts_vasp_errors.py | 285 | 4 |
| scripts/bind_reviewed_dimer_execution.py | 41 | 1 |
| scripts/collect_dual_model_ts_vasp_labels.py | 286 | 6 |
| scripts/convergence/common.py | 25 | 2 |
| scripts/convergence/setup_alpha_fe_bulk_smearing.py | 280 | 9 |
| scripts/convergence/setup_true_fe110_thickness_retest.py | 259 | 12 |
| scripts/dual_model_ml_neb.py | 1993 | 52 |
| scripts/dual_model_ts_force_prediction_batch.py | 323 | 8 |
| scripts/execution_backends.py | 141 | 6 |
| scripts/init_registry.py | 44 | 2 |
| scripts/jsonl_io.py | 22 | 1 |
| scripts/matris_energy_force_finetune.py | 990 | 18 |
| scripts/matris_finetune_speed_benchmark.py | 519 | 18 |
| scripts/matris_frozen_heldout_validate.py | 170 | 3 |
| scripts/matris_sella_local_peak.py | 304 | 11 |
| scripts/matris_sella_smoke.py | 123 | 4 |
| scripts/matris_training_exclusions.py | 258 | 7 |
| scripts/matris_ts_path_committee.py | 208 | 3 |
| scripts/ml_candidate_source.py | 52 | 2 |
| scripts/ml_sella_candidate.py | 170 | 6 |
| scripts/mlip_same_structure_benchmark.py | 1295 | 25 |
| scripts/neb_agent/__init__.py | 1 | 0 |
| scripts/neb_agent/analyze_neb_outputs.py | 317 | 6 |
| scripts/neb_agent/check_endpoints.py | 124 | 3 |
| scripts/neb_agent/cli_common.py | 34 | 3 |
| scripts/neb_agent/crop_neb_path.py | 39 | 1 |
| scripts/neb_agent/diagnose_path_geometry.py | 376 | 13 |
| scripts/neb_agent/generate_path.py | 319 | 12 |
| scripts/neb_agent/magnetic_continuity.py | 34 | 1 |
| scripts/neb_agent/path_quality_cli.py | 70 | 4 |
| scripts/neb_agent/path_quality_control.py | 330 | 7 |
| scripts/neb_agent/path_quality_service.py | 147 | 5 |
| scripts/neb_agent/pilot_validation.py | 202 | 8 |
| scripts/neb_agent/prepare_restart.py | 36 | 1 |
| scripts/neb_agent/remote_monitor.py | 87 | 5 |
| scripts/neb_agent/retrieval_prior_adapter.py | 76 | 2 |
| scripts/neb_agent/split_by_intermediate.py | 44 | 1 |
| scripts/neb_agent/submission.py | 540 | 15 |
| scripts/neb_agent/utils_report.py | 11 | 1 |
| scripts/neb_agent/utils_retrieval.py | 31 | 2 |
| scripts/neb_agent/utils_structure.py | 147 | 15 |
| scripts/neb_agent/utils_vasp.py | 148 | 4 |
| scripts/offline_mlip_fusion_feasibility.py | 1354 | 33 |
| scripts/prepare_aqcat25_ml_neb_handoff.py | 190 | 6 |
| scripts/prepare_dual_model_ts_active_learning_round.py | 294 | 4 |
| scripts/prepare_dual_model_ts_heldout_candidates.py | 465 | 8 |
| scripts/prepare_dual_model_ts_heldout_execution.py | 236 | 2 |
| scripts/prepare_matris_finetune_request.py | 307 | 8 |
| scripts/prepare_matris_remote_finetune_bundle.py | 332 | 4 |
| scripts/prepare_matris_replay_finetune_package.py | 547 | 11 |
| scripts/prepare_ml_candidate_active_learning.py | 150 | 5 |
| scripts/prepare_ml_candidate_rerun.py | 126 | 4 |
| scripts/prepare_reviewed_neb_peak_dimer.py | 113 | 1 |
| scripts/prepare_ts_heldout_aqcat_prediction_batch.py | 262 | 3 |
| scripts/prepare_ts_heldout_validation_candidates.py | 391 | 6 |
| scripts/prepare_ts_heldout_vasp_label_batch.py | 185 | 2 |
| scripts/registry_excel_promotion.py | 539 | 18 |
| scripts/registry_schema.py | 287 | 9 |
| scripts/registry_write.py | 372 | 10 |
| scripts/review_completed_neb_parent.py | 170 | 3 |
| scripts/scheduler_evidence.py | 106 | 5 |
| scripts/select_dual_model_ts_vasp_labels.py | 480 | 7 |
| scripts/state_manager/__init__.py | 6 | 0 |
| scripts/state_manager/__main__.py | 4 | 0 |
| scripts/state_manager/audit.py | 497 | 16 |
| scripts/state_manager/baseline.py | 152 | 6 |
| scripts/state_manager/checkpoints.py | 62 | 1 |
| scripts/state_manager/cli.py | 730 | 20 |
| scripts/state_manager/imports.py | 111 | 3 |
| scripts/state_manager/lifecycle_views.py | 62 | 1 |
| scripts/state_manager/lifecycle.py | 147 | 4 |
| scripts/state_manager/models.py | 670 | 36 |
| scripts/state_manager/projections.py | 957 | 35 |
| scripts/state_manager/proposals.py | 485 | 22 |
| scripts/state_manager/reconciliation.py | 99 | 2 |
| scripts/state_manager/review_reuse.py | 99 | 3 |
| scripts/state_manager/stale_items.py | 290 | 5 |
| scripts/state_manager/state_compaction.py | 89 | 1 |
| scripts/state_manager/store.py | 419 | 21 |
| scripts/ts_endpoint/__init__.py | 6 | 0 |
| scripts/ts_endpoint/database.py | 335 | 14 |
| scripts/ts_endpoint/evidence.py | 141 | 2 |
| scripts/ts_endpoint/generator.py | 174 | 6 |
| scripts/ts_endpoint/purpose.py | 261 | 7 |
| scripts/ts_endpoint/validator.py | 505 | 13 |
| scripts/ts_strategy_engine/__init__.py | 1 | 0 |
| scripts/ts_strategy_engine/active_learning_calibration.py | 130 | 2 |
| scripts/ts_strategy_engine/active_learning_cli.py | 315 | 9 |
| scripts/ts_strategy_engine/active_learning_common.py | 194 | 11 |
| scripts/ts_strategy_engine/active_learning_domain.py | 291 | 8 |
| scripts/ts_strategy_engine/active_learning_handoff.py | 203 | 7 |
| scripts/ts_strategy_engine/active_learning_label.py | 190 | 2 |
| scripts/ts_strategy_engine/active_learning_path_common.py | 25 | 3 |
| scripts/ts_strategy_engine/active_learning_path_labels.py | 316 | 5 |
| scripts/ts_strategy_engine/active_learning_path_predictions.py | 260 | 2 |
| scripts/ts_strategy_engine/active_learning_path_rerun.py | 92 | 2 |
| scripts/ts_strategy_engine/active_learning_path_selection.py | 182 | 4 |
| scripts/ts_strategy_engine/active_learning_path.py | 149 | 2 |
| scripts/ts_strategy_engine/active_learning_scheduler.py | 15 | 0 |
| scripts/ts_strategy_engine/active_learning_state.py | 131 | 2 |
| scripts/ts_strategy_engine/active_learning_training.py | 299 | 5 |
| scripts/ts_strategy_engine/active_learning.py | 58 | 0 |
| scripts/ts_strategy_engine/cli_commands.py | 240 | 18 |
| scripts/ts_strategy_engine/cli.py | 229 | 7 |
| scripts/ts_strategy_engine/connectivity_evidence.py | 154 | 4 |
| scripts/ts_strategy_engine/contract.py | 276 | 11 |
| scripts/ts_strategy_engine/dimer_analysis.py | 295 | 5 |
| scripts/ts_strategy_engine/dimer_gate_common.py | 42 | 5 |
| scripts/ts_strategy_engine/dimer_gate.py | 302 | 3 |
| scripts/ts_strategy_engine/dimer_path_gate.py | 222 | 2 |
| scripts/ts_strategy_engine/evidence.py | 323 | 7 |
| scripts/ts_strategy_engine/execution_decision.py | 91 | 2 |
| scripts/ts_strategy_engine/execution_evidence.py | 167 | 7 |
| scripts/ts_strategy_engine/execution_gate_cli.py | 55 | 2 |
| scripts/ts_strategy_engine/execution_gate.py | 143 | 3 |
| scripts/ts_strategy_engine/execution_path_rules.py | 326 | 3 |
| scripts/ts_strategy_engine/execution_submission_rules.py | 110 | 3 |
| scripts/ts_strategy_engine/fingerprint.py | 125 | 4 |
| scripts/ts_strategy_engine/handoff.py | 206 | 4 |
| scripts/ts_strategy_engine/learning_cli.py | 119 | 3 |
| scripts/ts_strategy_engine/learning_evidence.py | 102 | 8 |
| scripts/ts_strategy_engine/learning_store.py | 79 | 6 |
| scripts/ts_strategy_engine/matched_static_evidence.py | 150 | 4 |
| scripts/ts_strategy_engine/ml_neb_path.py | 235 | 9 |
| scripts/ts_strategy_engine/path_evidence.py | 110 | 6 |
| scripts/ts_strategy_engine/registry.py | 59 | 5 |
| scripts/ts_strategy_engine/strategy_learning.py | 351 | 17 |
| scripts/ts_strategy_engine/strategy.py | 153 | 3 |
| scripts/ts_strategy_engine/templates.py | 298 | 9 |
| scripts/ts_strategy_engine/workflow.py | 321 | 12 |
| scripts/ts_validation/__init__.py | 1 | 0 |
| scripts/ts_validation/analyze_vfa.py | 463 | 8 |
| scripts/ts_validation/connectivity.py | 751 | 19 |
| scripts/ts_validation/dimer_frequency_gate.py | 83 | 2 |
| scripts/ts_validation/prepare_connectivity.py | 116 | 1 |
| scripts/ts_validation/prepare_vfa_from_ts_image.py | 144 | 2 |
| scripts/ts_validation/validation_pipeline.py | 342 | 7 |
| scripts/vasp_inputs.py | 386 | 8 |
| scripts/vasp_lsf.py | 25 | 1 |
| scripts/vasp_result_gate.py | 89 | 5 |
| scripts/workflow_geometry.py | 49 | 7 |

### modules/

| File | Lines | Function/method definitions |
|---|---:|---:|
| modules/fe_convergence_baseline/validate_baseline.py | 131 | 8 |
| modules/structure_purpose_manager.py | 7 | 0 |
| modules/ts_endpoint_database.py | 7 | 0 |
| modules/ts_endpoint_evidence.py | 7 | 0 |
| modules/ts_endpoint_generator.py | 7 | 0 |
| modules/ts_endpoint_validator.py | 7 | 0 |

### skills/

| File | Lines | Function/method definitions |
|---|---:|---:|
| skills/catalysis-data-retrieval/scripts/hybrid_search.py | 195 | 9 |
| skills/catalysis-data-retrieval/scripts/self_test.py | 65 | 1 |
| skills/catalysis-data-retrieval/scripts/validate_records.py | 111 | 9 |
| skills/fe-vasp-incar-custodian/scripts/incar_custodian.py | 572 | 26 |

### tests/

| File | Lines | Function/method definitions |
|---|---:|---:|
| tests/conftest.py | 15 | 0 |
| tests/test_adsmind_framework_regressions.py | 144 | 5 |
| tests/test_adsmind_lite.py | 523 | 15 |
| tests/test_adsmind_prescreen.py | 153 | 8 |
| tests/test_adsorption_evidence_gate.py | 153 | 10 |
| tests/test_alpha_fe_bulk_submission.py | 181 | 11 |
| tests/test_aqcat25_calibration.py | 70 | 2 |
| tests/test_aqcat25_handoff.py | 263 | 10 |
| tests/test_aqcat25_ml_neb.py | 179 | 5 |
| tests/test_aqcat25_path_active_learning.py | 513 | 12 |
| tests/test_aqcat25_ts_active_learning.py | 793 | 24 |
| tests/test_artifact_io.py | 100 | 7 |
| tests/test_assess_dual_model_ts_vasp_errors.py | 39 | 1 |
| tests/test_catalysis_retrieval.py | 61 | 4 |
| tests/test_code_structure.py | 125 | 7 |
| tests/test_config_boundaries.py | 23 | 2 |
| tests/test_convergence_common.py | 15 | 1 |
| tests/test_dual_model_ml_neb.py | 665 | 27 |
| tests/test_dual_model_ts_force_prediction_batch.py | 106 | 7 |
| tests/test_execution_backends.py | 122 | 7 |
| tests/test_execution_gate_compatibility.py | 84 | 3 |
| tests/test_external_command_boundaries.py | 95 | 9 |
| tests/test_fe110_adsorption_builder.py | 117 | 5 |
| tests/test_fe110_adsorption_preflight.py | 88 | 4 |
| tests/test_fe110_c2_coads_labels.py | 60 | 2 |
| tests/test_fts_prescreen.py | 175 | 10 |
| tests/test_gas_vasp_common.py | 68 | 4 |
| tests/test_incar_custodian_cli.py | 144 | 5 |
| tests/test_matris_energy_force_finetune.py | 184 | 9 |
| tests/test_matris_sella_local_peak.py | 201 | 11 |
| tests/test_matris_sella_smoke.py | 45 | 2 |
| tests/test_matris_training_exclusions.py | 258 | 9 |
| tests/test_matris_ts_path_committee.py | 129 | 6 |
| tests/test_ml_sella_candidate.py | 326 | 18 |
| tests/test_mlip_same_structure_benchmark.py | 57 | 4 |
| tests/test_neb_execution_gate.py | 552 | 22 |
| tests/test_neb_geometry.py | 326 | 15 |
| tests/test_neb_high_force_policy.py | 76 | 5 |
| tests/test_neb_path_quality_control.py | 142 | 6 |
| tests/test_neb_path_quality_entrypoints.py | 600 | 15 |
| tests/test_neb_pilot_validation.py | 90 | 4 |
| tests/test_neb_remote_monitor.py | 83 | 9 |
| tests/test_neb_submission.py | 478 | 24 |
| tests/test_offline_mlip_fusion_feasibility.py | 120 | 4 |
| tests/test_prepare_matris_finetune_request.py | 211 | 6 |
| tests/test_python_package_contract.py | 19 | 1 |
| tests/test_registry_excel_promotion.py | 502 | 14 |
| tests/test_registry_schema.py | 62 | 3 |
| tests/test_registry_write.py | 260 | 9 |
| tests/test_repository_contracts.py | 496 | 23 |
| tests/test_select_dual_model_ts_vasp_labels.py | 61 | 3 |
| tests/test_state_manager.py | 1955 | 46 |
| tests/test_structure_purpose_manager.py | 688 | 24 |
| tests/test_true_fe110_thickness.py | 26 | 2 |
| tests/test_ts_endpoint_contracts.py | 1261 | 57 |
| tests/test_ts_handoff.py | 342 | 7 |
| tests/test_ts_strategy_engine.py | 974 | 35 |
| tests/test_ts_strategy_learning.py | 438 | 35 |
| tests/test_ts_validation_pipeline.py | 225 | 14 |
| tests/test_ts_validation.py | 786 | 17 |
| tests/test_vasp_inputs.py | 157 | 9 |
| tests/test_vasp_output_streaming.py | 104 | 3 |
| tests/test_vasp_result_gate.py | 24 | 1 |

## Appendix 2. Configuration, skill, shell and persistence surfaces

These lists distinguish active configuration/skill artifacts from the historical archive. SQL and scripts received static review; schema checks do not validate all stored production instances.

### Configuration files

- configs/adsmind_lite/adsorbate_rules.yaml
- configs/adsmind_lite/analysis_rules.yaml
- configs/adsmind_lite/backend.yaml
- configs/adsmind_lite/evidence_gate.yaml
- configs/adsmind_lite/iron_fts_prescreen.yaml
- configs/adsmind_lite/prescreen_rules.yaml
- configs/adsmind_lite/site_rules.yaml
- configs/adsmind_lite/surfaces.yaml
- configs/adsorption_result_promotion.yaml
- configs/aqcat25_domain_gate.yaml
- configs/aqcat25_handoff.schema.json
- configs/aqcat25_ts_active_learning.schema.json
- configs/aqcat25_ts_active_learning.yaml
- configs/aqcat25_ts_domain_gate.yaml
- configs/dimer_gate.yaml
- configs/dual_model_ts_active_learning.yaml
- configs/execution_backends.yaml
- configs/fe110_adsorbates_h2_chx_pilot.yaml
- configs/fe110_adsorbates_oxygenated_main_pilot.yaml
- configs/fe110_adsorbates_step12a.yaml
- configs/incar_custodian/project_profiles.yaml
- configs/neb_agent/default_thresholds.yaml
- configs/neb_agent/path_constraints_schema.json
- configs/neb_agent/retrieval_prior_schema.json
- configs/neb_path_quality_control_v2.yaml
- configs/offline_mlip_fusion_feasibility.yaml
- configs/postprocessing_software.yaml
- configs/registry_legacy_writers.yaml
- configs/skill_routing.yaml
- configs/state_handoff.yaml
- configs/state_handoff_event.schema.json
- configs/structure_purpose_routing.yaml
- configs/true_fe110_production.yaml
- configs/ts_connectivity_gate.yaml
- configs/ts_strategy_engine/families.yaml
- configs/ts_strategy_engine/learning.yaml
- configs/ts_validation_pipeline.yaml

### Repository skill files

- skills/README.md
- skills/catalysis-data-retrieval/SKILL.md
- skills/catalysis-data-retrieval/agents/openai.yaml
- skills/catalysis-data-retrieval/references/image_query_schema.json
- skills/catalysis-data-retrieval/references/record_schema.json
- skills/catalysis-data-retrieval/references/sources.yaml
- skills/catalysis-data-retrieval/scripts/hybrid_search.py
- skills/catalysis-data-retrieval/scripts/self_test.py
- skills/catalysis-data-retrieval/scripts/validate_records.py
- skills/chemical-plausibility-gate/SKILL.md
- skills/context_safe_shell.md
- skills/dataset-compatibility-gate/SKILL.md
- skills/dataset-compatibility-gate/agents/openai.yaml
- skills/fe-vasp-incar-custodian/SKILL.md
- skills/fe-vasp-incar-custodian/agents/openai.yaml
- skills/fe-vasp-incar-custodian/references/error_rules.yaml
- skills/fe-vasp-incar-custodian/references/profiles.yaml
- skills/fe-vasp-incar-custodian/references/report_messages.yaml
- skills/fe-vasp-incar-custodian/references/report_template_zh.md
- skills/fe-vasp-incar-custodian/scripts/incar_custodian.py
- skills/fe110-adsorbate-pilot-builder/SKILL.md
- skills/fe110-adsorbate-pilot-builder/agents/openai.yaml
- skills/fe110-adsorbate-pilot-builder/references/iron-fts-prescreen.md
- skills/neb-path-builder/SKILL.md
- skills/surface-adsorption-builder/SKILL.md
- skills/vasp-catalysis-workflow/SKILL.md
- skills/vasp_output_inspection.md

### Non-Python code and SQL

- modules/calculation_registry/migrations/001_ts_endpoint_records.sql
- modules/calculation_registry/migrations/001_ts_endpoint_records_rollback.sql
- modules/calculation_registry/schema.sql
- scripts/aqcat25_gpu_job.sh
- scripts/aqcat25_ml_neb_job.sh
- scripts/aqcat25_mz73_env.sh
- scripts/aqcat25_ts_finetune_job.sh
- scripts/aqcat25_ts_force_prediction_batch_job.sh
- scripts/dual_model_ml_neb_job.sh
- scripts/dual_model_ts_force_prediction_batch_job.sh
- scripts/dual_model_ts_force_prediction_batch_job_v2.sh
- scripts/git_snapshot.ps1
- scripts/matris_finetune_speed_benchmark_job.sh
- scripts/mlip_same_structure_benchmark_job.sh
- scripts/neb_agent/check_neb_job.sh
- scripts/registry_excel_writer.mjs

Additional entry/configuration surfaces: pyproject.toml, .github/workflows/state-manager.yml, .gitignore, .gitattributes, root AGENTS.md, all modules/*/README.md, and the module status/current-state documents.

## Appendix 3. Source-integrity check

The ignore-aware six-core-root inventory was rehashed before writing this report: **846 files, unchanged**. For each lexicographically sorted relative POSIX path, the aggregate hashes path UTF-8 bytes followed by the file's SHA-256 digest bytes. Start/end aggregate SHA-256:

18794d8fab4561028c0d44d134577a494e6ae7cf482f709ad31a6301fd73e78a

This guard covers code/config/tests/skills and module/CI material in that inventory; it is not a hash of all runtime data or the entire dirty working tree. No source changes were made by this audit. No production database, scientific workflow, scheduler, workbook or Git mutation was invoked. The only authored output is refactor_audit/full_coverage_report.md.
