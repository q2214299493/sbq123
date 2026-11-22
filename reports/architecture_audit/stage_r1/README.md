---
document_class: HISTORICAL_SNAPSHOT
as_of: '2026-11-22T00:00:00+08:00'
as_of_scope: Stage R.1 audit date in Asia/Shanghai
source_scope: SBQ123 publication source and archived evidence, focused offline Windows verification
source_version: 335008915ebcb227cc5012054df105a2e0ac4404
source_version_role: Requested production-code audit baseline
source_branch: codex/multiphase-phase0-integration
published_evidence_checkpoint: dd3a5cbbd180c97fe09a0554a6ef2a845ef95f73
evidence_kind: HISTORICAL
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Stage R.1 · SBQ123 architecture and technical debt audit

Audited on 2026-11-22 (Asia/Shanghai) against production code baseline `335008915ebcb227cc5012054df105a2e0ac4404`. Published evidence checkpoint `dd3a5cbbd180c97fe09a0554a6ef2a845ef95f73`.

## Decision

Keep the existing modular direction and V2.1 rate exchange. Before using the network-bound rate validator as the input gate for an external consumer, require it to validate reaction identity, parameter membership, direction and stoichiometry against the bound network. Local probes demonstrated that the current API and CLI accept altered copies of all three tested fields with an unchanged network and its correct SHA-256. The native adapter output builder already checks some of these relationships internally. [Scientific data architecture](scientific-data.md) · [Debt register](technical-debt.md)

CATKINAS and Zacros have separate native specifications, executables and scientific prerequisites. Their input dispatcher still imports both implementations for either selection. Preserve separate adapter ownership, make that selection lazy and engine-local, and keep comparisons conditional. Archived closed-cycle CATKINAS and seeded/restart Zacros runs support bounded synthetic capabilities. CATKINAS unequal-capacity bridge normalization is unverified. The Zacros oxide control failed in the simulation reader before lattice or mechanism load, despite exit code zero. The archived permission was consumed. [Engine and stage review](engines-and-stages.md)

The core can express catalyst-independent structural identities, footprints and cross-phase reaction contracts. Native representability remains topology- and evidence-specific. Reactor is an optional documented boundary. The scientific-priority tool ranks atomistic acquisition, and the adaptive engine-selection ADR specifies a future route. This checkpoint found no implemented general SPC engine dispatcher or Reactor balance solver. [Target architecture and extensibility](target-architecture.md)

## Deliverables

| Deliverable | Report |
| --- | --- |
| Repository and major-module ownership, dependency graph, and code quality | [Architecture map](architecture.md) · [Baseline Python inventory and file-level dependency edges](python-inventory.csv) |
| Material through reactor scientific data ownership and duplicate implementation inventory | [Scientific data architecture](scientific-data.md) |
| Engine independence, native capabilities, implementation and fixtures for Stage A and B | [Engine and stage review](engines-and-stages.md) |
| Baseline reconciliation, tests, governance, review queue and exact limitations | [Verification and governance](verification.md) · [57 existing State Handoff review IDs and choices](pending-state-reviews.csv) |
| P0–P3 defects, design recommendations and ordered minimal repair plan | [Technical debt register](technical-debt.md) |
| Target boundaries and Fe5C2, Ni/CeO2 and Pt/TiO2 case walkthroughs | [Target architecture and extensibility](target-architecture.md) |

## Verification in brief

The AST inventory covers all 522 tracked baseline Python files under `scripts/`, `modules/`, `configs/` and `tests/`. Two independent invocations of selected offline suites recorded **723 passed / 8 skipped** and **166 passed / 1 skipped** on Windows with Python 3.13.9. The skipped cases were native launches. Repository-state audit identified one pre-existing projection drift and 81 worktree review notices. The audit commit is limited to this report directory. [Exact scope and commands](verification.md)
