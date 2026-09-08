# Phase 3B Independent Verification Report

Date: 2026-07-27
Final conclusion: **PASS**

## 1. Actual review scope

Production:

- `modules/ts_endpoint_evidence.py`
- `modules/ts_endpoint_validator.py`
- `modules/ts_endpoint_generator.py`
- `modules/structure_purpose_manager.py`
- `modules/ts_endpoint_database.py`

Tests:

- `tests/test_ts_endpoint_contracts.py`
- `tests/test_structure_purpose_manager.py`

Evidence:

- all user-specified Phase 3A/3B reports, API and behavior baselines;
- `TS_ENDPOINT_CURRENT_ARCHITECTURE.md`;
- `PHASE_3B_IMPLEMENTATION_PLAN.md`;
- Phase 3A, Phase 3B, source-baseline, and Review v3 manifests;
- current source AST, imports, signatures, hashes, and executable behavior.

No implementation conclusion was accepted without checking current source or
an independent hash/test result.

## 2. Unique scientific validator

**Confirmed.**

The sole endpoint scientific classification authority is:

```text
modules.ts_endpoint_validator.TSEndpointValidator.validate
```

It alone creates `EndpointValidationStatus`, scientific errors/warnings,
scientific reasons, score, missing/unexpected bond changes, site-coordination
interpretation, and multi-event classification.

Repository scans found:

- evidence defines no status, score, reason, or final branch;
- manager imports no validator and implements no endpoint metric;
- database imports/calls neither validator nor generator;
- generator consumes validator output for eligibility/ranking but creates no
  alternate endpoint scientific status;
- later downhill connectivity and NEB path-quality modules are separate gates,
  not duplicate endpoint-purity evaluators;
- no dynamic import, module string, or hidden local copy of the endpoint
  evaluator.

The generator's pre-existing global-minimum `eligibility_reasons` are
application reuse reasons, not `EndpointValidationResult.reasons`.

## 3. Evidence collector

**Confirmed read-only and bounded.**

It:

- loads the two required structure representations;
- computes raw displacement, COM displacement, and connectivity edges;
- returns deterministic sorted evidence;
- defines no value for any threshold;
- accepts connectivity parameters from the validator policy;
- has no manager, database, routing, CLI, scheduler, or write dependency;
- catches no exception and fabricates no fallback result.

The collector is 102 lines with two functions; its largest function is 64
lines. It is not a general endpoint service.

Its dataclasses are shallowly frozen; contained dictionaries/POSCAR objects are
mutable Python objects. They are internal, not mutated by current code, and no
alias to an input ASE object escapes the collector. This is a low residual
maintainability fact, not a behavior regression.

## 4. Single-read safety

**Confirmed.**

Independent spies established:

- one successful validation loads ASE exactly as `[initial, endpoint]`;
- POSCAR parsing is exactly `[initial, endpoint]`;
- a second validation creates four new objects rather than reusing the first
  call's objects;
- changing the endpoint file between calls changes the result, proving there
  is no stale object cache;
- symbols/order, cell, PBC, constraints, tags, and initial magnetic moments are
  unchanged after evidence collection;
- input POSCAR objects are not mutated;
- collector metric failures propagate unchanged and abort before result
  construction/persistence.

The authorized improvement is specifically initial ASE loads `2 -> 1`.
POSCAR and ASE parsing both remain because their frozen algorithms differ.

## 5. Generator compatibility

**Confirmed.**

The generator SHA-256 exactly matches Phase 3A. Public signatures, dataclasses,
selection order, exception types, assessment order, and no-write behavior are
unchanged. It calls the validator once per candidate and does not independently
compute mapping, connectivity, thresholds, status, or endpoint scientific
reasons.

It remains a historical candidate selector despite the word “generator.” This
pre-existing naming/role mismatch is intentionally frozen.

## 6. Manager compatibility

**Confirmed.**

The manager SHA-256 exactly matches Phase 3A. Tests verify:

- purpose priority is unchanged;
- generator is called once;
- validator is called once per one-candidate test;
- success order is validator then database;
- rejection and validator/collector exceptions prevent persistence;
- database exceptions propagate and no success result is returned;
- unknown, stable, and legacy routes do not touch the endpoint database.

Purpose resolution necessarily occurs before choosing the TS path; “validator
failure does not continue routing” is satisfied as no downstream TS action or
persistence occurs after failure.

## 7. Database-adapter compatibility

**Confirmed.**

The adapter SHA-256 exactly matches Phase 3A. It:

- performs connection, transaction, serialization, insert, duplicate, query,
  and input-integrity work;
- does not import/call validator or generator;
- stores `REJECTED` evidence without re-evaluating it;
- propagates SQLite and JSON serialization errors;
- rolls back insert and serialization failures without a partial row;
- does not expose an update API;
- does not automatically execute migration or alter Schema.

The status-string allow-list is a storage-model invariant, not a scientific
calculation.

## 8. Migration protection

**Confirmed.**

- Forward and rollback SQL hashes match the blocked baseline.
- No endpoint test imports or calls `apply_ts_endpoint_migration`.
- A fail-fast monkeypatch proves ordinary adapter calls do not invoke either
  the runner or SQL-file executor.
- A missing table is not silently created.
- An incompatible existing table raises and remains structurally unchanged.
- All SQLite tests use `tmp_path`.
- Real database SHA-256 before and after all tests:
  `4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb`.

The migration runner remains present but `BLOCKED`, `PROHIBITED`, and
`NEEDS_REVISION`. It was not executed.

## 9. Phase 3A behavior baseline

**Compatible; zero incompatible cases.**

Every recorded status, reason, reason order, field order, exception, routing
decision, and persistence side effect matched. Exact historical floating
goldens were not stored by Phase 3A; current numbers, formula ownership, and
scientific branches are recorded in `PHASE_3B_BEHAVIOR_VERIFICATION.md` and
classified `SEMANTICALLY_EQUIVALENT` where historical numeric equality cannot
be independently replayed.

This corrects the implementation compatibility report's evidence wording, not
the behavior itself.

## 10. Frozen issues

All three are **PRE_EXISTING_CONFIRMED**:

1. sampled 0.2 Å close contact remains `VALID`;
2. sampled opposite-motion/desorption case remains warning-only;
3. empty reaction identity remains accepted.

Their current tests and future ownership are recorded in
`TS_ENDPOINT_FROZEN_ISSUES.md`. None was repaired or changed.

## 11. Public API

**No breaking or behavioral API change found.**

- existing module paths and public imports work;
- parameter order, keyword-only boundaries, defaults, and annotations match;
- all frozen dataclass fields and order match;
- existing monkeypatch/injection paths remain real;
- documented imports still resolve;
- no endpoint CLI, dynamic import, plugin registration, or string module path
  was found.

The evidence module is additive and does not replace an existing public path.

## 12. Scientific behavior and configuration

**No change found.**

- statuses and status priority: unchanged;
- reason codes and ordering: unchanged;
- threshold values and override order: unchanged;
- mapping, break/form, coordination, and site interpretation: unchanged;
- generator selection priority: unchanged;
- purpose configuration and connectivity-gate configuration hashes: unchanged;
- no JSON/SQLite Schema or record-field change.

Phase 2B path-quality files and the unified workflow retain their Review v3
hashes. Execution gate, scheduler evidence, and submission files retain their
acceptance-start hashes.

## 13. Complexity and benefit

| Metric | Phase 3A | Phase 3B | Verified result |
|---|---:|---:|---|
| Initial ASE loads/successful validation | 2 | 1 | reduced |
| Connectivity calculations/validation | 2 | 2 | unchanged, one per structure |
| Scientific validators | 1 | 1 | unique |
| Manager scientific evaluators | 0 | 0 | unchanged |
| Database scientific evaluators | 0 | 0 | unchanged |
| Validator lines | 479 | 452 | -27 |
| Largest endpoint module | 479 | 452 | -27 |
| Largest function | 137 | 138 | +1 |
| Endpoint production lines | 1116 | 1191 | +75 |
| Dependency edges | 3 | 4 | one acyclic collector edge |
| Cycles | 0 | 0 | unchanged |

The production increase is one 102-line evidence module minus 27 validator
lines. Implementation reports/snapshots comprise 773 lines; tests and
verification tests account for the other substantial growth. The evidence
boundary reduces repeated initial loading and isolates raw measurements
without creating a second evaluator. The benefit is real but deliberately
narrow.

## 14. Validation results

Executed locally without migration or real services:

```text
python -m pytest -q -ra tests/test_ts_endpoint_contracts.py \
  tests/test_structure_purpose_manager.py
41 passed

python -m pytest --collect-only -q
270 tests across 37 files

python -m pytest -q -ra
270/270 passed; exit code 0

python -m ruff check scripts modules tests
passed

git diff --check
exit code 0; only unrelated pre-existing LF/CRLF notices
```

Static results:

- skip/xfail markers: 0;
- endpoint dependency cycles: 0;
- duplicate top-level endpoint definitions: 0;
- broad/bare endpoint exception handlers: 0;
- real SSH/LSF/`bsub`/VASP/NEB operations: 0;
- migration executions: 0;
- real database writes: 0.

## 15. Verification changes

No production defect was found and no production source was modified.

Five necessary tests were added to
`tests/test_ts_endpoint_contracts.py` for:

1. read count, fresh object identity, metadata preservation, and no stale
   cache;
2. collector metric exception propagation and no persistence;
3. database exception propagation through manager;
4. JSON serialization rollback;
5. blocked migration and incompatible-table non-replacement.

`PHASE_3B_CHANGESET_MANIFEST.md` and historical baselines were not edited.
The additive verification changeset records the new test hash.

## 16. Remaining risks

- The three frozen scientific/input issues remain real.
- Exact pre-refactor floating values cannot be independently rerun because
  Phase 3A retained hashes and qualitative/contract snapshots, not an
  executable validator copy or full numeric golden file.
- Endpoint source files remain untracked in the current Git worktree; hashes,
  rather than Git history, are the present provenance mechanism.
- The blocked migration runner still shares the adapter module pending its
  separately governed revision.

None is a Phase 3B regression or a condition blocking closure of this
responsibility-only phase.

## 17. Final conclusion

**PASS**

The validator remains the unique scientific authority; the evidence collector
is read-only and bounded; single-read behavior is safe; public API and Phase 3A
behavior are compatible; migration remains blocked; and all 270 tests pass.

Phase 3B may end and a separately authorized final project-wide closure may
begin. That closure was not started.
