# AC-B2-001 Scientific Claim Authority Repair

Scope: targeted AC-B2-001 repair only. No new refactor phase, merge, production
operation or independent acceptance rerun is part of this task.

Repair status: targeted reproductions closed; required local regression and
release checks pass. Whole-repository independent acceptance is not reassessed.

## Baseline and historical evidence

- Repository: `q2214299493/sbq123`.
- Original failed independent audit / repair base:
  `fad1d32607723c851c457a5fb6fa85898cdc1edf`, branch
  `codex/b1-b7-final-acceptance`.
- Repair branch: `codex/ac-b2-001-scientific-claim-authority`.
- Work was isolated in `C:/Users/86177/AppData/Local/Temp/sbq123-ac-b2-001`.
  No unrelated work in the dirty development checkout was modified.
- `B1_B7_acceptance_report.md` and `B1_B7_acceptance.json` retain their original
  content and failed historical verdict. This report does not replace them.

## Defect and root cause

The old `validated_ts` summary predicate accepted boolean assertions. The gate
could issue `VALIDATED_TS`, `APPROVE_TS_CANDIDATE` and `REPORT_FINAL_BARRIER`
without underlying scientific evidence. `require_action` recomputed the saved
summary decision, but scientific claim actions did not traverse current source
verification. Changing a bound validation summary therefore did not revoke an
old claim. Self-consistent hashes proved identity, not scientific validity.

## Authority and ownership after repair

`SCIENTIFIC_CLAIM_ACTIONS` explicitly contains TS approval and final barrier
reporting. It is separate from the unchanged execution action category and
`user_execution_authorization`. A valid scientific claim grants no submission,
continuation, stop, VASP or GPU authority.

The small `scientific_claims.py` application boundary reuses
`source_bindings_valid` for the validation file's existence, current hash and
content equality. It dispatches to maintained scientific owners and rechecks the
summary binding after verification. Missing, stale or invalid evidence produces
`NEEDS_CURRENT_TS_VALIDATION_EVIDENCE`, with a specific
`CURRENT_TS_VALIDATION_EVIDENCE_*` reason and no claim permission.

`execution_gate.py` remains the unchanged public authoritative boundary (150
lines). Both creation and `require_action` validation run the same current claim
path through decision recomputation. A stale saved decision fails validation;
its own `state_sha256` cannot substitute for current scientific files.

Scientific owners remain:

- **DIMER/VFA:** `evaluate_validation_pipeline`, delegating to the existing
  `validate_dimer_vfa_binding`, `analyze_dimer`, `analyze_vfa` and frequency gate.
  Same analysis, final saddle, VFA workdir, contract, atom map, compatibility,
  current sources, scope/mode/geometry reviews and applicable soft review remain
  required. Optional A/B/C classification does not become a new DIMER acceptance
  requirement; frequency-only soft approval cannot finalize a TS. No new
  connectivity requirement is introduced for DIMER.
- **NEB/CI-NEB VFA:** current binding is applied in `analyze_vfa.py`, replaying
  the existing NEB parser, geometry/path review, contract binding, VFA analyzer
  and bidirectional connectivity owner. Replay and transitive manifests retain
  current raw outputs, structures, endpoints, contract source, policy and review
  evidence. Explicit nondefault path-review locations remain supported.
- **Geometry/scope helpers:** existing `same_vfa_geometry` and `vfa_scope_checks`
  moved unchanged into the scientific VFA owner. Original preparation-module
  imports are direct re-exports. Their function ASTs are identical to baseline.
  This removes the preparation -> gate -> scientific-validation import cycle;
  it does not create another validator or executor.
- **Barriers:** the gate alone lacks current database-backed final energies, so
  it never grants `REPORT_FINAL_BARRIER` from boolean metadata. The existing
  `record_matched_static_barrier` consumes a current TS-approval gate and the
  exact bound `barrier_claim` request, then performs its existing accepted-TS,
  result/file/job/scientific-status, compatibility, convention, finite-energy,
  nonnegative-barrier and transactional template checks. It also matches the
  current TS evidence's object/contract fields to the registered validation.
  No SQL or barrier arithmetic was moved into the gate.

`record_ts_validation` still calls `require_action` before insertion and retains
all its additional payload, file, source-saddle/job, applicable connectivity and
persistence checks. Those remain a separate trust boundary.

## Caller characterization and compatibility

All references to `validated_ts`, `decide_execution`, `build_decision`,
`require_action`, both claim action names and both registration APIs were
searched across maintained source, CLI/skill adapters, tests and docs before
changing their contract. The maintained claim artifact is the full
`analyze_vfa` output for DIMER, NEB or CI-NEB, including current review/workdir,
normalized reaction contract and scientific source bindings. An optional
`barrier_claim` is retained as request metadata, never scientific proof.

The separate `ts_validation_pipeline_status` output remains a stage/status
artifact, not an arbitrary Grade-A dictionary accepted by the gate. Its existing
scientific evaluator is reused for DIMER claim verification. Generic hand-written
or legacy unbound summaries are not a compatibility fallback: they need current
reanalysis and the existing hash-bound review procedure. No historical artifact
was silently refreshed in this task.

Existing gate and registration API signatures remain. `decide_search` gains an
optional keyword-only `source_bindings` argument, and `analyze_search` supplies
the actual validation file binding. NEB/geometry/connectivity analyzers keep
their default write behavior and add `write_output=False` for read-only replay.
New replay/source metadata requires reanalysis of older artifacts that lack the
current source chain; it does not require rerunning a scientific calculation.

The legacy `validated_ts` function remains a summary-only compatibility predicate;
production claim application no longer consumes it as authority.

## Before/after reproductions and positive cases

| Case | Before | Repaired behavior / evidence |
| --- | --- | --- |
| Audit's bare Grade-A/DIMER/barrier booleans | VALIDATED_TS and both claim actions | Real Python gate and CLI producer return a nonaccepted evidence state; both actions rejected |
| Bound validation summary changed to Grade C or removed | Saved gate retained claim permission | Existing gate rejected at `require_action` for both claim actions |
| Summary byte-identical, underlying source changed | Summary alone was sufficient | Rejected for VFA OUTCAR/POSCAR/handoff/scope/mode review; DIMER INCAR/OUTCAR/CONTCAR/MODECAR/analysis/handoff/final-mode review |
| DIMER A with VFA B | Risk of summary-only acceptance | Existing B2.1 cross-object protections run through the claim path and reject |
| Current fully bound DIMER/VFA | Legitimate scientific workflow | TS approval works with no execution authorization or connectivity, while all execution/report-only actions stay denied |
| Current NEB/CI-NEB and connectivity | Legitimate scientific workflow | Both methods pass actual scientific owners; changed branch OUTCAR, NEB source, contract or path review revokes the claim |
| TS persistence | Summary gate could reach insertion boundary | Positive current registration works; stale gate fails before new TS insertion |
| Final matched-static barrier | Gate boolean claimed reportability | Existing owner successfully records valid negative total energies/finite nonnegative barriers; stale TS evidence prevents barrier/template insertion |

New tests exercise `build_decision`, `decide_execution`, `require_action`,
`record_ts_validation` and `record_matched_static_barrier` through their actual
maintained paths. No scientific verifier is mocked. Synthetic structures,
outputs, reviews and temporary SQLite databases are used. The old registry
fixture's hand-written acceptance summaries were replaced with real NEB/VFA/
connectivity analysis fixtures; its existing registration, rollback, finite-value,
status and template assertions remain.

## Exact changed files

1. `scripts/ts_strategy_engine/scientific_claims.py`
2. `scripts/ts_strategy_engine/execution_path_rules.py`
3. `scripts/ts_strategy_engine/execution_evidence.py` (summary-only docstring)
4. `scripts/ts_strategy_engine/evidence.py`
5. `scripts/ts_strategy_engine/strategy.py`
6. `scripts/ts_strategy_engine/workflow.py`
7. `scripts/ts_validation/analyze_vfa.py`
8. `scripts/ts_validation/connectivity.py`
9. `scripts/ts_validation/prepare_vfa_from_ts_image.py`
10. `scripts/neb_agent/analyze_neb_outputs.py`
11. `scripts/neb_agent/diagnose_path_geometry.py`
12. `tests/scientific_claim_fixtures.py`
13. `tests/test_scientific_claim_authority.py`
14. `tests/test_ts_strategy_engine.py`
15. `reports/capability_readiness.json`
16. `reports/refactor_audit/AC_B2_001_repair_report.md`
17. `modules/ts_vibrational_validation/README.md` (ownership reference only)

The existing derived readiness JSON was regenerated with its original owner
because B6 tests require the view to match current sources. Only the two hashes
for `workflow.py` and `test_ts_strategy_engine.py` changed. Module states,
scientific validation, production readiness and every other field are unchanged.
The corresponding Markdown view is byte-unchanged. This is the only new repair
report; the independent failed audit remains untouched.

## Validation results

Environment: local Windows 11 / Python 3.13.9. All scientific test data are
synthetic and local. Commands were executed in the isolated repair worktree.

| Check | Final result |
| --- | --- |
| `python -m ruff check scripts modules tests` | Exit 0; All checks passed! |
| `python -m pytest -o addopts= -q` | Exit 0; **1128 passed in 325.60s (0:05:25)** |
| New AC tests plus explicit dependency-graph and readiness determinism checks | Exit 0; **33 passed in 20.67s** (31 new AC regressions plus two existing gates) |
| Existing TS registration / B2.1 regression run | Exit 0; **79 passed in 53.61s** |
| Existing B1-B7 critical regression group | Exit 0; **495 passed in 82.97s (0:01:22)** |
| Actual wheel / clean environments | Exit 0; PASS, editable/wheel parity true |

The final count increases from the base's 1097 tests by the 31 new AC regressions.
Existing test cases were not removed. The final source passed the full suite;
afterward only the module ownership reference was updated, with B6 included
again in the final critical regression group.

Exact focused command:

```text
python -m pytest -o addopts= -q tests/test_scientific_claim_authority.py tests/test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic tests/test_b6_governance.py::test_readiness_generation_is_deterministic_and_matches_checked_in_view
```

Exact existing critical group:

```text
python -m pytest -o addopts= -q tests/test_b7_release.py tests/test_execution_lifecycle.py tests/test_b2_scientific_contract.py tests/test_b21_scientific_acceptance.py tests/test_b3_evidence_governance.py tests/test_b3_ml_governance.py tests/test_b4_registry_governance.py tests/test_b4_state_governance.py tests/test_registry_write.py tests/test_registry_schema.py tests/test_state_manager.py tests/test_b5_architecture_boundaries.py tests/test_b6_governance.py tests/test_code_structure.py tests/test_repository_contracts.py tests/test_artifact_io.py
```

Exact final release command:

```text
python -m scripts.validate_release --source . --output C:/Users/86177/AppData/Local/Temp/ac-b2-001-release-final
```

The reviewed validator exported indexed source, built the actual wheel, installed
it in a fresh environment, and ran probes outside the repository. Its separate
editable installation matched the wheel's CLI, resources and smoke results.
Repository-only operations failed explicitly without context. All 60 runtime
resources, including registry SQL and retrieval schemas, were present.

- Wheel: `sbq_catalyst_agent_workflow-0.1.0-py3-none-any.whl`.
- SHA-256: `d20515361fe74aa650a0d22cfae961258dd790a885ad4559cb54b59b2325e8c9`.
- Members: 286; excluded-artifact findings: none.
- Local smoke: PASS, schema 9, two temporary calculation/file rows,
  idempotent replay, `scientific_acceptance=false`, `external_actions=0`.
- Canonical release evidence is outside source at
  `C:/Users/86177/AppData/Local/Temp/ac-b2-001-release-final/release_environment.json`.
- No packaging policy/resource redesign was needed. The final wheel validates
  the repaired Python source; the subsequent README ownership-reference edit
  changes no packaged code or runtime resource.

The first development full run exposed an import cycle, derived-view hash drift
and an outdated delegation assertion while ownership was being corrected. Those
results are not treated as final acceptance. The cycle was fixed by ownership,
the derived view by its generator, and the assertion now checks the actual
scientific owners. No architecture limit or scientific assertion was weakened.

## Scientific policy and external actions

No ENCUT, KPOINTS, ISMEAR, SIGMA, EDIFF, EDIFFG, MAGMOM, fixed atoms, frequency
thresholds, DIMER hard/soft criteria, NEB thresholds, reaction families, energy
conventions or TS grading rules were changed. Negative DFT total energies remain
valid; finite-number and nonnegative-barrier requirements remain enforced.

`execution_gate.py`, `submission.py` and `artifact_io.py` are unchanged. B1
execution authorization/source binding, POTCAR checks, paths, reservation,
unknown-submission reconciliation and upload integrity retain their behavior.
No schema, migration, production database, calculation output, model weight,
production workbook or historical scientific evidence was changed.

**external_scientific_actions = 0.** No real SSH, scheduler query/submission/stop,
VASP, GPU model, training, production DB or workbook action occurred. Git/pip
networking for the explicitly requested source publication and wheel validation
does not constitute an external scientific action.

## Operational limitations and disposition

The read-only candidate startup audit returned exit 1: one pre-existing managed
projection drift in `docs/06_MODULE_MAP.md#module_row:transition_state_search`,
plus two isolated-worktree ownership warnings. Unrelated live
`STATE_RECONCILIATION_REQUIRED` task conflicts were not re-queried or resolved.
No state events/proposals were changed, and managed synchronization was not used
to modify unrelated projections during this targeted repair.

Production deployment, live credentials/environments, scheduler state, scientific
performance and historical-artifact reanalysis remain unverified. This local
repair does not establish whole-repository merge readiness or production
readiness; the original failed independent acceptance verdict remains historical.
A fresh independent acceptance task is separate and was not run here.

Publication is limited to the repair branch on `q2214299493/sbq123`; no merge,
main update or subsequent phase is performed. Stop after publishing this repair.
