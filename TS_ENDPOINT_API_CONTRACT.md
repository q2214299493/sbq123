# TS Endpoint Public API Contract

Date: 2026-07-27
Scope: Phase 3A behavior freeze; no production implementation change

## Contract rule

An interface is treated as public when it is imported by another repository
module or test, returned by a public call, serialized into a stored record, or
named by the transition-state governance documentation. Leading underscores
alone are not used to decide public status.

No endpoint module has `__all__`, a CLI parser, a package entry point, or a
`python -m` entry. Repository scanning found no dynamic import, plugin
registry, subprocess module string, configuration module path, or monkeypatch
path for the four modules.

## `modules.ts_endpoint_generator`

### Public data types

| Type | Frozen constructor fields | Role |
|---|---|---|
| `EndpointCandidate` | `endpoint_id`, `product_id`, `structure_path`, `site`, `energy_eV=None`, `is_global_minimum=False`, `local_stability_validated=False`, `path_connectivity_validated=False`, `structure_file_id=None`, `metadata={}` | Candidate reference and reuse evidence; does not contain generated coordinates |
| `TSEndpointGenerationRequest` | `reaction_id`, `surface`, `reaction_type`, `reactant_id`, `initial_structure`, `reactive_atoms`, `adsorbate_atoms`, `bond_changes`, `surface_atoms=()`, `expected_site_changes=()`, `atom_map=()`, `template_id=None`, `endpoint_role="final"`, `endpoint_version="1"`, `source_calculation_id=None`, `stable_structure_path=None`, `stable_structure_file_id=None` | Selection and validation request |
| `CandidateAssessment` | `candidate`, `validation`, `reuse_eligible`, `eligibility_reasons=()` | Per-candidate result; returned inside `GeneratedTSEndpoint` |
| `GeneratedTSEndpoint` | `request`, `candidate`, `validation`, `assessments` | Selected result |

All four are frozen dataclasses. Field names, order, defaults, tuple ordering,
and nested result types are compatibility requirements for Phase 3B.

### Public class

```text
TSEndpointGenerator(
    validator: TSEndpointValidator | None = None
)

generate(
    request: TSEndpointGenerationRequest,
    candidates: Iterable[EndpointCandidate],
) -> GeneratedTSEndpoint
```

Observed callers:

- `StructurePurposeManager`;
- `tests/test_structure_purpose_manager.py`;
- `tests/test_ts_endpoint_contracts.py`;
- transition-state README names the module as the endpoint implementation.

Exceptions and side effects:

- invalid `endpoint_role`: `ValueError`;
- no eligible candidate: `ValueError`;
- validator/config/file errors propagate unchanged;
- reads candidate structures through the validator;
- does not create, alter, copy, or write a structure;
- has no database or scheduler side effect.

Compatibility requirement: keep the existing module path, constructor
injection point, method signature, deterministic assessment order, selection
priority, return dataclasses, and exceptions.

Despite its name, the current class is a candidate validator/selector, not a
geometry generator. Phase 3B must not silently add geometry generation to this
API.

## `modules.ts_endpoint_validator`

### Public constants and Enum

- `DEFAULT_CONFIG`
- `MULTI_EVENT_REACTION = "MULTI_EVENT_REACTION"`
- `EndpointValidationStatus`, in this exact order and with these exact values:
  `VALID`, `VALID_WITH_WARNING`, `REVIEW_REQUIRED`, `REJECTED`

### Public data types

| Type | Frozen fields/contract |
|---|---|
| `EndpointThresholdPolicy` | version, six positive numeric thresholds, `applied_overrides=()` |
| `BondChange` | `kind`, `atoms`; kind is `break`/`form`, atom pair is sorted, invalid values raise `ValueError` |
| `EndpointValidationRequest` | two structure paths; reactive/adsorbate/bond-change inputs; optional surface/site/map/surface/reaction/template context |
| `EndpointValidationResult` | 24 fields in current dataclass order; `as_dict()` converts only `status` to its string value |

`EndpointValidationResult` field order:

```text
status
threshold_version
applied_threshold_overrides
atom_mapping_method
periodic_mapping_method
expected_bond_changes
observed_bond_changes
site_coordination_bond_changes
unexpected_bond_changes
missing_expected_bond_changes
expected_site_changes
observed_site_changes
unexpected_site_changes
atomic_displacement_A
reactive_displacement_A
adsorbate_com_displacement_A
max_reactive_displacement_A
max_non_reactive_adsorbate_displacement_A
max_surface_displacement_A
migration_flag
validation_score
errors
warnings
reasons
```

The tuple/list ordering is part of the behavior contract. Errors and warnings
are independently deduplicated and lexically sorted; `reasons` is
`errors + warnings`.

### Public calls

```text
load_endpoint_threshold_policy(
    config_path: Path = DEFAULT_CONFIG,
    *,
    surface: str | None = None,
    reaction_type: str | None = None,
    template_id: str | None = None,
) -> EndpointThresholdPolicy

TSEndpointValidator(config_path: Path = DEFAULT_CONFIG)

TSEndpointValidator.validate(
    request: EndpointValidationRequest
) -> EndpointValidationResult
```

Observed callers:

- `TSEndpointGenerator`;
- both endpoint test files;
- governance and source-architecture documents.

Exception and side-effect contract:

- malformed or missing threshold configuration: `ValueError` or file I/O
  exception;
- missing structure: `FileNotFoundError`;
- malformed structure: `ValueError`;
- missing request constructor fields: Python `TypeError`;
- scientific rejection is returned as `EndpointValidationResult(REJECTED)`,
  not raised;
- reads YAML and structure files; does not write structures, reports, or
  database records.

Phase 3B must preserve all statuses, reason strings, priority, score mapping,
threshold values, override order, mapping labels, output fields, and exception
boundary.

## `modules.structure_purpose_manager`

### Public constants, Enum, Protocols, and data types

- `DEFAULT_CONFIG`
- `PURPOSE_CONFIRMATION_PROMPT`
- `StructurePurpose`: `ADSORPTION_STABLE`, `TS_ENDPOINT`, `UNRESOLVED`
- `StructurePurposeContext`
- `PurposeResolution`
- `LegacyStructureWorkflow` protocol
- `StableAdsorptionSelector` protocol
- `StructurePurposeResult`

### Public calls

```text
resolve_structure_purpose(
    context: StructurePurposeContext,
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> PurposeResolution

StructurePurposeManager(
    *,
    stable_adsorption_selector: StableAdsorptionSelector,
    ts_endpoint_generator: TSEndpointGenerator,
    ts_endpoint_database: TSEndpointDatabase,
    legacy_workflow: LegacyStructureWorkflow | None = None,
    config_path: Path = DEFAULT_CONFIG,
)

StructurePurposeManager.select_structure(
    purpose: str | StructurePurpose | None = None,
    *,
    context: StructurePurposeContext | None = None,
    legacy_request: Any = None,
    adsorption_request: Any = None,
    ts_request: TSEndpointGenerationRequest | None = None,
    endpoint_candidates: Iterable[EndpointCandidate] = (),
) -> StructurePurposeResult
```

Observed callers:

- endpoint tests only; no unified CLI or production workflow currently imports
  the manager;
- `StructurePurposeManager` imports generator/database directly.

Routing contract:

1. explicit `context.purpose` or method `purpose`;
2. inherited `parent_purpose`;
3. legacy bypass for non-new tasks, listed operations, or batch;
4. unresolved confirmation.

The TS route is generator/validator first, record construction second,
database save last. A generator/validator failure must prevent `save()`.

Exceptions and side effects:

- bad routing config: `ValueError`;
- legacy route without adapter: `ValueError`;
- TS route without request: `ValueError`;
- dependency errors propagate;
- stable and legacy routes call only their injected adapters;
- successful TS route hashes files and writes through the injected database;
- unresolved route has no persistence side effect.

## `modules.ts_endpoint_database`

### Public data type

`TSEndpointRecord` is a frozen serialization contract with 14 stored fields.
Its constructor rejects unsupported IDs, roles, statuses, and inconsistent
stable/path combinations with `ValueError`. `as_dict()` preserves dataclass
field order.

### Public adapter

```text
TSEndpointDatabase(database: Path)

save(record: TSEndpointRecord) -> str
get(endpoint_record_id: str) -> dict[str, Any]
find_by_reaction(reaction_id: str) -> list[dict[str, Any]]
```

Behavior contract:

- exact duplicate content returns the existing record ID;
- same ID with different content raises `ValueError`;
- missing ID raises `KeyError`;
- missing table raises `ValueError`;
- SQLite/transaction errors propagate and are rolled back by `open_registry`;
- query order is `endpoint_role`, `created_at`, `endpoint_record_id`;
- `validation_json` is deterministically serialized with sorted JSON keys;
- the adapter has no update API;
- it stores even `REJECTED` validation evidence and does not re-run science.

### Guarded migration APIs

```text
apply_ts_endpoint_migration(
    database: Path,
    *,
    rollback: bool = False,
) -> None
```

The legacy signature is preserved. `rollback=True` now refuses destructive
rollback. Empty-table rollback has a separate exact-confirmation API:

```text
rollback_empty_ts_endpoint_migration(
    database: Path,
    *,
    confirmation: str,
) -> None
```

Both SQL files are review-only. Direct execution, unauthorized real-database
application, and non-empty rollback are prohibited.

## Config contracts

### `configs/structure_purpose_routing.yaml`

Top-level key order and fields:

```text
schema_version
enabled
endpoint_validation:
  threshold_version
  defaults:
    reactive_atom_displacement_warning_A
    non_reactive_adsorbate_displacement_warning_A
    adsorbate_com_displacement_warning_A
    surface_atom_displacement_warning_A
    covalent_radius_scale
    minimum_bond_distance_A
    collision_radius_scale
    absolute_minimum_distance_A
    desorption_height_change_warning_A
  overrides:
    surfaces
    reaction_types
    templates
```

The file combines a routing feature switch with scientific endpoint thresholds.
The Phase 3A/3B v1 freeze was intentionally superseded by the authorized v2
contact/desorption correction; subsequent changes again require explicit
scientific review.

### `configs/ts_connectivity_gate.yaml`

This configuration is not consumed by the four endpoint modules. It is owned
by `scripts.ts_validation.connectivity` for later bidirectional connectivity
validation. Phase 3B must not merge it into endpoint purity validation or
change its eight fields/defaults.
