# Reproducibility Checklist

1. Record Python and dependency versions.
2. Preserve original VASP and simulator output directories unchanged.
3. Store the case-local `config.yaml`, `reaction.yaml`, and `surface.yaml`.
4. Use explicit executable commands and timeouts.
5. Retain generated mappings, validation reports, parser logs, execution
   history, and `workflow_state.json`.
6. Do not compare energies from incompatible computational conventions.
7. Report `NOT_AVAILABLE` rather than estimating absent values.
8. Run `python -m ruff check main.py src tests`.
9. Run `python -m unittest discover -s tests -v`.
10. Record any unavailable external software or non-redistributable data.
