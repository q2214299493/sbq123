---
document_class: CURRENT_AUTHORITY
authority_model_id: document-governance-v1
as_of: '2026-09-09T00:00:00+08:00'
source_scope: B6 governance of the B5 publication baseline; no live scientific sources
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: CURRENT_CODE_STATE
owners:
  scientific_method: docs/01_METHOD_PROTOCOL.md
  scientific_branch: configs/true_fe110_production.yaml
  current_state: docs/02_CURRENT_STATE.md
  module_status: docs/06_MODULE_MAP.md
  current_task: tasks/current_task.md
  backlog: tasks/backlog.md
  execution_backends: configs/execution_backends.yaml
  scientific_thresholds:
  - configs/neb_agent/default_thresholds.yaml
  - configs/neb_path_quality_control_v2.yaml
  - docs/10_TS_VALIDATION_PROTOCOL.md
  registry_code_schema: scripts/registry_schema.py
  production_schema: NOT_VERIFIED_IN_B6
  scientific_provenance: docs/11_DATA_PROVENANCE_PROTOCOL.md
  endpoint_constraints: AGENT_RULE_TS_ENDPOINT.md
  agent_rules: AGENTS.md
  submission_recovery: SUBMISSION_RECOVERY.md
  data_classification: configs/data_governance.yaml
report_authority: NONE; generated and historical reports are scoped evidence, not
  state owners
preserved_authority_documents: [AGENTS.md, AGENT_RULE_TS_ENDPOINT.md, SUBMISSION_RECOVERY.md]
preserved_historical_documents: [ARCHITECTURE.md, BASELINE_INTEGRITY_REPORT.md, CHANGESET_MANIFEST.md, CLEAN_CHECKOUT_VERIFICATION.md, CONDITION_CLOSURE_REPORT.md,
  DEPRECATED_CODE.md, E_SOURCE_ARCHITECTURE.md, FINAL_API_COMPATIBILITY_REPORT.md, FINAL_ARCHITECTURE.md, FINAL_AUDIT_CLOSURE_MATRIX.md,
  FINAL_BACKLOG.md, FINAL_BEHAVIOR_COMPATIBILITY_REPORT.md, FINAL_CHANGESET_MANIFEST.md, FINAL_CODE_QUALITY_AUDIT.md, FINAL_COMMIT_PLAN.md,
  FINAL_REFACTOR_REPORT.md, FINAL_STAGING_PLAN.md, FINAL_VERIFICATION_REPORT.md, GOVERNANCE_DOCUMENT_DECISION.md, MIGRATION_REVIEW.md,
  MIGRATION_REVISION_BACKLOG.md, NEB_PATH_QUALITY_ARCHITECTURE.md, PHASE_2A1_CLOSURE_REPORT.md, PHASE_2A_REPORT.md, PHASE_2B_BEHAVIOR_BASELINE.md,
  PHASE_2B_BEHAVIOR_COMPATIBILITY.md, PHASE_2B_CHANGESET_MANIFEST.md, PHASE_2B_DIFF_REVIEW.md, PHASE_2B_ENTRY_EQUIVALENCE_REPORT.md,
  PHASE_2B_IMPLEMENTATION_REPORT.md, PHASE_2B_PROPOSAL.md, PHASE_2B_VERIFICATION_REPORT.md, PHASE_2B_VERIFIED_CHANGESET.md,
  PHASE_3A_CHANGESET_MANIFEST.md, PHASE_3A_REPORT.md, PHASE_3B_BEHAVIOR_COMPATIBILITY.md, PHASE_3B_BEHAVIOR_VERIFICATION.md,
  PHASE_3B_CHANGESET_MANIFEST.md, PHASE_3B_DIFF_REVIEW.md, PHASE_3B_IMPLEMENTATION_PLAN.md, PHASE_3B_IMPLEMENTATION_REPORT.md,
  PHASE_3B_PRECHANGE_SNAPSHOT.md, PHASE_3B_VERIFICATION_REPORT.md, PHASE_3B_VERIFIED_CHANGESET.md, PROJECT_AUDIT.md, REFACTOR_CHANGESET.md,
  REFACTOR_PLAN.md, REFACTOR_REPORT.md, REVIEW_BASELINE_V2.md, REVIEW_BASELINE_V3.md, SOURCE_BASELINE_PLAN.md, SOURCE_PROVENANCE_REPORT.md,
  TS_ENDPOINT_API_CONTRACT.md, TS_ENDPOINT_BEHAVIOR_BASELINE.md, TS_ENDPOINT_CURRENT_ARCHITECTURE.md, TS_ENDPOINT_DUPLICATION_AUDIT.md,
  TS_ENDPOINT_FROZEN_ISSUES.md, TS_ENDPOINT_ISSUE_CLOSURE_REPORT.md, TS_ENDPOINT_REFACTORED_ARCHITECTURE.md, UNTRACKED_FILE_INVENTORY.md,
  VERIFICATION_REPORT.md]
---

# Document Governance

This is the one documentation-authority model. Its metadata names owners; the
[data policy](../configs/data_governance.yaml) classifies data, not scientific status.

## Authority hierarchy

1. Approved scientific protocols and validated machine-readable configuration/code
   own their respective method, threshold, backend and supported-schema facts.
   Code/config does not silently override a locked scientific protocol; conflicts
   require owning-module review. `AGENT_RULE_TS_ENDPOINT.md` remains an applicable
   scoped constraint under the existing scientific protocols.
2. [Current state](02_CURRENT_STATE.md), [module status](06_MODULE_MAP.md) and task
   projections summarize identified sources, dates and scope; they do not override
   current evidence files. Only the module map owns module status.
3. Module READMEs describe contracts, inputs, outputs and done criteria, with
   historical observations labelled. A file or passing test does not promote status.
4. Generated capability/audit reports are DERIVED views bound to source hashes and
   a code base; they never establish live production or accepted scientific state.
5. Historical reports preserve earlier conclusions within their original scope.
   FINAL, CURRENT, CLOSURE, VERIFIED and PASS in filenames confer no freshness.

## Required interpretation

`as_of` identifies document review unless `as_of_scope` explicitly says otherwise.
Observation time must be separately recorded as `observed_at`, or NOT_RECORDED.
`source_scope` distinguishes development source, publication subset, local fixture,
recorded scientific evidence and live deployment. `source_version` here denotes
the B6 base; generated views additionally bind exact current input hashes.

- CURRENT_CODE_STATE: implemented software/configuration, not production deployment.
- LAST_RECORDED_OBSERVATION: source-dated snapshot, never a live scheduler query.
- HISTORICAL: preserved previous scope; no automatic current-authority selection.
- SCIENTIFICALLY_ACCEPTED: only a result accepted by its scientific owner, with
  bound evidence and scope. A document may report prior acceptance without renewing it.
- PREDICTION_ONLY: model candidates, predictions and inferred rankings are not
  accepted local calculations. Ranking PASS and tests cannot promote them.
- PRODUCTION_UNVERIFIED: deployment/database/queue state lacks current verification.

Supported code schema derives from `scripts.registry_schema.CURRENT_VERSION` (9).
`production_schema_version: NOT_VERIFIED_IN_B6` is mandatory until separately
reviewed local/live evidence establishes deployment. No database is opened by the
readiness generator or document checks. HISTORICAL_SCHEMA v8 observations remain
historical. Do not rewrite them as a migration to v9.

## Document classes and defaults

CURRENT_AUTHORITY requires both explicit classification and an owner in the model.
CURRENT_REFERENCE is guidance, not an independent state owner.
GENERATED_CURRENT_REPORT is DERIVED, source-bound and limited to its generation inputs.
HISTORICAL_SNAPSHOT and SUPERSEDED cannot supply current state.
UNKNOWN_REVIEW_REQUIRED is the default for unclassified or ambiguous documents.
Historical root reports stay at their canonical paths because code, tests, history
or external links may reference them; B6 records classification in this authority model without changing hash-bound file bytes or rewriting
scientific conclusions. The chronology formerly in current state has one canonical
[history file](history/current_state_chronology_before_B6_20260909.md); its managed
block remains verbatim in the current-state projection for compatibility.

## Derived readiness

`scripts.generate_capability_readiness` reads only this model, the module map,
explicit maturity annotations in that same map, schema source and referenced source
files. Missing dimensions remain unknown/unverified. Unit/integration tests describe
software behavior, never scientific validation. No second manually maintained status
table is allowed. Generation is deterministic, performs no registry/remote queries,
and writes only `reports/capability_readiness.{json,md}` under a chosen repository root.

## Checks and recovery

`scripts.document_governance` checks classification-aware wording and affected local
Markdown links. Historical wording is allowed. Missing evidence flags require
source review, not invented dates, confidence or scientific conclusions. Existing
unresolved internal links in unchanged historical prose are reported separately
rather than silently rewritten. Generated metadata is not scientific evidence;
B7 owns packaging/physical cleanup. The PKG-INFO classification mismatch does not
justify editing B4 state history or transaction behavior.
