# MM-004 Extracted Notes

## Preserved Workflow

1. Validate DFT structures, adsorption energies, NEB/CI-NEB/DIMER TS candidates, and frequencies.
2. Apply ZPE, enthalpy, entropy, and Gibbs corrections.
3. Build balanced species, reaction, barrier, and rate tables with units and provenance.
4. Solve baseline mean-field MKM.
5. Add coverage-dependent energetics when required.
6. Escalate to surface-reaction KMC for diffusion, heterogeneity, lateral interactions, or spatial correlations.
7. Connect validated intrinsic rates to a specified reactor model.
8. Use sensitivity, DRC, and uncertainty propagation to prioritize new calculations.

## Boundaries

- GCMC/adsorption isotherms provide equilibrium loading or coverage inputs; they are not substitutes for surface-reaction KMC.
- Coverage-self-consistent MKM is required only when energetics depend on coverage.
- Reactor simulation starts only after rate units, site density, and kinetic source are defined.

## Missing Inputs

- complete reaction mechanism and site balance
- validated TS and frequency data
- thermochemical corrections and free-energy table
- operating temperature, pressure, feed, and standard states
- coverage-dependent interaction parameters
- KMC lattice, events, diffusion barriers, and neighbor rules
- reactor type, catalyst loading, transport assumptions, and site density
