# VASP2Kinetics

VASP2Kinetics is a transparent, auditable post-processing interface between
existing VASP/NEB calculations and kinetic-model inputs.

## Scientific objective

The project preserves a traceable path from existing electronic-structure
outputs to explicitly supplied kinetic records, simulator adapters, raw
simulation results, and neutral reports. It does not replace scientific review
or create missing kinetic parameters.

## Current status

Phases 1 through 11 are implemented at the engineering level:

- project structure
- YAML configuration loading and validation
- application logging
- base exceptions
- read-only OUTCAR, OSZICAR, and numeric NEB image parsing
- standardized `vasp_result.json` output
- typed `ReactionRecord` construction from `vasp_result.json` and human YAML
- non-overwriting `kinetic_dataset.json` registration
- standalone, versioned reviewed-parameter handoff schema with dataset/file
  hashes, units, method fingerprints, scientific gates, and manual approval
- read-only completeness, source, element-balance, energy-consistency, barrier,
  VASP-status, and TS-information checks
- independent `validation_report.json` output
- validation-gated static CATKINAS adapter package generation
- validation-gated static Zacros adapter package generation using an explicit,
  human-authored surface/site mapping
- single-attempt CATKINAS and Zacros external process management with raw
  stdout/stderr, status, runtime, and execution-history recording
- strict CATKINAS text-export and Zacros result parsing into one typed
  `simulation_result.json`, with separate parser diagnostics
- deterministic TOF, coverage, selectivity, and reaction-rate organization into
  `analysis_result.json`, plus a neutral Markdown report
- fail-fast orchestration with atomic per-step state persistence and read-only
  status inspection
- release-oriented structure, interface documentation, reproducible
  environments, example configuration, and quality reports

Catalytic-performance interpretation, mechanism/RDS judgement, and automatic
retry/tuning are not implemented. The generated report organizes existing
values only and does not provide scientific interpretation.

## Supported scope

The project will consume real calculation outputs and preserve their source
paths. It will not run VASP, modify structures, invent missing values, extend
reaction mechanisms, or replace scientific review.

## Not supported

- automatic reaction/mechanism discovery;
- AI prediction or missing-barrier estimation;
- VASP/NEB submission or repair;
- TS proof, RDS assignment, or catalyst ranking;
- automatic failed-step retry or input optimization;
- direct execution of static adapters when real software requires additional
  model-specific files.

## Requirements

- Python 3.10 or newer
- dependencies listed in `requirements.txt`

## Installation

Using `venv`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Or using Conda:

```powershell
conda env create -f environment.yml
conda activate vasp2kinetics
```

Verify the installation:

```powershell
python main.py --help
python -m unittest discover -s tests -v
```

## Input and output formats

Primary inputs are an existing VASP directory, human-authored reaction/surface
YAML, strict JSON artifacts from earlier phases, simulator output directories,
and a validated `config.yaml`. Primary outputs are `vasp_result.json`,
`kinetic_dataset.json`, `validation_report.json`, adapter directories,
`run_status.json`, `simulation_result.json`, `analysis_result.json`,
`report.md`, and `workflow_state.json`.

See [module interfaces](docs/MODULE_INTERFACES.md),
[configuration reference](docs/CONFIGURATION.md), and
[reproducibility checklist](docs/REPRODUCIBILITY.md).
Current release evidence is summarized in
[FINAL_TEST_REPORT.md](FINAL_TEST_REPORT.md) and
[PROJECT_RELEASE_REPORT.md](PROJECT_RELEASE_REPORT.md).

## Example

The [Fe(110) CO dissociation example](examples/Fe110_CO_dissociation/README.md)
contains reviewable YAML/configuration only. It deliberately has no fabricated
VASP or simulator result and demonstrates the expected fail-fast state until
real inputs are supplied.

## Usage

Use one action per command. Individual phase commands are documented below;
the unified case entry points are:

```powershell
python main.py --workflow --case examples/Fe110_CO_dissociation
python main.py --workflow-status --case examples/Fe110_CO_dissociation
```

Every workflow case loads its own `config.yaml`. The selected external command
is executed without a shell and only after all preceding steps succeed.

## Phase 2 parser

From this directory:

```powershell
python main.py --parse-vasp C:\path\to\existing\vasp_case
python -m unittest discover -s tests -v
```

The parser writes `data/processed/vasp_result.json`. It reads existing files
only and does not run VASP, calculate reaction quantities, or validate a
transition state.

See `PROJECT_STRUCTURE.md` for the directory contract, `TEST_REPORT.md` for
Phase 1 checks, `TEST_REPORT_PHASE2.md` for Phase 2 checks, and
`TEST_REPORT_PHASE3.md` for Phase 3 checks. Phase 4 checks are recorded in
`TEST_REPORT_PHASE4.md`, Phase 5 checks in `TEST_REPORT_PHASE5.md`, Phase 6
checks in `TEST_REPORT_PHASE6.md`, and Phase 7 checks in
`TEST_REPORT_PHASE7.md`. Phase 8 checks are in `TEST_REPORT_PHASE8.md`, and
Phase 9 checks are in `TEST_REPORT_PHASE9.md`, and Phase 10 checks are in
`TEST_REPORT_PHASE10.md`.

## Phase 3 kinetic record

```powershell
python main.py --build-kinetics `
  --input data/processed/vasp_result.json `
  --reaction reaction.yaml
```

This writes or appends to `data/processed/kinetic_dataset.json`. A repeated
`reaction_id` returns `DUPLICATE_ID` and does not overwrite the existing
record. `E_reaction`, activation energies, and TS verification remain unset.

## Phase 4 validation

```powershell
python main.py --validate --input data/processed/kinetic_dataset.json
```

This writes `data/processed/validation_report.json` without modifying the input
dataset. Missing information produces `WARNING`; explicit scientific or
provenance failures produce `FAILED`. A report containing failed reactions is
still written, and the command returns exit code `1`.

## Reviewed kinetic parameter handoff

The standalone versioned contract in
`schemas/kinetic_parameter_handoff.schema.json` records human-approved
IS/FS/TS energies, units, source hashes, method compatibility, validation
evidence, and review status. Validate a prepared handoff with:

```powershell
python -m src.kinetics.handoff path\to\kinetic_parameter_handoff.json
```

The blank template is
`examples/kinetic_parameter_handoff.template.json`. It is intentionally
`DRAFT` and not eligible for simulation. The current workflow and adapters do
not consume handoffs yet; see `docs/KINETIC_PARAMETER_HANDOFF.md` and its
review record before any integration work.

## Phase 5 CATKINAS adapter

```powershell
python main.py --generate-catkinas `
  --input data/processed/kinetic_dataset.json
```

The matching `validation_report.json` is read from the same directory as the
dataset. Output is written to the configured `output/catkinas_project/`.

The generated `.dat` files are the bounded static adapter format requested for
Phase 5. They are not CATKINAS MATLAB `INPUT_*` scripts and are not directly
executed by `CATKINAS.p`. Producing an executable CATKINAS model would require
additional validated thermodynamic, rate-law, standard-state, site-balance, and
solver settings that Phase 5 does not invent.

## Phase 6 Zacros adapter

Define the surface and reaction-to-site mapping manually in
`surface_config.yaml`, then run:

```powershell
python main.py --generate-zacros `
  --input data/processed/kinetic_dataset.json `
  --surface surface_config.yaml
```

The matching `validation_report.json` is read from the dataset directory.
Output is written to the configured `output/zacros_project/`. Reactions with a
`FAILED` validation status or missing forward barrier are rejected. Missing
reaction-site mappings are never inferred; when warnings are allowed, they are
recorded as `NOT_AVAILABLE` in the static adapter output.

These files preserve the Phase 6 data and provenance contract, but they are not
a directly executable Zacros model. A runnable Zacros project also requires an
explicit spatial lattice (coordinates, neighbor connectivity, and boundary
conditions) plus simulation controls, none of which Phase 6 is allowed to
invent.

## Phase 7 simulation runner

Set `simulation.catkinas_command`, `simulation.zacros_command`, and
`simulation.timeout` in `config/config.yaml`. A command with arguments must be
written as a YAML string list so each argument remains explicit and no shell is
used.

```powershell
python main.py --run-catkinas --input output/catkinas_project
python main.py --run-zacros --input output/zacros_project
```

The input project directory becomes the external process working directory.
Latest raw streams and process status are written under
`output/catkinas_run/` or `output/zacros_run/`; metadata for every attempt is
appended to `output/execution_history.json`, and runner activity is logged to
the configured `logging.phase_files.simulation` path.

`SUCCESS` means only that the configured process returned exit code zero. It
does not validate scientific inputs or interpret the simulator output. In
particular, the bounded Phase 5/6 static adapter files may still be rejected by
real CATKINAS/Zacros installations that require additional model-specific
inputs.

## Phase 8 result parser

```powershell
python main.py --parse-catkinas-result --input output/catkinas_run
python main.py --parse-zacros-result --input output/zacros_run
```

The parser follows the Phase 7 `run_status.json` `input_path` when the simulator
wrote result files in its working project directory. It writes
`output/results/simulation_result.json` and `parser_log.json` by default.

Supported strict text-export contract:

- CATKINAS: `coverage.dat`, `reaction_rates.dat`, and `tof.dat`;
- Zacros: `coverage.dat`, `tof.dat`, and either native
  `procstat_output.txt` or `event_frequency.dat`;
- both: optional `conditions.dat` and `selectivity.dat`;
- all keyed `.dat` files use one `label value` pair per line;
- reaction/event keys are resolved through the existing `mapping.json` and are
  never renumbered.

CATKINAS native `data<i>.mat` is detected but not decoded because the public
format is version-dependent and no stable variable schema is provided. Zacros
`specnum_output.txt` is used for its explicitly reported temperature only; raw
species counts are not mislabeled as coverage. A normalized `coverage.dat` is
required, and TOF is parsed only when explicitly exported rather than computed
with an unstated product or normalization convention.

## Phase 9 analysis and report

Set `report.output_path` and `report.template_path` in `config/config.yaml`,
then run:

```powershell
python main.py --analyze --input output/results/simulation_result.json
```

The command writes `output/report/analysis_result.json` and `report.md` by
default. Coverage and reaction rates are sorted numerically. The reported
`relative_contribution` is only `abs(rate) / sum(abs(rate))`; it is not a
mechanistic assignment or an RDS criterion.

The Phase 8 schema does not contain surface identity, Phase 4 validation data,
VASP provenance, kinetic-dataset provenance, or units. Phase 9 therefore marks
those report fields `NOT_AVAILABLE` instead of discovering or inferring them.

## Phase 10 workflow controller

Each case is self-contained:

```text
example/
├── vasp/
├── reaction.yaml
├── surface.yaml
└── config.yaml
```

The case `config.yaml` contains the complete application configuration plus an
explicit workflow section. Relative paths are resolved from the case directory.

```yaml
workflow:
  software: CATKINAS  # or ZACROS; exactly one is required
  output_root: ../../output
```

Run or inspect the case with:

```powershell
python main.py --workflow --case .\case\example
python main.py --workflow-status --case .\case\example
```

Outputs are placed under `<workflow.output_root>/<case-name>/`. The controller
persists `workflow_state.json` before and after every step and stops on the
first failure. A clean saved state resumes only pending work after successful
steps. A step left `RUNNING` by an interrupted process is marked for manual
review and is not automatically executed again.

Only the backend named by `workflow.software` is generated, run, and parsed;
the controller does not choose between simulators. Raw run artifacts,
`parser_log.json`, and `execution_history.json` are retained in addition to the
required result files.

The current Phase 3 builder deliberately leaves activation barriers unset,
while Phase 5/6 require an existing forward barrier. A standalone reviewed
handoff contract now validates eligible data, but it is intentionally not
connected to dataset promotion, workflow, or adapters. Therefore a new
raw-VASP case still stops at input generation. The Phase 5/6 adapter formats
also remain static representations and may not be directly executable by a
real CATKINAS or Zacros installation.

## Limitations

The repository is an engineering preview, not a scientifically complete
closed-loop release. Raw VASP input cannot currently cross the reviewed
handoff-to-dataset integration gate, native simulator compatibility is
unverified, and no complete real-data example is distributed. See `CODE_REVIEW.md`,
`IMPLEMENTATION_STATUS.md`, and `docs/TODO.md` for the exact boundaries.
