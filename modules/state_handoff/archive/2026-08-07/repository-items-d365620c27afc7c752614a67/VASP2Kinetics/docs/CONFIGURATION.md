# Configuration Reference

`config.yaml` is required and is loaded strictly. Relative paths use the
selected project root; workflow case configurations use the case directory.

| Section | Required fields | Purpose |
| --- | --- | --- |
| `project` | `name`, `version` | Application identity |
| `paths` | `data_path`, `output_path`, `raw_vasp_cases`, `processed_data` | Shared data/output roots |
| `logging` | `level`, `console`, `file`, `phase_files` | General and phase-specific logs |
| `logging.phase_files` | `parser`, `simulation`, `workflow` | Dedicated timestamped logs |
| `validator` | `energy_tolerance`, `allowed_elements` | Existing validation thresholds |
| `catkinas` | `input_path`, `output_path`, `allow_warning` | CATKINAS adapter settings |
| `zacros` | `surface_config`, `output_path`, `allow_warning` | Zacros adapter settings |
| `simulation` | two commands, `timeout` | Shell-free external execution |
| `analysis` | `result_path`, `output_path` | Simulation-result parsing paths |
| `report` | `output_path`, `template_path` | Phase 9 report files |
| `workflow` | `software`, `output_root` | Explicit backend and per-case output root |

Commands containing arguments must be YAML string lists. Paths and commands
are never interpolated by a shell. `workflow.software` must be exactly
`CATKINAS` or `ZACROS`.

The canonical example is
`examples/Fe110_CO_dissociation/config.yaml`. Placeholder executable paths
must be replaced by the user; the program does not discover software.
