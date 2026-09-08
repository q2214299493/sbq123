# Phase 3B Independent Behavior Verification

Date: 2026-07-27
Reference: `TS_ENDPOINT_BEHAVIOR_BASELINE.md` and
`PHASE_3B_PRECHANGE_SNAPSHOT.md`

## Evidence method

The Phase 3A baseline records exact statuses, characteristic/exact reasons,
field order, exceptions, routing, and side effects, but it does not retain an
executable old validator or every old floating-point value. Therefore:

- `IDENTICAL` means every value explicitly frozen in the historical documents
  matched the current executable result;
- `SEMANTICALLY_EQUIVALENT` means recorded scientific status/reasons/fields
  match and the calculation path is unchanged, but an exact old floating
  golden value was not retained;
- `INCOMPATIBLE` means a scientific or contract difference was observed.

No case was normalized beyond temporary paths.

## Generator and validator cases

| Case | Current executable result | Comparison evidence | Conclusion |
|---|---|---|---|
| Valid break endpoint | `GeneratedTSEndpoint`, `VALID`, observed break `(1,2)`, score `1.0` | exact recorded type/status/bond/reasons/fields match | IDENTICAL |
| Target bond formation | `VALID`, observed form `(1,2)` | exact recorded status/bond match | IDENTICAL |
| Repeated identical input | same selected ID and validation dict | deterministic test, input bytes unchanged | IDENTICAL |
| Atom count mismatch | `REJECTED`, `STRUCTURE_INCOMPATIBLE:*` | exact recorded boundary match | IDENTICAL |
| Element/order mismatch | `REJECTED`, `STRUCTURE_INCOMPATIBLE:*` | exact recorded boundary match | IDENTICAL |
| Non-identity mapping | `REJECTED`, `ATOM_MAP_NOT_PRESERVED` | exact reason match | IDENTICAL |
| Intended bond unchanged | `REJECTED`, `EXPECTED_BOND_CHANGE_MISSING` | exact reason match | IDENTICAL |
| Identical endpoints | same missing-event rejection | exact recorded result match | IDENTICAL |
| Unexpected non-target bond | `REVIEW_REQUIRED`, includes `UNEXPECTED_BOND_CHANGE` | exact recorded status/reason match | IDENTICAL |
| Site mismatch/coordination | frozen review classification and sorted reasons | exact ordering assertions pass | IDENTICAL |
| Multiple issues | errors sorted before warnings; `reasons=errors+warnings` | exact priority/order assertions pass | IDENTICAL |
| Reactive displacement warning | `VALID_WITH_WARNING` | exact status/reason match | IDENTICAL |
| Large COM migration | `REVIEW_REQUIRED`, `MULTI_EVENT_REACTION` | exact status/reason match | IDENTICAL |
| 0.2 Å contact sample | `VALID`, reasons `()` | exact frozen gap match | IDENTICAL |
| Detached/opposite-motion sample | `VALID_WITH_WARNING`; only reactive displacement warning | exact frozen gap match | IDENTICAL |
| Missing constructor fields | `TypeError` | exact exception type | IDENTICAL |
| Missing structure | `FileNotFoundError` | exact exception type | IDENTICAL |
| Invalid POSCAR | `ValueError` | exact exception type | IDENTICAL |
| Empty reaction identity | accepted; request retains `""`; `VALID` | exact frozen gap match | IDENTICAL |

Representative current numerical snapshot:

| Case | Atomic displacement Å | COM Å | Max reactive Å | Score |
|---|---|---:|---:|---:|
| valid break | `{0:0.0, 1:0.2, 2:0.9}` | `0.5998322027847196` | `0.9` | `1.0` |
| identical | all `0.0` | `0.0` | `0.0` | `0.0` |
| close contact | `{0:0.0, 1:0.2, 2:0.8}` | `0.3711888611210284` | `0.8` | `1.0` |
| detached sample | `{0:0.0, 1:5.0, 2:4.2}` | `0.25493752231345973` | `5.0` | `0.75` |

Floating values are shown rounded where the executable result contains normal
binary floating representation. Because Phase 3A did not preserve these exact
numbers, their historical comparison is `SEMANTICALLY_EQUIVALENT`; no formula,
threshold, field, status, or reason difference was found.

## Single-read and object-isolation cases

| Case | Result | Conclusion |
|---|---|---|
| One successful validation | ASE calls exactly `[initial, endpoint]`; POSCAR calls exactly `[initial, endpoint]` | IDENTICAL except authorized read-count reduction |
| Two validations | four distinct ASE objects and four distinct POSCAR objects | IDENTICAL behavior; no cross-call cache |
| Endpoint file changed between calls | first `VALID`, second reads new bytes and becomes `REJECTED` | IDENTICAL scientific response to current input |
| Metadata after collector | symbols, cell, PBC, constraints, tags, initial magnetic moments unchanged | IDENTICAL |
| Collector metric failure | same exception object propagates | IDENTICAL exception boundary |

The read-count change is the authorized non-scientific implementation
difference. No result field changes because of it.

## Purpose-routing cases

| Case | Current result | Conclusion |
|---|---|---|
| Explicit purpose over parent | explicit purpose wins | IDENTICAL |
| Normal TS path | generator once, validator once, database once | IDENTICAL |
| Unknown purpose | unresolved/awaiting confirmation; no endpoint write | IDENTICAL |
| Default non-new call | legacy unchanged | IDENTICAL |
| Disabled feature | legacy unchanged | IDENTICAL |
| Stable route | stable adapter only | IDENTICAL |
| Missing TS request | `ValueError` | IDENTICAL |
| Validator rejection | no-compatible `ValueError`; no save | IDENTICAL |
| Validator exception | original exception propagates; no save | IDENTICAL |
| Collector exception through validator | original exception propagates; no save | IDENTICAL |
| Database exception | original SQLite exception propagates; no success result | IDENTICAL |

Purpose rules and priority configuration are byte-identical to Phase 3A.

## Database-adapter cases

| Case | Current result | Conclusion |
|---|---|---|
| Save/get/find | frozen row fields and order | IDENTICAL |
| Exact duplicate | existing ID; one row | IDENTICAL |
| Same ID/different content | `ValueError`; no second row | IDENTICAL |
| Missing ID/table | `KeyError` / `ValueError` | IDENTICAL |
| Stored `REJECTED` evidence | stored without validator call | IDENTICAL |
| Forced insert failure | `sqlite3.IntegrityError`; zero rows | IDENTICAL |
| JSON serialization failure | `TypeError`; zero rows | IDENTICAL |
| Incompatible table | SQLite error; table remains byte/logically untouched | IDENTICAL |
| Adapter initialization | no migration call and no Schema creation | IDENTICAL |

All database files in tests were created below pytest temporary directories.
The real database hash before and after testing is identical.

## Field and API comparison

- 24 `EndpointValidationResult` fields: exact order match.
- Enum status order and values: exact match.
- Errors, warnings, reasons, bond/site tuples: exact deterministic order.
- Generator assessment order and selection priority: exact match.
- Public signatures, keyword-only boundaries, and defaults: exact match.
- Serialized record fields and JSON key sorting: exact match.

## Overall conclusion

- `IDENTICAL`: every historically recorded status, reason, field, ordering,
  exception, routing, and persistence behavior.
- `SEMANTICALLY_EQUIVALENT`: historical floating values not retained as golden
  data, with unchanged formula and no detected result difference.
- `INCOMPATIBLE`: **0 cases**.

The Phase 3A behavior baseline remains compatible with Phase 3B.
