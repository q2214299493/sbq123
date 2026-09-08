# MM-004 Migration Report

- Batch: `MM-004`
- Completed: 2026-06-23
- Scope: MKM, KMC, and reactor workflow planning
- Accepted records: 10
- Scientific calculation files modified: none

## Result

The complete intended DFT-to-reactor chain is preserved as a dependency graph, not as completed software. All referenced local skills were confirmed present.

## Registered Status

- Kinetic data schema: `Planned`
- Thermochemistry, reaction network, baseline MKM, coverage MKM, surface KMC, reactor simulation, and sensitivity/uncertainty: `Blocked` until required upstream inputs exist.

## Next Modeling Entry Point

Define the machine-readable species/energy/reaction/barrier schema first. It can proceed before the full dataset is complete and prevents unit or provenance loss later.
