# Fe(110) CO Dissociation Example

This is a configuration and failure-handling example, not a packaged
scientific result. No VASP output, activation barrier, CATKINAS output, or
Zacros output is fabricated or redistributed here.

## Prepare the case

1. Place real VASP output files under `vasp/`.
2. Review `reaction.yaml` and `surface.yaml` against that calculation.
3. Replace the simulator command in `config.yaml`.
4. Confirm the selected backend in `workflow.software`.

## Run

From the repository root:

```powershell
python main.py --workflow --case examples/Fe110_CO_dissociation
python main.py --workflow-status --case examples/Fe110_CO_dissociation
```

Outputs are configured under `output/Fe110_CO_dissociation/`.

## Expected repository example result

The distributed `vasp/` directory intentionally contains no OUTCAR. Running
the example as shipped returns exit code `1`, writes `vasp_result.json`, and
records `failed_step: vasp_parser`. This verifies fail-fast orchestration and
does not claim a completed calculation.

Even after real VASP files are supplied, Phase 3 does not generate an
activation barrier. The workflow must stop at adapter generation unless an
authorized upstream handoff provides reviewed kinetic data. See
`docs/TODO.md`; do not insert a guessed barrier.
