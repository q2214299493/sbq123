# Final Architecture

Date: 2026-07-27

This document is the additive final architecture description. Historical
architecture and Review Baseline files remain unchanged except for a pointer
from `ARCHITECTURE.md`.

## Final directory tree

```text
work/
|-- tasks/                 current executable step and backlog
|-- docs/                  method, state, decisions, validation, handoff
|-- configs/               routing, schemas, thresholds, backend contracts
|-- modules/               scientific ownership and endpoint adapters
|-- scripts/               CLIs, workflows, evaluators, evidence, executors
|-- skills/                repository-backed reusable scientific tooling
|-- tests/                 behavior, API, structure, and safety contracts
|-- artifacts/             additive review/release manifests
|-- calculations/          calculation inputs/evidence/runtime (not release source)
|-- data/                  real registry and backups (not release source)
|-- outputs/, reports/     generated deliverables (not release source)
`-- archive/               historical or superseded material
```

## Module responsibility table

| Layer/module | Responsibility | Must not do |
|---|---|---|
| `scripts.ts_strategy_engine.cli` | parse and present unified TS commands | submit, duplicate science, invent defaults |
| `scripts.ts_strategy_engine.workflow` | order validated planning/analysis steps | reimplement evaluators or authorize actions |
| `scripts.ts_strategy_engine.execution_gate` | sole action authorization and decision validation | run scheduler commands |
| `scripts.neb_agent.path_quality_control` | collect/evaluate path-quality scientific evidence | authorize execution |
| `scripts.neb_agent.path_quality_service` | shared application orchestration/report construction | define thresholds/status/reason policy |
| `modules.ts_endpoint_evidence` | read-only raw endpoint evidence | create scientific status/reason codes |
| `modules.ts_endpoint_validator` | sole endpoint science aggregation | route workflow or write DB |
| `modules.ts_endpoint_generator` | candidate assessment/generation result | persist or create a second validator |
| `modules.structure_purpose_manager` | purpose/generation/validation/persistence orchestration | recompute science |
| `modules.ts_endpoint_database` | record validation, transaction, query, serialization | migrate implicitly or judge chemistry |
| `scripts.artifact_io` | atomic JSON/hash primitives | merge concurrent domain records |
| scheduler/submission adapters | query evidence and gate-enforced action execution | treat unknown/timeout as success |

## Authority and dependency direction

```text
machine-readable config / schema
        |
        v
CLI adapters -> workflow / application orchestration -> scientific evaluators
        |                         |                           |
        |                         v                           v
        +-----------------> evidence / artifacts ------> execution gate
                                      |                      |
                                      v                      v
                             registry adapters       guarded executors
```

Dependencies flow inward from CLI and workflow layers. Scientific evaluators do
not import CLI, scheduler, submission, or database adapters. Persistence and
execution boundaries do not recreate scientific conclusions.

Forbidden reverse dependencies:

- evidence/evaluator modules must not import CLI, manager, scheduler, submission,
  or database adapters;
- database adapters must not import generator/validator or execution modules;
- pure decision construction must not import the execution gate;
- CLI/workflow must not define local scientific thresholds or reason ordering;
- executors must not bypass `require_action`;
- no module may auto-run the endpoint migration at import/init time.

## Unique authorities

| Concern | Sole authority | Non-authoritative collaborators |
|---|---|---|
| NEB action authorization | `scripts.ts_strategy_engine.execution_gate` | parsers, monitors, workflow, strategy, path-quality service |
| Execution-decision document construction | `scripts.ts_strategy_engine.execution_decision` | called by the gate; no I/O or authority |
| NEB path-quality science | `scripts.neb_agent.path_quality_control.evaluate_quality` | collector/service/CLI/workflow/pilot adapters |
| TS endpoint scientific validation | `modules.ts_endpoint_validator.TSEndpointValidator` | read-only evidence collector, generator, purpose manager, DB adapter |
| Atomic JSON state write | `scripts.artifact_io` | domain callers |
| Registry connection/transaction | `scripts.ts_strategy_engine.registry` | domain record adapters |
| NEB submission/stop enforcement | `scripts.neb_agent.submission` | scheduler evidence and gate decision |

## NEB path-quality flow

```text
files / monitor evidence
  -> collector
  -> path_quality_service (input/config/report orchestration)
  -> path_quality_control.evaluate_quality (science)
  -> CLI | unified workflow | pilot adapter
  -> execution_gate (authorization)
  -> submission executor (enforcement)
```

The service owns no scientific threshold, status priority, reason-code rule, or
execution authority. All entry points preserve the evaluator's scientific
fields and ordering.

## TS endpoint flow

```text
generation request + candidate structures
  -> TSEndpointGenerator
  -> ts_endpoint_evidence (raw, read-only geometry evidence)
  -> TSEndpointValidator (status, metrics, reasons)
  -> StructurePurposeManager (purpose/routing orchestration)
  -> TSEndpointDatabase (optional transaction/serialization)
```

The generator ranks candidates using the validator result but does not define a
second scientific status system. The manager does not recompute validation.
The database adapter validates record shape and allowed enum values, not
scientific validity. It requires the endpoint table and never implicitly
migrates or creates it.

## Side-effect boundaries

- CLI and workflow modules may write only their documented outputs.
- State/report JSON uses atomic same-directory replacement.
- SQLite writes are transaction-bound and rollback on exception.
- External commands require finite timeout, captured context, and explicit
  success checks.
- Scheduler state, electronic convergence, ionic/force convergence, geometry
  validity, and scientific validity remain separate facts.
- Dry-run/preflight is evidence generation, never submission authority.

## Compatibility boundaries

Legacy imports remain intentional facades:

- `execution_gate` re-exports the historical constants/builders required by
  existing callers while action authority remains there.
- `path_quality_control` and `path_quality_cli` module paths remain stable.
- generator, validator, purpose-manager, and endpoint-database public names
  remain at their Phase 3A paths.
- `scripts.aqcat25_ts_active_learning` remains a wrapper for the unified CLI.

These facades may be removed only by a separately versioned migration with
caller inventory and compatibility tests.

## Database and migration boundary

`modules/calculation_registry/migrations/001_ts_endpoint_records.sql` and its
rollback are formal, revised, review-only assets. Direct SQL execution and
non-empty rollback are prohibited; real-database application requires separate
path-specific authorization. They remain outside the core registry schema
version and were exercised only through the guarded API on temporary SQLite.

## Release-baseline boundary

The final release baseline includes production source, tests and fixtures,
configuration, governance, blocked migrations, and documentation. It excludes
calculation directories, outputs, scheduler/runtime state, databases, caches,
archives, credentials, and generated scientific results. It is additive and
does not rewrite Review Baseline v1, v2, or v3.
