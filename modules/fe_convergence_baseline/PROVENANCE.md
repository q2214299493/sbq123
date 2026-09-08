# Provenance

## Retrieval

- Retrieval date: `2026-06-23` (Asia/Shanghai).
- Remote host: `sunboquan-codex`.
- Alpha-Fe source: `~/sbq/agent/jobs/convergence/fe_bulk_fe110_slab_20260618/alpha_fe_bulk/reference/POSCAR`.
- The alpha-Fe structure was copied without coordinate, lattice, or atom-order
  edits.

## Evidence Sources

- ENCUT and k-mesh CSV files were copied from `modules/memory_migration/inputs/MM-002_evidence/`.
- Alpha-Fe smearing data were copied from `reports/2026-06-23_alpha_fe_bulk_smearing_summary.csv`.
- Accepted parameter interpretations come from `docs/01_METHOD_PROTOCOL.md`
  and current project-state files.
- Alpha-Fe smearing jobs `9542651-9542658` were recorded as `DONE` and normally
  finished. Job IDs for the earlier ENCUT/k-mesh sweeps are not present in the
  curated evidence and remain `Needs confirmation`.

## Licensed External Input

`POTCAR` is not stored in this repository. The alpha-Fe reference used:

- `TITEL = PAW_PBE Fe 06Sep2000`
- size: `238259` bytes
- SHA-256: `cd5a22d9368cc8b5cc476bea79732366149640da08ac9009b0e1b7fc627eea28`
- recorded remote modification time: `2010-03-02 19:57:10 +0800`

The VASP executable version used for the historical alpha-Fe sweeps is `Needs
confirmation`. This missing metadata does not change the stored numerical
results, but it must be resolved before claiming a complete calculation
registry record.
