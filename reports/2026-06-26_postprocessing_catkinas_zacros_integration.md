# CATKINAS and Zacros 4.0 Post-Processing Integration

Date: 2026-06-26 Asia/Shanghai

## Local Files Found

CATKINAS:

- Path: `C:/Users/86177/Desktop/app/CATKINAS`
- Found files: `CATKINAS.p`, `ReadMe.m`, `README_DEPLOYMENT.md`, `quickstart/`, and `examples/`
- Local notes: CATKINAS runs inside MATLAB; MATLAB executable discovery is **Needs confirmation**.

Zacros 4.0:

- Path: `D:/Zacros4.0`
- Shell entry: `D:/Zacros4.0/Zacros_Shell.cmd`
- Executable: `D:/Zacros4.0/bin/Zacros.exe`
- Manual: `D:/Zacros4.0/manual/ZacrosManual.pdf`
- Work path: `D:/Zacros4.0/work`

## Workflow Placement

CATKINAS is now the preferred local post-processing tool for:

- `modules/baseline_mkm/`: baseline mean-field MKM
- `modules/coverage_mkm/`: coverage-dependent MKM scans or iteration, when justified

Zacros 4.0 is now the preferred local engine for:

- `modules/surface_kmc/`: surface-reaction KMC

Both tools are downstream consumers only. They must consume validated kinetic-data and reaction-network records, and they cannot bypass TS validation, thermochemistry, provenance, or scientific review.

## Files Updated

- `configs/postprocessing_software.yaml`
- `docs/01_METHOD_PROTOCOL.md`
- `modules/kinetic_data/README.md`
- `modules/baseline_mkm/README.md`
- `modules/coverage_mkm/README.md`
- `modules/surface_kmc/README.md`
- `docs/12_WORKFLOW_ARCHITECTURE.md`
- `docs/06_MODULE_MAP.md`
- `docs/02_CURRENT_STATE.md`
- `docs/03_DECISIONS_LOG.md`
- `docs/04_ERROR_LOG.md`
- `docs/05_FILE_INDEX.md`
- `tasks/backlog.md`

## Remaining Work

- Confirm MATLAB executable path and run a CATKINAS quickstart smoke test.
- Run or inspect a copied Zacros 4.0 example without treating example output as project science.
- Build traceable CATKINAS input/export templates from validated kinetic records.
- Build traceable Zacros input/export templates from validated lattice/site/event/rate records.
- Populate the calculation registry before any post-processing result is accepted.

## Decision

The tools are integrated into the repository workflow, but the scientific modules remain blocked until validated DFT, TS, thermochemistry, reaction-network, and kinetic-data inputs exist.
