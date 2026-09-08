# Final API Compatibility Report

Date: 2026-07-27

## Conclusion

No public import path, required parameter, default, documented CLI path, or
endpoint result field was removed. The authorized correction deliberately
makes empty reaction identity fail earlier and adds a guarded empty-rollback
API. Compatibility is verified by contract tests and the full regression suite.

## Public Python interfaces

| Surface | Compatibility result | Evidence |
|---|---|---|
| `scripts.ts_strategy_engine.execution_gate` | COMPATIBLE | legacy constants/functions re-exported; signature and reverse-import tests pass |
| `scripts.ts_strategy_engine.execution_decision` | ADDITIVE | pure internal/public helper module; no reverse dependency on gate |
| `scripts.neb_agent.path_quality_control` | COMPATIBLE | `quality_source_paths`, `collect_evidence`, `evaluate_quality` remain importable |
| `scripts.neb_agent.path_quality_service` | ADDITIVE | request/service functions do not replace old paths |
| `scripts.neb_agent.path_quality_cli` | COMPATIBLE | module path and arguments preserved; help exits 0 |
| `scripts.neb_agent.pilot_validation` | COMPATIBLE | original functions remain callable; shared adapter is additive |
| `modules.ts_endpoint_generator` | COMPATIBLE WITH STRICTER INPUT | old path/signature/result preserved; empty reaction ID now raises |
| `modules.ts_endpoint_validator` | COMPATIBLE | public dataclasses/enums/validator signature and output fields preserved |
| `modules.structure_purpose_manager` | COMPATIBLE | Phase 3A SHA-256 preserved through Phase 3B; call-order tests pass |
| `modules.ts_endpoint_database` | COMPATIBLE WITH ADDITIVE GUARD | CRUD paths/signatures/fields preserved; migration validation and empty-only rollback are additive |
| `scripts.artifact_io` | COMPATIBLE | existing public writer/hash functions retained |
| SSH/LSF/submission modules | COMPATIBLE | timeout/idempotency changes preserve entry paths and make failures stricter, not successful |

The new endpoint evidence collector is additive. It is not a replacement
public API for validator results.

## 重点 contract snapshot

| Public callable | Frozen signature |
|---|---|
| `execution_gate.decide_execution` | `(geometry, analysis, thresholds, *, climb, path_reviewed, path_quality=None, preflight=None, validation=None, scheduler=None, authorization=None, source_bindings=None)` |
| `execution_gate.require_action` | `(decision_path, action, current_state_sha256)` |
| `execution_gate.validate_decision` | `(decision)` |
| `path_quality_control.evaluate_quality` | `(evidence, thresholds)` |
| `path_quality_service.load_path_quality_thresholds` | `(quality_path, geometry_path)` |
| `path_quality_service.build_path_quality_report` | `(request)` |
| `TSEndpointGenerator` | `(validator=None)` |
| `TSEndpointGenerator.generate` | `(self, request, candidates) -> GeneratedTSEndpoint` |
| `TSEndpointValidator` | `(config_path=configs/structure_purpose_routing.yaml)` |
| `TSEndpointValidator.validate` | `(self, request) -> EndpointValidationResult` |
| `StructurePurposeManager` | keyword-only collaborators plus unchanged `config_path` default |
| `StructurePurposeManager.select_structure` | `(self, purpose=None, *, context=None, legacy_request=None, adsorption_request=None, ts_request=None, endpoint_candidates=()) -> StructurePurposeResult` |
| `TSEndpointDatabase` | `(database)` |
| `TSEndpointDatabase.save/get/find_by_reaction` | `(record) -> str`; `(endpoint_record_id) -> dict`; `(reaction_id) -> list[dict]` |
| `apply_ts_endpoint_migration` | `(database, *, rollback=False) -> None`; `rollback=True` now refuses |
| `rollback_empty_ts_endpoint_migration` | `(database, *, confirmation) -> None` |

Annotations are documented in `TS_ENDPOINT_API_CONTRACT.md` and inspected at
runtime.

## Import/reference scan

The scan covered static imports, tests, `python -m` commands, configuration
entry points, documentation, monkeypatch paths, and string producer paths.

- Production code contains no dynamic `import_module` path for a second gate,
  path-quality evaluator, or endpoint validator.
- No internal import cycle was found.
- Existing test monkeypatches target the actual service/evidence/adapter
  boundaries, not copied implementations.
- `configs/execution_backends.yaml` continues to point to the unified
  `scripts.ts_strategy_engine.cli active-learning` surface.
- Historical `path_quality_control` producer strings remain stable.

## Major CLI acceptance

All commands below were run with `--help` and returned exit code 0:

1. `python -m scripts.ts_strategy_engine.cli --help`
2. `python -m scripts.ts_strategy_engine.cli active-learning --help`
3. `python -m scripts.ts_strategy_engine.execution_gate_cli --help`
4. `python -m scripts.neb_agent.path_quality_cli --help`
5. `python -m scripts.neb_agent.submission --help`
6. `python -m scripts.neb_agent.remote_monitor --help`
7. `python -m scripts.neb_agent.pilot_validation --help`
8. `python -m scripts.adsmind_lite.plan_adsorption_candidates --help`
9. `python -m scripts.aqcat25_handoff --help`

No command contacted SSH/LSF, submitted work, or touched a database during help
acceptance.

## Schema and serialization

The endpoint result dataclass and database record fields are unchanged. The
endpoint threshold policy intentionally advances to
`ts_endpoint_thresholds_v2` with contact and desorption keys. The core registry
schema remains version 5; the optional endpoint extension remains version 1 and
is not applied implicitly. Path-quality and execution-gate Schemas are
unchanged.
