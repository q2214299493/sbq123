# Phase 3B Prechange Snapshot

Date: 2026-07-27
Captured before any Phase 3B production-source modification

## Safety boundary

- Endpoint tests used synthetic POSCAR files, mocks, and temporary SQLite only.
- Neither blocked endpoint migration was executed.
- The real database was not opened through SQLite; its read-only SHA-256 was
  recorded as
  `4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb`.
- No SSH, LSF, submission, VASP, NEB, execution-gate, or path-quality action
  was executed.

## Production/configuration hashes

| SHA-256 | Bytes | Path |
|---|---:|---|
| `db07eea4541cfdb414cc8957a50dd14b5881264c5310d20df7f6900c28ddc1da` | 6015 | `modules/ts_endpoint_generator.py` |
| `b0bc707a97c3a032bd5d7d610cb96a961034e17ad763cc1ccb3e7d645f808882` | 18639 | `modules/ts_endpoint_validator.py` |
| `f68fbb78a7e5f4926cb0531a5b4b0e38211fc839bd8304f1ad96d846651749b5` | 9668 | `modules/structure_purpose_manager.py` |
| `8145e739bf80b0eee5e017a28b3caf4e0dac9310b85090f60d6bcef77208a702` | 7763 | `modules/ts_endpoint_database.py` |
| `a4bc47e51e21a612e067b8a4fd123703db3da207219c3ebc7a28f16164ad5315` | 441 | `configs/structure_purpose_routing.yaml` |
| `43427e5bd1a7950d7ee6defc0ce43c14c80b37b04175ee790fba1f61c629fe88` | 300 | `configs/ts_connectivity_gate.yaml` |

Blocked migration hashes, recorded without execution:

- forward:
  `cbbedb50005d1bc57a821d5e983e2578c2d8e43c8f0cfe774f710af91ce1093f`;
- rollback:
  `6fdd989767a58aea76987cdbff4b0fa77182f1d4fd8cb2477ae10dacaa4808d5`.

## Public signatures

The 17-test API contract confirmed:

```text
TSEndpointGenerator.__init__(self, validator)
TSEndpointGenerator.generate(self, request, candidates)
TSEndpointValidator.__init__(self, config_path)
TSEndpointValidator.validate(self, request)
load_endpoint_threshold_policy(
    config_path, *, surface, reaction_type, template_id
)
resolve_structure_purpose(context, *, config_path)
StructurePurposeManager.select_structure(
    self, purpose, *, context, legacy_request, adsorption_request,
    ts_request, endpoint_candidates
)
TSEndpointDatabase.save(self, record)
TSEndpointDatabase.get(self, endpoint_record_id)
TSEndpointDatabase.find_by_reaction(self, reaction_id)
```

All dataclass fields/defaults and the 24-field
`EndpointValidationResult` order matched `TS_ENDPOINT_API_CONTRACT.md`.

## Frozen generation/validation behavior

| Sample | Prechange result |
|---|---|
| Valid endpoint / requested break | `GeneratedTSEndpoint`; `VALID`; observed break `(1,2)` |
| Requested bond formation | `VALID`; observed form `(1,2)` |
| Same input / tied candidates | deterministic `endpoint-a`; assessment input order retained |
| Atom mapping anomaly | `REJECTED`; `("ATOM_MAP_NOT_PRESERVED",)` |
| Atom-count/species-order mismatch | `REJECTED`; `STRUCTURE_INCOMPATIBLE:*` |
| Identical endpoint | `REJECTED`; `("EXPECTED_BOND_CHANGE_MISSING",)` |
| Unexpected non-target bond | `REVIEW_REQUIRED`; includes `UNEXPECTED_BOND_CHANGE` |
| 0.2 Å atom contact | current frozen result `VALID`; no reason |
| Sampled detached/opposite movement | current frozen result `VALID_WITH_WARNING`; only `REACTIVE_ATOM_DISPLACEMENT_WARNING` |
| Site evidence mismatch | `REVIEW_REQUIRED`; sorted `EXPECTED_SITE_CHANGE_MISSING`, `UNEXPECTED_SITE_CHANGE` |
| Multiple issues | errors sorted first, warnings sorted second; `reasons=errors+warnings` |
| Missing structure | `FileNotFoundError` |
| Invalid structure | `ValueError` |
| Invalid generator role/no candidate | `ValueError`; no default result |

No sample wrote or modified a structure.

## Purpose and persistence behavior

| Sample | Prechange result |
|---|---|
| Explicit purpose + different parent purpose | explicit purpose wins |
| Unknown purpose | `UNRESOLVED` / `AWAITING_PURPOSE_CONFIRMATION` |
| Default non-new call | legacy route / `LEGACY_UNCHANGED` |
| TS success | call order validator → database; one record |
| Validator rejection | generator raises no-compatible `ValueError`; database not called |
| Validator exception | exception propagates; no default success/persistence |
| Exact DB duplicate | existing ID returned; one row |
| Same ID/different content | `ValueError`; no second row |
| Missing row/table | `KeyError` / `ValueError` |
| Forced insert failure | `sqlite3.IntegrityError`; transaction rolls back to zero rows |
| Stored `REJECTED` evidence | adapter stores it without scientific re-evaluation |

## Test result

```text
python -m pytest -q -ra tests/test_ts_endpoint_contracts.py \
  [six explicit non-migration endpoint test node IDs]

23 passed; exit 0
skip/xfail: 0
```

This snapshot is the direct before-state for
`PHASE_3B_BEHAVIOR_COMPATIBILITY.md`.
