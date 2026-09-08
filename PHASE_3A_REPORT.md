# Phase 3A Report

Date: 2026-07-27
Conclusion: **PASS WITH CONDITIONS**

## Outcome

The post-Phase-2B additive Review Baseline v3, endpoint public API contract,
current architecture, behavior baseline, focused contract tests, and a minimal
Phase 3B plan are complete. No endpoint production module, scientific
configuration, SQL migration, governance rule, execution gate, NEB
path-quality module, or real database was modified.

Phase 3B must not start automatically. It may begin only with explicit
authorization and the scope/conditions in `PHASE_3B_IMPLEMENTATION_PLAN.md`.

## Deliverables

- `REVIEW_BASELINE_V3.md`
- `artifacts/review_baseline_v3/parent_v2_sha256.txt`
- `artifacts/review_baseline_v3/phase_2b_verified_source_manifest.txt`
- `artifacts/review_baseline_v3/phase_2b_verified_test_manifest.txt`
- `artifacts/review_baseline_v3/phase_2b_verified_document_manifest.txt`
- `artifacts/review_baseline_v3/baseline_v3_sha256.txt`
- `TS_ENDPOINT_API_CONTRACT.md`
- `TS_ENDPOINT_CURRENT_ARCHITECTURE.md`
- `TS_ENDPOINT_BEHAVIOR_BASELINE.md`
- `PHASE_3B_IMPLEMENTATION_PLAN.md`
- `PHASE_3A_CHANGESET_MANIFEST.md`
- `tests/test_ts_endpoint_contracts.py`

`tests/test_repository_contracts.py` was minimally extended to admit exactly
the five requested v3 artifact files and verify all five v3 SHA-256 bindings.
Its Review Baseline v2 hash
`f3b7b2a78e1f0bc84a5d46b9982ee94334018f277b253c908428657ece286398`
is retained as historical; the Phase 3A after-hash is recorded in the additive
Phase 3A changeset rather than written back into v2.

## Baseline result

- v3 directly binds Review Baseline v2.
- It records all five Phase 2B verified production sources and three verified
  tests.
- It explicitly records the authorized `pilot_validation.py` hash.
- It binds the Phase 2B verification reports and verified changeset.
- Calculation, runtime, scheduler, database, migration, and output files are
  excluded.
- v1, v2, Phase 2A, and Phase 2B historical baseline files were not edited.
- Phase 3A audit/test/report additions are bound separately by
  `PHASE_3A_CHANGESET_MANIFEST.md`; they are not retroactively admitted into
  the post-Phase-2B starting baseline.

## Endpoint architecture result

- Internal dependency graph: 3 edges, 0 cycles.
- Sole endpoint scientific evaluator: `TSEndpointValidator`.
- Generator: existing-candidate validation/reuse/ranking, not geometry
  generation.
- Manager: routing and application orchestration; successful TS route persists
  only after validation/selection.
- Database adapter: storage only for ordinary calls; it contains a separate
  blocked migration runner but no scientific validation.
- No CLI, production workflow, dynamic import, plugin, or string module caller
  currently connects the manager.

## Behavior freeze result

The new 17-test contract file freezes:

1. public signatures and output field order;
2. generator break/form results and deterministic ranking;
3. atom order/mapping and candidate/site pass-through;
4. validator status, reason and list order;
5. invalid input and file exception boundaries;
6. purpose priority and route behavior;
7. validator-before-database call order;
8. no persistence after validation failure;
9. temporary-database save/get/duplicate/query/rollback behavior;
10. absence of scientific imports/calls in the database adapter.

The tests do not execute either blocked migration. Temporary database tests
create a minimal test-only table directly.

## Findings

### P0 — scientific acceptance risk, not authorized for repair

1. `modules/ts_endpoint_validator.py`: a sampled 0.2 Å C–O contact is interpreted
   as the requested bond being absent and returns `VALID` without a collision
   reason.
2. The same module: sampled large opposite-direction adsorbate movements can
   cancel in the mass-weighted COM vector; the result was
   `VALID_WITH_WARNING`, without a dedicated desorption reason.

Benefit of correction: prevent scientifically invalid endpoint acceptance.
Risk: changes scientific outcomes, statuses, and reasons.
Required tests: element-aware contact cases, surface-distance/desorption cases,
periodic-boundary cases, multi-adsorbate COM counterexamples, independent
scientific review.
Immediate action: prohibit using this validator alone as automatic scientific
acceptance; create a separately authorized scientific-correction task. Do not
hide the change inside Phase 3B.

### P1 — responsibility/maintenance risk

1. Validator combines file/config loading, repeated parsing, metric
   calculation, classification, and result formatting.
2. Initial structures are parsed through multiple representations per
   candidate; multi-candidate generation reloads common input/config.
3. Database module combines ordinary adapter code with a blocked migration
   runner.
4. Routing and scientific thresholds share one YAML file.
5. Empty reaction identity strings are accepted and passed through.

Immediate Phase 3B recommendation: address only validator evidence collection
versus evaluation. Defer database/config separation and identity validation.

### P2 — low-value structure issues

- `TSEndpointGenerator` is named as a generator but currently selects existing
  candidates.
- Status values are duplicated in the validator Enum, adapter validation set,
  and SQL CHECK.

Immediate action: none; renaming or centralization has more compatibility risk
than present benefit.

### Not recommended

- rewriting generator, manager, and database together;
- changing route/status/reason priority;
- integrating the blocked migration;
- adding a CLI or real workflow connection;
- merging later connectivity validation into endpoint purity validation.

## Validation

Executed without migration or real database access:

```text
python -m py_compile modules/ts_endpoint_generator.py \
  modules/ts_endpoint_validator.py \
  modules/structure_purpose_manager.py \
  modules/ts_endpoint_database.py \
  tests/test_ts_endpoint_contracts.py
# passed

python -m ruff check scripts modules tests
# passed

python -m pytest -q -ra tests/test_ts_endpoint_contracts.py \
  [three Review Baseline v3 contract node IDs] \
  [six explicit safe test_structure_purpose_manager node IDs]
# 26 passed

python -m pytest -q -ra --ignore=tests/test_structure_purpose_manager.py
# 246 passed

python -m pytest --collect-only -q
# 262 collected

git diff --check
# exit 0; only task-external existing LF/CRLF warnings
```

The complete 262-test suite was deliberately not run because the unchanged
historical `tests/test_structure_purpose_manager.py` contains tests that call
the prohibited forward and rollback migrations. This is an explicit scope
constraint, not a test failure.

Additional integrity checks:

- Review Baseline v3: 5/5 top-level bindings matched;
- four v3 manifests: 19/19 path/byte/hash rows matched current files;
- four endpoint production modules plus two configurations: 6/6 entry hashes
  remained equal to the Phase 3A starting hashes;
- static skip/xfail marker scan: 0;
- endpoint internal cycles and duplicate top-level definitions: 0.

## Conditions

1. Do not start Phase 3B without explicit approval.
2. Phase 3B must preserve the frozen scientific behavior and exclude the
   blocked migration/database/configuration scope.
3. The two P0 findings require a separate scientifically authorized correction
   and cannot be silently bundled with responsibility refactoring.
4. A future complete-suite claim requires either explicit permission to execute
   the blocked migration tests in temporary SQLite or replacement of those
   historical tests with non-migration fixtures under separate authorization.
