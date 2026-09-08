# MM-002 Migration Report

- Batch: `MM-002`
- Completed: 2026-06-23
- Scope: adsorption, endpoints, and Fe convergence
- Accepted records: 11
- Scientific calculation files modified: none

## Verification Summary

- Four adsorption/coadsorption OUTCAR values verified directly on `sunboquan-codex`.
- Both active NEB endpoints traced to converged remote CONTCAR files and matched to the current path.
- Nine bounded convergence README/CSV files copied into the module as evidence.
- Bulk and clean-slab production baselines reproduce the recorded sub-`1 meV/atom` criterion.

## Limitations

- Raw clean-slab and gas-CO reference OUTCAR paths remain `Needs confirmation`.
- Extra smearing/vacuum/thickness runs are preserved as completed data, but no new production recommendation was inferred from total energies alone.
