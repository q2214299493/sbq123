# TS Endpoint Refactored Architecture

Date: 2026-07-27
Phase: 3B implementation

## Scope decision

`PHASE_3B_IMPLEMENTATION_PLAN.md` is the highest implementation authority for
this phase. It explicitly limits production changes to a non-judgmental
evidence collector and the validator delegation needed to use it. Therefore:

- `modules/ts_endpoint_evidence.py` was added;
- `modules/ts_endpoint_validator.py` was adapted;
- generator, manager, database adapter, configuration, SQL, and migration
  runner were not changed;
- no general endpoint service was added.

This is a responsibility extraction, not a four-module rewrite.

## Current call graph

```text
StructurePurposeManager
    -> TSEndpointGenerator
        -> TSEndpointValidator
            -> ts_endpoint_evidence
    -> TSEndpointDatabase (only after generation/validation succeeds)
```

The endpoint-module dependency graph is acyclic:

```text
structure_purpose_manager -> ts_endpoint_generator -> ts_endpoint_validator
                          \-> ts_endpoint_database
ts_endpoint_validator     -> ts_endpoint_evidence
```

## Responsibility boundaries

### Endpoint evidence collector

Authority: `modules.ts_endpoint_evidence`

Responsibilities:

- load the initial and endpoint POSCAR representations;
- calculate raw per-atom displacement vectors and magnitudes;
- calculate the existing mass-weighted adsorbate COM displacement metric;
- calculate sorted initial and endpoint ASE connectivity edges;
- return immutable raw evidence objects.

It defines no status, threshold, score, reason code, priority, routing decision,
or persistence behavior. It has no manager, database, CLI, execution-gate, or
scheduler dependency and performs no write.

Each POSCAR is parsed once by the POSCAR parser and each structure is loaded
once by the ASE loader per successful validation. This removes the prior
duplicate ASE load of the initial structure.

### Endpoint validator

Scientific authority: `modules.ts_endpoint_validator.TSEndpointValidator.validate`

Responsibilities retained:

- load the existing threshold policy and apply its existing override order;
- preflight structure compatibility and atom mapping;
- interpret raw displacement and connectivity evidence;
- derive observed, missing, unexpected, and site-coordination bond changes;
- apply the existing scientific status and priority branches;
- construct errors, warnings, reasons, score, metrics, and the frozen result.

The validator does not route purpose, write database records, choose workflow
actions, call `sys.exit`, or convert exceptions into default success.

### Endpoint generator

Compatibility authority: `modules.ts_endpoint_generator`

The module is unchanged. Its historical public `generate()` entry remains a
candidate-selection facade: it builds validation requests, delegates every
scientific classification to `TSEndpointValidator`, applies the frozen
candidate reuse/selection ordering, and returns the existing dataclasses.

It contains no connectivity calculation, threshold loading, metric
calculation, file copy, database write, or independent reason-code generation.
The validator call remains intentionally inside this facade because moving it
to the manager would change the frozen public API and selection behavior and
is expressly excluded by the implementation plan.

### Structure purpose manager

Compatibility authority: `modules.structure_purpose_manager`

The module is unchanged. It:

- resolves purpose through the existing configuration;
- delegates TS candidate work to the generator;
- persists only after the generator/validator path succeeds;
- delegates stable and legacy paths to their existing adapters;
- returns the existing workflow result.

It does not calculate endpoint connectivity, displacements, scientific status,
or reason codes. Validator rejection and exceptions stop the path before
persistence.

### Endpoint database adapter

Persistence authority: `modules.ts_endpoint_database`

The module is unchanged. It owns:

- connection and transaction scope;
- deterministic JSON serialization;
- insert, duplicate handling, query, row decoding, and rollback behavior;
- record-integrity checks for required fields, paths, and supported stored
  status strings.

The supported-status check is data-model integrity, not scientific
re-evaluation. The adapter imports or calls neither generator nor validator,
does not inspect structures, and does not run migrations.

## Data boundary

The compatible data flow remains:

```text
TSEndpointGenerationRequest
    -> EndpointCandidate assessments
    -> EndpointValidationRequest
    -> EndpointGeometryEvidence (internal raw evidence)
    -> EndpointValidationResult
    -> GeneratedTSEndpoint
    -> StructureSelectionResult
    -> TSEndpointRecord (optional)
```

No public object, field, signature, import path, status, reason-code ordering,
or serialized database field was changed. The two new evidence dataclasses are
internal additive types and are not substituted for public result types.

## Explicitly deferred

The frozen close-contact, sampled desorption, and empty-reaction-identity gaps
remain unchanged. Blocked endpoint migrations remain blocked and unexecuted.
No endpoint CLI, generic service, Schema change, or scientific correction was
introduced.
