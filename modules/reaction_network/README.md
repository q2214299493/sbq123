---
document_class: CURRENT_REFERENCE
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: MODULE_CONTRACT_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Reaction Network

## Purpose

Assemble validated states and transition states into atom- and site-balanced elementary reactions.

## Required Inputs

- registered species and site definitions
- validated IS/FS pairs and Grade A TSs
- consistent reaction/free-energy and forward/reverse barrier data

## Outputs

- stoichiometric reaction table
- site-balance rules and reversibility
- source geometry and TS links
- consistency checks for atoms, sites, and thermodynamic cycles

## Done Criteria

Every elementary step balances atoms and sites, links source states/TSs, and passes forward/reverse thermodynamic consistency checks.
