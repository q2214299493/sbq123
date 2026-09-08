# Phase 3B Independent Diff Review

Date: 2026-07-27
Review scope: implemented TS endpoint responsibility extraction only

## Evidence boundary

All four Phase 3A endpoint production files are untracked in the current Git
repository. Consequently, `git diff` cannot reconstruct a Phase 3A-to-3B
line-by-line patch for them. This review independently used:

- Phase 3A and prechange file SHA-256 values;
- the current file bytes and AST;
- `TS_ENDPOINT_CURRENT_ARCHITECTURE.md` and
  `TS_ENDPOINT_DUPLICATION_AUDIT.md` for the recorded prechange structure;
- the implementation changeset only as a claim to verify, not as authority;
- current public signatures and executable behavior.

This is sufficient to prove byte identity for unchanged files and to identify
the current production boundary. It is not equivalent to possessing a stored
copy of the old validator source.

## Changeset hash verification

Before any independent-verification test was added, all seven implementation
entries matched `PHASE_3B_CHANGESET_MANIFEST.md`:

| Path | Manifest SHA-256 | Independently calculated | Result |
|---|---|---|---|
| `modules/ts_endpoint_evidence.py` | `51822d18...bdabf2` | same | MATCH |
| `modules/ts_endpoint_validator.py` | `04e0a33d...c50fa5` | same | MATCH |
| `modules/ts_endpoint_generator.py` | `db07eea4...dc1da` | same | MATCH |
| `modules/structure_purpose_manager.py` | `f68fbb78...749b5` | same | MATCH |
| `modules/ts_endpoint_database.py` | `8145e739...8a702` | same | MATCH |
| `tests/test_ts_endpoint_contracts.py` | `998e85ce...f9997` | same | MATCH |
| `tests/test_structure_purpose_manager.py` | `14fe6e6e...156e` | same | MATCH |

The independent review subsequently added five permitted regression tests.
Only `tests/test_ts_endpoint_contracts.py` therefore has a new verified hash,
recorded in `PHASE_3B_VERIFIED_CHANGESET.md`. No implementation manifest or
historical baseline was overwritten.

## File-by-file review

### `modules/ts_endpoint_evidence.py`

1. Actual change: new module with two frozen dataclasses and two functions.
   It loads initial/final POSCAR representations, calculates raw
   minimum-image displacements, loads each ASE representation once, calculates
   the existing mass-weighted COM displacement, and returns sorted
   connectivity edges.
2. Purpose: remove the duplicate initial ASE load and isolate raw measurement
   from scientific interpretation.
3. Authorization: within the exact Phase 3B production plan.
4. Public API: no existing API changed. The new names are additive. They are
   treated as internal by architecture, although Python does not enforce that
   because their names are not underscore-prefixed.
5. Return structure: new internal `EndpointStructures` and
   `EndpointGeometryEvidence`; no existing return type replaced.
6. Exceptions: no catch or conversion. File, ASE, NumPy, and connectivity
   failures propagate.
7. Side effects: file reads only. No write, database, routing, scheduler, or
   mutation call was found.
8. Unrecorded change: none in production behavior. The evidence dataclasses
   are shallowly frozen; their contained `dict`/POSCAR objects are still
   mutable. They remain internal and are not mutated by the current call path.

### `modules/ts_endpoint_validator.py`

1. Actual current delta relative to the recorded Phase 3A architecture:
   raw POSCAR/ASE loading and displacement/connectivity measurement are
   delegated to `ts_endpoint_evidence`; `_observed_bond_changes` now consumes
   raw edges; the duplicate COM/ASE-loading helper is absent.
2. Purpose: one raw evidence path and one initial ASE load per successful
   validation.
3. Authorization: within the exact Phase 3B plan.
4. Public API: current signatures, constants, Enum order, dataclass fields,
   defaults, and module path match `TS_ENDPOINT_API_CONTRACT.md`.
5. Return structure: the 24-field `EndpointValidationResult` order is exact.
6. Exceptions: no new catch; invalid file/config and calculation exceptions
   propagate at the same outer boundary.
7. Side effects: YAML/structure reads only; no write or database call.
8. Unrecorded change: none found. Because the old bytes were not retained,
   exact line-by-line deletion claims cannot be independently reconstructed
   from Git; current code and prechange architecture agree with the manifest.

### `modules/ts_endpoint_generator.py`

1. Phase 3A SHA-256 and current SHA-256 are both
   `db07eea4541cfdb414cc8957a50dd14b5881264c5310d20df7f6900c28ddc1da`.
2. Actual Phase 3B production modification: none.
3. Authorization: correctly left unchanged.
4. Public API/return/exception/file side effects: unchanged.
5. Boundary finding: it consumes validator status and metrics to reject
   `REJECTED` candidates and rank the rest. It does not create an endpoint
   scientific status or `EndpointValidationResult.reasons`.
6. Precision correction: it does create separate, pre-existing
   `eligibility_reasons` for global-minimum reuse. Statements that it creates
   “no reason code” must be read as “no endpoint scientific reason code.”

### `modules/structure_purpose_manager.py`

1. Phase 3A SHA-256 and current SHA-256 are both
   `f68fbb78a7e5f4926cb0531a5b4b0e38211fc839bd8304f1ad96d846651749b5`.
2. Actual Phase 3B production modification: none.
3. Public API, routing result, exceptions, and persistence mapping: unchanged.
4. It invokes the generator once and saves only after a generated result
   exists. It does not import the validator or calculate endpoint science.
5. No implementation-report omission found.

### `modules/ts_endpoint_database.py`

1. Phase 3A SHA-256 and current SHA-256 are both
   `8145e739bf80b0eee5e017a28b3caf4e0dac9310b85090f60d6bcef77208a702`.
2. Actual Phase 3B production modification: none.
3. Public API, record fields, JSON behavior, query order, and exceptions:
   unchanged.
4. Ordinary adapter calls do not invoke the migration runner, validator, or
   generator. `_VALID_STATUSES` is a storage-integrity allow-list, not a
   structural scientific evaluation.
5. The blocked migration runner remains in the same module. This pre-existing
   mixed responsibility is recorded and remains blocked.

### `tests/test_ts_endpoint_contracts.py`

Implementation changed the Phase 3A 17-test file to 20 tests. The independent
review added five more without changing production:

- fresh POSCAR/ASE object identity and no stale cache across validations;
- preservation of ASE symbols, cell, PBC, constraints, tags, and initial
  magnetic moments;
- collector metric failure propagation and no manager persistence;
- manager database-failure propagation;
- serialization rollback and incompatible-table/no-migration protection.

Current result: 25 tests passed. Current SHA-256:
`4af139c9fd4802d6b6670239e6f13e0675d7b05bf412ce2d1aa79e301cad4bf4`.

### `tests/test_structure_purpose_manager.py`

The implementation replaced execution of the blocked migration with a
hand-built temporary Schema and a no-implicit-migration assertion. The change
is recorded by the implementation report and manifest. The independent review
made no further change. All 16 tests passed; current SHA-256 remains
`14fe6e6ea5a1178659156616089fb9c41c0a4f1d6a5537230c8fba88af68156e`.

## Production-change conclusion

The independent hash comparison supports the claim that only
`ts_endpoint_validator.py` and the new `ts_endpoint_evidence.py` changed
production source in Phase 3B. Generator, manager, and database adapter are
byte-identical to Phase 3A. No configuration, migration, Schema, real
database, NEB path-quality, execution-gate, scheduler, or submission change
was found.

## Report accuracy findings

No production change omitted from the implementation report was found. Two
wording qualifications are required:

1. “one read” means one ASE load per initial/final structure after preflight;
   each file is still parsed once through POSCAR and once through ASE because
   those representations serve different frozen algorithms;
2. the Phase 3B compatibility report's blanket `IDENTICAL` claim is stronger
   than the retained historical evidence for unrecorded floating metrics.
   Exact recorded fields are identical; unrecorded historical floats are
   classified `SEMANTICALLY_EQUIVALENT` in the independent behavior report.

Neither qualification is a behavior regression.
