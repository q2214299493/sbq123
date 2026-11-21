---
document_class: CURRENT_AUTHORITY
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: CURRENT_CODE_STATE_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Current State

## Authority and scope

This is a source/publication entry point, not a live monitoring report. Governance
is defined in [DOCUMENT_GOVERNANCE.md](DOCUMENT_GOVERNANCE.md). The development
checkout is `C:/Users/86177/Desktop/work`; this branch is an isolated publication
worktree based on B5. No scheduler or production database was queried in B6.

## Active Scientific Branch

The selected protocol is the corrected true Fe(110) five-layer branch,
`true_fe110_5layer_5x5x1`, as recorded in
[method protocol](01_METHOD_PROTOCOL.md) and
[production profile](../configs/true_fe110_production.yaml).
Compatible final OUTCAR TOTEN uses the existing
`fe110_converged_toten_sigma0p20_v1` convention. No thresholds or parameters
were changed. Source configuration establishes the selected method, not a newly
completed calculation or a deployment observation.

## Implemented software and registry scope

CURRENT_CODE_STATE: B1-B5 implementations and 1054 passing software tests at B5
are recorded in the [B5 report](../reports/refactor_audit/B5_completion_report.md).
Execution gates, VASP/contract parsing, evidence/data gates and registry lifecycle
remain separate authorities. [Module status](06_MODULE_MAP.md) owns status;
[derived readiness](../reports/capability_readiness.md) does not own it.
SUPPORTED_CODE_SCHEMA: 9, from [registry schema code](../scripts/registry_schema.py).
production_schema_version: NOT_VERIFIED_IN_B6. HISTORICAL_SCHEMA: version 8
statements and counts are preserved in the chronology, not a deployment claim.

## Latest recorded scientific/workflow gate

LAST_RECORDED_OBSERVATION: the B5 module map records Dimer `9746548` after
ordinary NEB `9745217` review. Last recorded scheduler status: PEND;
observed_at: 2026-09-07T11:15:50Z; source: [module map](06_MODULE_MAP.md).
This is later than the retained managed snapshot below; neither is live evidence.
The [task projection](../tasks/current_task.md) is also a recorded snapshot and
must be reconciled against the development task before any new scientific action.

## Explicitly not established

PRODUCTION_UNVERIFIED: present queue state, production schema/deployment and
current evidence availability. PREDICTION_ONLY: GPU/ML candidates do not establish
accepted TSs, barriers or final adsorption minima. SCIENTIFICALLY_ACCEPTED labels
in older records describe their original reviewed scope only; B6 did not revalidate
them. Software test success does not establish scientific or production readiness.
Planned/Blocked kinetic modules remain as listed in the module map.

## History and provenance

The [preserved chronology](history/current_state_chronology_before_B6_20260909.md)
contains the former long sections, including the UTF-8 C/C2/O site labels.
The earlier [TS history](history/active_fe110_co_dissociation_history_through_20260803.md)
remains canonical for its original period. Root FINAL/PHASE reports are classified
historical snapshots; filenames do not establish authority or freshness.

## Active Transition-State Gate

LAST_RECORDED_OBSERVATION: retained state-manager projection, dated 2026-08-27
(local document date; no exact observation time supplied). This historical managed
block is preserved verbatim for projection compatibility, not selected as the
latest observation. Its scientific claims are not revalidated in B6.

<!-- state-handoff:start active-fe-110-co-dissociation-test-current-gate -->
### Active Gate - 2026-08-27 GPU Job 1327 Failed; Revised Path Design Required

- Held-out VASP jobs `9731537`-`9731543` are `DONE` and quality-passed; frozen MatRIS passed the six-structure primary held-out gate, while AQCat25 remains a force/geometry auditor.
- MZ73 job `1327` produced exit code `1` during restrained preconditioning step `9`, before ordinary MatRIS ML-NEB and before the AQCat25 fixed-path audit.
- The required forming O-H `1.1-1.8 A` coverage fell from five to two internal images; at least three were required, so the geometry guard correctly stopped the run.
- O-H monotonicity, C1-C2 preservation, adjacent RMSD, maximum movable-atom step, minimum pair distance, and periodic-branch checks still passed.
- No complete GPU path, Dimer parent, VASP result, TS, barrier, fine-tuning, automatic retry, or resubmission exists.
- The completed seven-job VASP batch remains accepted held-out evidence; job `1327` is a separate failed GPU path attempt and does not invalidate that batch.

Next action: Prepare and review a revised preconditioning or resampling design that preserves at least three O-H interval images; require new explicit authorization before any rerun.
<!-- state-handoff:end active-fe-110-co-dissociation-test-current-gate -->
