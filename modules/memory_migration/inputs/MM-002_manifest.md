# MM-002 Input Manifest

- Batch: `MM-002`
- Status: `Completed`
- Completed: 2026-06-23
- Scope: adsorption energies, endpoint origins, alpha-Fe/Fe(110) convergence baselines, and extra clean-slab convergence summaries.

## Sources

1. `vasp-catalysis-workflow/references/adsorption.md`
2. Legacy memory convergence sections
3. Read-only remote OUTCAR/CONTCAR checks under `~/sbq/agent/jobs`
4. `modules/memory_migration/inputs/MM-002_evidence/`
5. Current endpoint geometry precheck in the active NEB directory

## Outcome

- Accepted historical records: 11
- Raw clean-slab and gas-CO reference OUTCAR paths: `Needs confirmation`
- Extra smearing/vacuum/thickness summaries preserved; no unsupported production choice inferred.
- Extracted notes: `modules/memory_migration/extracted/MM-002_extracted.md`
- Report: `modules/memory_migration/reports/MM-002_report.md`
