# Project Structure

## Phase status

Phases 1 through 11 are implemented at the engineering-preview level. External
process execution, strict extraction, and neutral reporting remain isolated
from scientific interpretation.

```text
VASP2Kinetics/
|-- README.md
|-- LICENSE
|-- requirements.txt
|-- environment.yml
|-- config/
|   `-- config.yaml
|-- data/
|   |-- raw/vasp_cases/
|   `-- processed/
|-- docs/
|-- examples/Fe110_CO_dissociation/
|-- logs/
|-- schemas/
|   `-- kinetic_parameter_handoff.schema.json
|-- src/
|   |-- analysis/
|   |-- catkinas/
|   |-- kinetics/
|   |-- runner/
|   |-- vasp/
|   |-- workflow/
|   `-- zacros/
|-- tests/
`-- main.py
```

## Implemented responsibilities

- `src/config.py` and `src/config_sections.py`: strict YAML loading, section
  validation, and path resolution.
- `src/logging_config.py` and `src/logging_context.py`: consistent console,
  general-file, and phase-specific logging.
- `src/vasp/`: read-only OUTCAR, OSZICAR, and numeric NEB image parsing.
- `src/kinetics/schema.py`, `builder.py`, and `registry.py`: typed record
  construction and non-overwriting persistence.
- `src/kinetics/handoff.py` and `handoff_support.py`: standalone reviewed
  parameter-contract validation without dataset mutation or workflow import.
- `src/kinetics/validator.py` and `validation_structure.py`: independent
  structural, provenance, energy, barrier, VASP, and TS-information checks.
- `src/catkinas/`: validation-gated static CATKINAS adapter files.
- `src/zacros/`: validation-gated static Zacros adapter files using explicit
  human surface/site data.
- `src/runner/`: shell-free single-attempt process execution, raw streams,
  status, runtime, and history.
- `src/analysis/`: strict simulator-result parsing, deterministic numeric
  organization, and neutral JSON/Markdown reports.
- `src/workflow/`: ordered module dispatch, atomic state transitions, fail-fast
  stopping, pending-step restoration, and status inspection.
- `tests/`: unit, command-line, integration, failure, and recovery coverage.
- `docs/`: interface, configuration, reproducibility, TODO, review, test, and
  release contracts.

## Release artifacts

- `CODE_REVIEW.md`
- `IMPLEMENTATION_STATUS.md`
- `FINAL_TEST_REPORT.md`
- `PROJECT_RELEASE_REPORT.md`
- `docs/MODULE_INTERFACES.md`
- `docs/CONFIGURATION.md`
- `docs/REPRODUCIBILITY.md`
- `docs/TODO.md`
- `examples/Fe110_CO_dissociation/`

## Explicitly not implemented

- automatic promotion to `VALIDATED`;
- activation-energy calculation or missing-data estimation;
- executable native CATKINAS/Zacros models without authoritative schemas;
- CATKINAS native MAT-file decoding without a versioned variable contract;
- scientific interpretation, RDS identification, or catalyst ranking;
- automatic workflow repair, failed-step skipping, or interrupted-step retry;
- VASP/NEB execution or submission.

Missing data are reported with explicit states and errors. They are never
inferred or filled.
