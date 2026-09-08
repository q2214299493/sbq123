# Calculations

This directory holds the small local input/precheck snapshot for a calculation that is still active or awaiting review.

- Live scheduler/output truth remains on the remote path recorded in `docs/02_CURRENT_STATE.md`.
- Raw VASP runtime files remain ignored; reviewed structures/results are promoted through the owning module and registry.
- Commands and scientific gates belong to the owning module README, not calculation folders.
- Completed, superseded, or rejected snapshots move to `archive/`.

Current snapshots:

- `alpha_fe_bulk_c_fe_20260629/`: prepared alpha-Fe bulk relaxation under `~/sbq/c_fe`; awaiting user review and not submitted.
- `true_fe110_clean_20260629/`: prepared five-layer 3x3 true Fe(110) clean-slab relaxation under `~/sbq/Fe110/fe110`; awaiting user review and not submitted.
