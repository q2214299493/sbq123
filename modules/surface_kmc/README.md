# Surface-Reaction KMC

## Purpose

Model site heterogeneity, diffusion, lateral interactions, and spatial correlations that mean-field MKM cannot represent.

## Primary Software

- Zacros 4.0 is the preferred local surface-reaction KMC engine; its verified path, shell entry, work area, and I/O contract are in `configs/postprocessing_software.yaml`.
- The example run proves software execution only, not project-specific scientific validity.

## Entry Gate

- lattice and site model
- elementary event catalog with validated rates/barriers
- diffusion and neighbor rules
- detailed-balance and boundary-condition definitions
- Zacros input files generated from traceable kinetic records, not manual untracked values

## Zacros Input Scope

- `simulation_input.dat`
- `lattice_input.dat`
- `energetics_input.dat`
- `mechanism_input.dat`
- optional `state_input.dat`

## Outputs

- event statistics, coverage evolution, spatial distributions, TOF, and uncertainty
- comparison with baseline MKM under matched conditions
- Zacros `general_output.txt`, `specnum_output.txt`, `procstat_output.txt`, `history_output.txt`, `lattice_output.txt`, and restart metadata when present

Surface-reaction KMC is distinct from GCMC adsorption loading.

## Done Criteria

The lattice/event model is traceable, detailed balance is checked, outputs are reproducible, and matched-condition comparison with baseline MKM exists.
