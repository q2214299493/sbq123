# TS Endpoint Behavior Baseline

Date: 2026-07-27
Baseline type: pre-Phase-3B synthetic behavior freeze

## Method and safety boundary

Fixtures use minimal synthetic POSCAR files in pytest temporary directories,
in-memory objects, mock adapters, and temporary SQLite files with a hand-built
test-only table. No blocked migration file was executed. The real project
database was neither opened nor hashed during behavior tests.

Tuple ordering, dataclass field ordering, statuses, reasons, exceptions, and
side effects below are current observations, not claims that every scientific
behavior is correct.

## Generator/selector samples

| Case | Input summary | Return/status/reasons | Side effects and Schema |
|---|---|---|---|
| Valid break endpoint | Fe/C/O order, identity atom map, requested C–O break | `GeneratedTSEndpoint`; validator `VALID`; observed `(BondChange("break",(1,2)),)` | Reads structures only; four top-level dataclass fields |
| Target bond formation | initially separated C/O, final bonded, requested form | `VALID`; observed form `(1,2)` | No write |
| Determinism | two otherwise equal candidates `endpoint-b`, `endpoint-a` | both calls select `endpoint-a`; validation dict identical; assessments retain input order | Input bytes unchanged |
| Atom count/order | selected candidate has Fe/C/O and three atoms | validator mapping passes; candidate structure is returned by path | No copied structure |
| Site information | candidate `site="C_near+O_near"` | exact value preserved | No site derivation |
| Invalid role | `endpoint_role="middle"` | `ValueError("endpoint_role must be...")` | No validation/write |
| No eligible candidate | empty candidates or all rejected | `ValueError("no path-compatible...")` | No result/persistence |
| Missing reaction identity | empty reaction/surface/type/reactant strings, valid geometry | currently succeeds and returns `VALID` | Gap: identity is pass-through, not validated |

Selection order is frozen as validation status → migration flag → reactive
displacement → adsorbate COM displacement → surface displacement → energy →
endpoint ID. Energy cannot override an earlier gate.

## Validator samples

| Case | Current status | Exact or characteristic reasons | Exception/side effect |
|---|---|---|---|
| Complete pass | `VALID` | `()` | score 1.0; read only |
| Atom count mismatch | `REJECTED` | one or more `STRUCTURE_INCOMPATIBLE:*` | returned result |
| Element/order mismatch | `REJECTED` | one or more `STRUCTURE_INCOMPATIBLE:*` | returned result |
| Non-identity atom map | `REJECTED` | `("ATOM_MAP_NOT_PRESERVED",)` | returned result |
| Intended bond unchanged | `REJECTED` | `("EXPECTED_BOND_CHANGE_MISSING",)` | returned result |
| Identical endpoints | `REJECTED` | same missing-event reason for the sampled contract | returned result |
| Unexpected non-target Fe–adsorbate bond | `REVIEW_REQUIRED` | includes `UNEXPECTED_BOND_CHANGE` | returned result |
| Site evidence mismatch | `REVIEW_REQUIRED` | `EXPECTED_SITE_CHANGE_MISSING`, `UNEXPECTED_SITE_CHANGE`; sorted | returned result |
| Multiple issues | `REVIEW_REQUIRED` or `REJECTED` according to errors-first priority | `errors` sorted, then `warnings` sorted; `reasons=errors+warnings` | returned result |
| Reactive displacement only | `VALID_WITH_WARNING` | `REACTIVE_ATOM_DISPLACEMENT_WARNING` | a displacement warning alone does not reject |
| Large COM migration | `REVIEW_REQUIRED` | includes `MULTI_EVENT_REACTION` | returned result |
| Atom contact at 0.2 Å | currently `VALID` | `()` | frozen risk: no collision reason |
| Sampled detached/opposite motion | currently `VALID_WITH_WARNING` | only `REACTIVE_ATOM_DISPLACEMENT_WARNING` | frozen risk: no desorption reason |
| Missing constructor fields | none | Python `TypeError` | no file access |
| Missing structure file | none | `FileNotFoundError` | no output |
| Invalid POSCAR text | none | `ValueError` | no output |

Result field order is the 24-field order recorded in
`TS_ENDPOINT_API_CONTRACT.md`. `as_dict()` retains that order and converts the
Enum status to a string. Bond changes, errors, warnings, expected/observed site
sets, and reasons use deterministic tuple ordering.

## Purpose manager samples

| Case | Input/rule | Result | Persistence |
|---|---|---|---|
| Explicit purpose and parent both present | explicit adsorption, parent TS | explicit adsorption wins | endpoint DB untouched |
| Normal TS route | explicit TS, one valid candidate | call order `validator`, then `database`; `PURPOSE_RESOLVED` | one record |
| Validator rejection | identical endpoints with required break | generator raises no-compatible `ValueError` | database save not called |
| Unknown explicit purpose | unknown string | `UNRESOLVED` / `AWAITING_PURPOSE_CONFIRMATION` | none |
| Stable route | `ADSORPTION_STABLE` | stable selector only | none |
| Legacy/default route | no purpose and not a new task | legacy selector only; `LEGACY_UNCHANGED` | none |
| Missing TS request | TS purpose | `ValueError` | none |
| Disabled routing switch | `enabled: false` fixture | `LEGACY_UNCHANGED` | none |

The manager does not convert dependency errors into a default success result.

## Database adapter samples

All samples use temporary SQLite with a test-only Schema created directly by
the test; neither blocked SQL file is read or executed.

| Case | Current result | Database effect |
|---|---|---|
| Save and get | returns record ID; `get` reconstructs boolean and JSON | one row |
| Find by reaction | list ordered by role/time/ID | read only |
| Exact duplicate | returns existing ID | still one matching row |
| Same ID/different content | `ValueError` | no second row |
| Missing ID | `KeyError` | none |
| Missing endpoint table | `ValueError` | none |
| Invalid record ID/path invariant | constructor `ValueError` | no connection/write |
| Triggered SQLite insert failure | `sqlite3.IntegrityError` propagates | transaction rollback; zero rows |
| Stored `REJECTED` evidence | accepted as a record | proves adapter does not re-evaluate science |
| Update | no public update method | unsupported |

Stored row keys are the SQL adapter fields plus decoded `validation`; the raw
`validation_json` key is removed by `_row`. JSON keys are serialized
deterministically.

## Test binding

`tests/test_ts_endpoint_contracts.py` contains 17 contract tests covering the
above signatures, fields, deterministic results, errors, routing order,
failure-before-persistence, temporary database behavior, and absence of
scientific imports/calls in the database adapter.

The existing `tests/test_structure_purpose_manager.py` remains unchanged. Six
safe non-migration tests from it were run with the new contract file. Tests in
that historical file that invoke `apply_ts_endpoint_migration` were
deliberately not executed because the migration is blocked.
