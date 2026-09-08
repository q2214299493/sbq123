# Module Interface Contract

Every module reads existing data, writes a new artifact, reports explicit
errors, and logs through the `vasp2kinetics` logger. No module silently fills
missing scientific values.

| Module | Input | Output | Explicit failure examples | Log destination |
| --- | --- | --- | --- | --- |
| VASP parser | Existing VASP/NEB directory | `vasp_result.json` | `VASP_CASE_NOT_FOUND`, `OUTCAR_NOT_FOUND`, incomplete NEB image | `logging.phase_files.parser` |
| Kinetic builder | `vasp_result.json`, human `reaction.yaml` | Typed record in `kinetic_dataset.json` | invalid JSON/YAML, unsupported reaction field, duplicate ID | `logging.file` |
| Kinetic parameter handoff | Reviewed handoff JSON, bound dataset and evidence files | Validation result only; no dataset mutation | schema error, non-finite value, energy identity/hash/evidence mismatch | stdout from standalone module |
| Validator | `kinetic_dataset.json` | `validation_report.json` | missing source, imbalance, inconsistent energy relation, unconverged VASP | `logging.file` |
| CATKINAS adapter | Dataset and matching validation report | Static adapter project and `generation_report.json` | failed validation, missing activation energy | `logging.file` |
| Zacros adapter | Dataset, validation report, human `surface.yaml` | Static adapter project and `generation_report.json` | missing/invalid site, failed validation, missing barrier | `logging.file` |
| Simulation runner | Existing generated project, configured command | raw stdout/stderr, `run_status.json`, execution history | executable/input missing, timeout, nonzero return | `logging.phase_files.simulation` |
| Result parser | Existing simulator output and mapping | `simulation_result.json`, `parser_log.json` | directory/file missing, invalid numeric text, unmapped ID | `logging.phase_files.parser` |
| Analysis/report | `simulation_result.json` | `analysis_result.json`, `report.md` | invalid JSON/schema, missing template token | `logging.phase_files.parser` |
| Workflow | Case directory and case-local `config.yaml` | per-case artifacts and `workflow_state.json` | first failed phase, interrupted running step, invalid state | `logging.phase_files.workflow` |

## Status semantics

- Parser statuses describe file availability and parse completeness only.
- Validation statuses describe the implemented checks only.
- Runner `SUCCESS` means process return code zero only.
- Workflow `SUCCESS` means all seven existing modules returned success.
- None of these statuses independently establish scientific validity beyond
  the owning module's explicit checks.
