# Phase 3B Minimal Implementation Plan

Date: 2026-07-27
Status: proposed only; not authorized or implemented

## Recommendation

Phase 3B should be limited to separating non-judgmental endpoint evidence
collection from the single scientific validator while preserving every public
path and frozen output. Generator, manager, database, configuration, SQL,
governance, and execution-gate behavior should remain unchanged.

The audit does not support a four-module rewrite: generator, manager, and the
ordinary database adapter already have distinct responsibilities. The main
mixed responsibility is validator file/config loading plus metric calculation
plus scientific classification.

## Preconditions

1. Explicit authorization to start Phase 3B.
2. Acceptance that Phase 3B is behavior-preserving and will not repair the
   close-contact, desorption, or empty-reaction-identity findings.
3. Blocked migration files and the migration runner remain excluded.
4. The 17 endpoint contract tests and Review Baseline v3 are the starting
   compatibility evidence.
5. No endpoint module may be connected to a real production database or
   workflow during Phase 3B.

## Proposed files

Allowed production scope:

- new internal `modules/ts_endpoint_evidence.py`;
- `modules/ts_endpoint_validator.py`, only to delegate evidence collection and
  keep the sole evaluator/public facade;
- import-only adaptation in `modules/ts_endpoint_generator.py` only if typing
  requires it.

Allowed tests/reports:

- `tests/test_ts_endpoint_contracts.py`;
- minimal additions to existing endpoint tests that do not execute migration;
- Phase 3B behavior comparison and changeset reports.

Explicitly excluded:

- `modules/structure_purpose_manager.py`;
- `modules/ts_endpoint_database.py`;
- both migration SQL files;
- both endpoint/configuration YAML files;
- `AGENT_RULE_TS_ENDPOINT.md`;
- execution gate and NEB path-quality files;
- real database, calculation, scheduler, SSH, LSF, or submission integration.

## Target responsibility boundary

```text
TSEndpointValidator.validate(request)             # unchanged public facade
    ↓
collect_endpoint_evidence(request, policy)        # file parsing/raw metrics only
    ↓
evaluate_endpoint_evidence(evidence, policy)      # sole scientific authority
    ↓
EndpointValidationResult                         # exact frozen structure
```

Collector constraints:

- read each structure once per validation;
- preserve existing POSCAR compatibility and ASE connectivity semantics;
- return raw mapping, bond-change, displacement, and site evidence;
- define no status, score, reason, or priority branch;
- perform no write or persistence.

Evaluator constraints:

- remain owned by `modules.ts_endpoint_validator`;
- preserve the exact four statuses;
- preserve errors, warnings, lexical ordering, `reasons=errors+warnings`, and
  score values;
- preserve threshold loading/override order and existing numeric behavior;
- preserve all current edge-case outputs, including known gaps, unless a
  separate scientific-change task is authorized.

## Compatibility gates

Phase 3B acceptance must compare old and new results for every behavior sample
in `TS_ENDPOINT_BEHAVIOR_BASELINE.md`:

- complete dataclass equality;
- exact status, reason content/order, score, threshold version and overrides;
- exact atom/bond/site list ordering;
- identical exceptions for malformed inputs;
- generator selection and assessment order;
- manager validator-before-persistence behavior;
- zero database or migration effect.

No sample may be normalized except temporary absolute paths.

## Deferred work

### Separate scientific correction task

Requires explicit scientific authorization and new expected outputs:

- reject or review unphysical atom contacts independently of connectivity;
- detect adsorbate desorption without COM-vector cancellation;
- validate required reaction identity fields;
- define geometry-backed adsorption-site validity.

These are not refactor changes.

### Migration/database task

Requires closing `MIGRATION_REVISION_BACKLOG.md` first:

- integrate an exact schema fingerprint and version chain;
- add safe transactional migration;
- prohibit destructive non-empty rollback by default;
- only then consider moving the migration runner out of the adapter.

### Low-value changes not recommended

- renaming `TSEndpointGenerator`;
- moving dataclasses solely for aesthetics;
- splitting the 170-line generator or 261-line manager;
- merging connectivity-gate configuration into endpoint validation;
- adding an endpoint CLI before a real caller is authorized.

## Expected Phase 3B conclusion

Phase 3B should pass only if all frozen behavior is identical, the validator
remains the sole scientific authority, the import graph stays acyclic, and no
migration/database/configuration/execution behavior changes.
