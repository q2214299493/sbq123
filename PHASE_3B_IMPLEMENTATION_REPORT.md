# Phase 3B Implementation Report

Date: 2026-07-27
Conclusion: **PASS**

## 1. Authority and scope

`PHASE_3B_IMPLEMENTATION_PLAN.md` was applied as the highest scope authority.
The production change is limited to extracting non-judgmental endpoint
evidence collection from the existing validator. The plan explicitly excludes
a generator/manager/database rewrite, so those three production modules remain
byte-identical to the Phase 3A hashes.

The requested four responsibilities remain represented by the existing
generator/selector, scientific validator, purpose manager, and database
adapter. `ts_endpoint_evidence` is an internal helper inside the validator
layer, not a fifth workflow authority.

## 2. Actual modified files

### Production

- `modules/ts_endpoint_evidence.py` — added immutable raw structure/evidence
  containers and read-only displacement/connectivity collection.
- `modules/ts_endpoint_validator.py` — delegates raw loading/measurement to the
  collector; retains every scientific status, threshold, reason, score, and
  result-construction branch.

### Tests

- `tests/test_ts_endpoint_contracts.py` — added three tests for raw-only
  evidence, one ASE load per structure, direct/manager result equivalence,
  exact generator/validator call counts, exception propagation, and no
  persistence after validator exception.
- `tests/test_structure_purpose_manager.py` — changed its temporary database
  fixture to create the minimal test-only Schema directly and replaced a test
  that executed the blocked migration with a test proving the adapter does not
  implicitly migrate. This permits complete regression testing while complying
  with the express prohibition on executing either endpoint migration. No
  adapter assertion was weakened: CRUD, duplicate, rollback, rejection, and
  idempotence behavior remain covered in the contract suite.

### Reports and phase evidence

- `TS_ENDPOINT_DUPLICATION_AUDIT.md` — supplied the missing prerequisite
  document and limited the authorized duplicate removal to raw evidence
  collection.
- `PHASE_3B_PRECHANGE_SNAPSHOT.md`
- `TS_ENDPOINT_REFACTORED_ARCHITECTURE.md`
- `PHASE_3B_BEHAVIOR_COMPATIBILITY.md`
- `PHASE_3B_CHANGESET_MANIFEST.md`
- this report.

## 3. New responsibility boundary

### Generator

`modules.ts_endpoint_generator` remains byte-identical. It accepts generation
requests and candidates, delegates scientific classification to the validator,
applies the frozen candidate reuse/selection ordering, and returns the
historical result dataclasses. It does not calculate connectivity or
displacement, load thresholds, write files, or persist records.

Its existing validator delegation is retained as a public compatibility facade
because relocating it would change the frozen `generate()` behavior and is
explicitly excluded by the implementation plan. It does not constitute a
second scientific evaluator.

### Validator

The only scientific authority remains:

```text
modules.ts_endpoint_validator.TSEndpointValidator.validate
```

It alone constructs the four scientific statuses, errors, warnings, reasons,
scores, migration flag, expected/observed/missing/unexpected bond changes, and
site-coordination interpretation.

### Manager

`modules.structure_purpose_manager` remains byte-identical. It resolves purpose,
delegates candidate selection/validation, calls persistence only after success,
and returns the existing workflow result. It contains no endpoint geometry or
scientific validation implementation.

### Database adapter

`modules.ts_endpoint_database` remains byte-identical. It performs record
integrity checks, transactions, serialization, duplicate handling, queries,
and rollback. It imports/calls neither generator nor validator and does not
read structures or execute migration.

### Evidence collector

`modules.ts_endpoint_evidence` performs read-only input loading and raw
measurement. It owns no status, reason, score, threshold definition, routing,
or persistence. Errors from POSCAR/ASE/file access propagate unchanged.

## 4. Removed or consolidated duplication

- Initial ASE structure loading during a successful validation: `2 -> 1`.
- Raw per-atom displacement, mass-weighted COM displacement, and initial/final
  connectivity collection now have one internal implementation.
- Validator-private COM and connectivity-loading helpers were removed after
  exact delegation.

No `INTENTIONAL_LAYERING` or `NEEDS_REVIEW` item from the duplication audit was
changed. Public wrappers were retained.

## 5. Public API and behavior compatibility

- Existing module paths and public names: unchanged.
- Constructor and method signatures, parameter order, keyword names, and
  defaults: unchanged.
- Return dataclasses, fields, ordering, and `as_dict()` behavior: unchanged.
- Exception types for invalid roles, missing inputs, invalid POSCAR, rejected
  candidates, and database errors: unchanged.
- Generator selection order, purpose routing priority, and persistence timing:
  unchanged.
- Test monkeypatch targets on existing public entries: unchanged.

The two new evidence dataclasses/functions are additive internal interfaces.

## 6. Scientific, configuration, and Schema compatibility

No scientific rule was changed:

- no threshold or override-order change;
- no atom-mapping or element-order change;
- no bond-formation/bond-breaking rule change;
- no site, coordination, close-contact, desorption, or non-target-bond rule
  change;
- no status, reason code, reason order, score, or priority change.

The known frozen close-contact, sampled desorption, and empty-identity gaps
remain present and are explicitly regression-tested.

Both endpoint YAML files are hash-identical. No JSON Schema, data model,
database Schema, schema version, SQL, migration runner, governance rule,
execution gate, NEB path-quality, scheduler, or submission file was modified.

## 7. Database and migration protection

- Real database before SHA-256:
  `4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb`.
- Real database after SHA-256: the same value.
- Forward blocked migration SHA-256:
  `cbbedb50005d1bc57a821d5e983e2578c2d8e43c8f0cfe774f710af91ce1093f`.
- Rollback blocked migration SHA-256:
  `6fdd989767a58aea76987cdbff4b0fa77182f1d4fd8cb2477ae10dacaa4808d5`.

Neither migration was read by a test runner or executed. All endpoint database
tests used pytest temporary directories. No real database was opened through
SQLite during this phase.

## 8. Complexity comparison

| Metric | Before | After | Result |
|---|---:|---:|---|
| Scientific validator implementations | 1 | 1 | unique authority preserved |
| Generator orchestration implementations | 1 | 1 | unchanged |
| Validation orchestration implementations | 1 | 1 | unchanged |
| Purpose-rule implementations | 1 | 1 | unchanged |
| Persistence-field constructors | 1 | 1 | unchanged |
| Initial ASE loads per successful validation | 2 | 1 | duplicate removed |
| Validator lines | 479 | 452 | -27 |
| Largest endpoint module | 479 | 452 | -27 |
| Largest function | 137 | 138 | +1 |
| Endpoint production lines | 1116 | 1191 | +75 |
| Endpoint production bytes | 42085 | 44141 | +2056 |
| Endpoint production modules | 4 | 5 | +1 internal collector |
| Endpoint-module dependency edges | 3 | 4 | one validator-to-collector edge |
| Circular dependencies | 0 | 0 | unchanged |
| Duplicate top-level definitions | 0 | 0 | unchanged |

Total production LOC increased because a named, typed evidence boundary was
added. The complexity benefit is narrower responsibility, removal of repeated
I/O/raw collection, and a 27-line reduction in the scientific authority
module—not a claim of total LOC reduction. No general service or catch-all
manager was introduced.

## 9. Verification

Executed:

```text
python -m pytest -q -ra <23-test prechange endpoint selection>
    23 passed

python -m pytest -q -ra tests/test_ts_endpoint_contracts.py
    20 passed

python -m pytest -q -ra tests/test_ts_endpoint_contracts.py \
    tests/test_structure_purpose_manager.py
    36 passed

python -m pytest --collect-only -q
    265 tests across 37 files

python -m pytest -q -ra
    265/265 passed; exit code 0

python -m ruff check scripts modules tests
    passed

git diff --check
    exit code 0; only pre-existing LF/CRLF notices
```

Static inspection found:

- dependency graph acyclic;
- no duplicate top-level definitions in the five endpoint modules;
- evidence collector has no status/reason/database/manager dependency;
- validator has no database/manager dependency;
- database adapter has no validator/generator dependency;
- repository test scan contains no skip/xfail marker.

## 10. Actual fixes made during implementation

1. Extracted repeated raw evidence loading/measurement from the validator.
2. Added regression coverage for raw-only evidence and one-load behavior.
3. Added exact direct/manager equivalence and single-call protection.
4. Added validator-exception/no-persistence protection.
5. Removed blocked migration execution from the historical endpoint test and
   replaced it with an adapter-boundary assertion.
6. Added the missing `pytest` import detected by targeted Ruff after that test
   change.

No production behavior was changed to satisfy a test.

## 11. Remaining risks

- The known close-contact sample still returns `VALID`.
- The sampled opposite-motion/desorption case still lacks a desorption reason.
- Empty reaction identity fields remain accepted.
- The historical generator name covers candidate assessment/selection as well
  as candidate handling. Changing that public layering would be higher risk and
  is explicitly deferred by the implementation plan.
- Blocked endpoint migrations still need the separate revision process in
  `MIGRATION_REVISION_BACKLOG.md`.

These are pre-existing, frozen findings rather than Phase 3B regressions.

## 12. Not implemented

- no generator, manager, or database-adapter rewrite;
- no `ts_endpoint_service.py`;
- no public rename or deprecation;
- no scientific correction;
- no configuration or Schema change;
- no migration modification or execution;
- no real workflow/calculation/database integration;
- no git staging, commit, or push;
- no Phase 3B independent acceptance or project-wide final cleanup.

## 13. Final conclusion

**PASS**

The validator remains the single scientific authority; the new collector is
raw-only; generator, manager, and database adapter contain no duplicate
scientific evaluator; all frozen behaviors and public interfaces are
compatible; configuration, migration, baseline, and real database hashes are
unchanged; and all 265 tests pass with zero skip/xfail.

Phase 3B implementation is complete and may proceed to a separate independent
acceptance task. That acceptance has not been started.
