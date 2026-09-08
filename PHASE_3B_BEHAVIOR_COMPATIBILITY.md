# Phase 3B Behavior Compatibility

Date: 2026-07-27
Comparison basis: `TS_ENDPOINT_BEHAVIOR_BASELINE.md` and
`PHASE_3B_PRECHANGE_SNAPSHOT.md`

## Comparison method

The prechange endpoint suite passed 23 tests. After the production change, the
same 23 tests passed. Three additional regression tests were then added, and
the final endpoint suite passed 36 tests (`20` contract tests plus `16`
historical endpoint/manager tests). The full repository suite passed all 265
collected tests.

Tests use synthetic POSCARs, spies, mocks, and temporary SQLite only. Exact
dataclass equality, tuple/list order, status, reasons, metrics, exception type,
call count, and persistence side effects are asserted where applicable.

## Generator and selection samples

| Frozen sample | Before | After | Compatibility |
|---|---|---|---|
| Valid break endpoint | `GeneratedTSEndpoint`; `VALID`; observed break `(1,2)` | Same type, status, and bond change | IDENTICAL |
| Target bond formation | `VALID`; observed form `(1,2)` | Same | IDENTICAL |
| Determinism/tie break | `endpoint-a`; assessments retain input order | Same result on repeated calls | IDENTICAL |
| Atom count/order | Fe/C/O, three atoms, identity mapping | Same candidate path and mapping result | IDENTICAL |
| Site metadata | exact `C_near+O_near` value | Same | IDENTICAL |
| Invalid endpoint role | `ValueError` | Same exception type and message contract | IDENTICAL |
| Empty/all rejected candidates | no-compatible `ValueError` | Same; no persistence | IDENTICAL |
| Empty reaction identity | currently accepted and `VALID` | Same frozen gap | IDENTICAL |
| Direct versus manager call | not separately asserted | exact generated result equality; one generator and one validator call | IDENTICAL |

The frozen selection order remains status, migration flag, reactive
displacement, adsorbate COM displacement, surface displacement, energy, and
endpoint ID.

## Validator samples

| Frozen sample | Before | After | Compatibility |
|---|---|---|---|
| Complete pass | `VALID`, reasons `()`, score `1.0` | Same full result fields | IDENTICAL |
| Atom-count mismatch | `REJECTED`, `STRUCTURE_INCOMPATIBLE:*` | Same return behavior | IDENTICAL |
| Element/order mismatch | `REJECTED`, `STRUCTURE_INCOMPATIBLE:*` | Same return behavior | IDENTICAL |
| Non-identity atom map | `REJECTED`, `ATOM_MAP_NOT_PRESERVED` | Same | IDENTICAL |
| Intended bond unchanged | `REJECTED`, `EXPECTED_BOND_CHANGE_MISSING` | Same | IDENTICAL |
| Identical endpoint | same missing-event rejection | Same | IDENTICAL |
| Unexpected non-target bond | `REVIEW_REQUIRED`, `UNEXPECTED_BOND_CHANGE` | Same | IDENTICAL |
| Site mismatch | review; sorted site reasons | Same status and exact order | IDENTICAL |
| Multiple issues | errors-first priority; sorted errors then warnings | Same exact tuple ordering | IDENTICAL |
| Reactive displacement warning | `VALID_WITH_WARNING` | Same | IDENTICAL |
| Large COM migration | `REVIEW_REQUIRED`, `MULTI_EVENT_REACTION` | Same | IDENTICAL |
| 0.2 Å close contact | currently `VALID`, no reason | Same frozen risk | IDENTICAL |
| Sampled detached/opposite motion | warning only; no desorption reason | Same frozen risk | IDENTICAL |
| Missing constructor field | `TypeError` | Same | IDENTICAL |
| Missing structure | `FileNotFoundError` | Same | IDENTICAL |
| Invalid POSCAR | `ValueError` | Same | IDENTICAL |

All 24 public result fields and `as_dict()` ordering remain unchanged. The new
collector supplies raw evidence only; the validator still creates all status,
reason, score, threshold, and ordering decisions.

## Purpose-routing samples

| Frozen sample | Before | After | Compatibility |
|---|---|---|---|
| Explicit purpose over parent purpose | explicit purpose wins | Same | IDENTICAL |
| Normal TS route | validator then database; one record | Same call order and one save | IDENTICAL |
| Validator rejection | no-compatible `ValueError`; no save | Same | IDENTICAL |
| Validator exception | propagates; no default success | Explicitly regression-tested; no save | IDENTICAL |
| Unknown purpose | unresolved/awaiting confirmation | Same; endpoint DB untouched | IDENTICAL |
| Stable route | stable selector only | Same | IDENTICAL |
| Legacy/default route | legacy selector only | Same | IDENTICAL |
| Missing TS request | `ValueError` | Same | IDENTICAL |
| Disabled routing | legacy unchanged | Same | IDENTICAL |
| Multiple rule priority | existing configured priority | Same | IDENTICAL |

## Database-adapter samples

| Frozen sample | Before | After | Compatibility |
|---|---|---|---|
| Save/get | one row; JSON/boolean decoded | Same | IDENTICAL |
| Find by reaction | frozen ordering | Same | IDENTICAL |
| Exact duplicate | existing ID; one row | Same | IDENTICAL |
| Same ID/different content | `ValueError`; no second row | Same | IDENTICAL |
| Missing ID | `KeyError` | Same | IDENTICAL |
| Missing endpoint table | `ValueError`; no implicit migration | Same, now explicitly tested without migration execution | IDENTICAL |
| Invalid record/path | constructor `ValueError` | Same | IDENTICAL |
| Forced insert failure | `sqlite3.IntegrityError`; rollback | Same | IDENTICAL |
| Stored `REJECTED` evidence | stored without science re-evaluation | Same | IDENTICAL |
| Update | no public update entry | Same | IDENTICAL |

## Public and serialized compatibility

- Public module paths, classes, functions, parameter order, keyword names,
  defaults, return types, and exception semantics: unchanged.
- Generator, validator, manager, and database result field order: unchanged.
- Status names, reason codes, reason order, thresholds, override order, and
  scores: unchanged.
- Routing configuration and connectivity-gate configuration hashes: unchanged.
- Database record fields and deterministic JSON serialization: unchanged.
- Database Schema and schema version: unchanged.

## Conclusion

All frozen samples are `IDENTICAL`; none is semantically normalized and none
is incompatible.
