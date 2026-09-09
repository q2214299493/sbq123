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

# Fe Convergence Baseline

## Purpose

Preserve the valid alpha-Fe bulk convergence baseline.

The package contains conventional bcc alpha-Fe bulk inputs and evidence: 2 Fe
atoms with `a = 2.8665 A`.

## Accepted Parameter Branches

| System and purpose | ENCUT | Gamma mesh | Smearing | Structural model |
|---|---:|---|---|---|
| alpha-Fe relaxation | 400 eV | 15x15x15 | `ISMEAR=1`, `SIGMA=0.10 eV` | conventional bcc, relax cell and ions |
| alpha-Fe final static | 400 eV | 15x15x15 | `ISMEAR=-5` | same accepted bulk geometry |

## Layout

- `systems/`: curated POSCAR, INCAR, and KPOINTS files.
- `evidence/`: copied raw convergence summaries plus the accepted-selection summary.
- `manifest.json`: machine-readable systems, parameters, hashes, source paths, and limitations.
- `PROVENANCE.md`: retrieval and source record, including external `POTCAR` metadata.
- `validate_baseline.py`: standard-library validation of alpha-Fe structure,
  settings, evidence, and forbidden files.

Run the local validation from the repository root:

```powershell
python modules/fe_convergence_baseline/validate_baseline.py
```

The licensed Fe PAW-PBE `POTCAR` is intentionally absent. Create it at calculation time from the approved server-side potential and verify the SHA-256 recorded in `manifest.json`.

## Scientific Limitation

This module no longer stores the old Fe110-labeled surface branch. Corrected
true Fe(110) convergence and production inputs are owned by
`modules/convergence_workflow/`.

## Done Criteria

Alpha-Fe remains reproducible and no old Fe110-labeled surface branch remains
in this module.
