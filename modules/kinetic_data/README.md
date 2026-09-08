# Kinetic Data Schema

## Purpose

Translate validated DFT and thermochemistry outputs into machine-readable species, energy, reaction, barrier, rate, and coverage-dependence records.

## Required Inputs

- registered and validated adsorption states
- Grade A transition states
- consistent DFT energy branch and free-energy corrections
- units, temperature, pressure, reference convention, and provenance

## Outputs

- species table
- electronic and free-energy table
- balanced reactions and forward/reverse barriers
- rate expressions and prefactors
- coverage-dependence parameters with valid ranges
- export package for downstream post-processing tools:
  - CATKINAS-ready mean-field MKM input fields
  - Zacros-ready event/lattice/rate fields for surface KMC

No ambiguous free-text energy may feed kinetics.

## Post-Processing Handoff Rule

CATKINAS and Zacros 4.0 consume only validated records from this module and the reaction-network module. They must not receive hand-entered energies or barriers unless each value has units, reference convention, source file, and review status.

## Done Criteria

Machine-readable tables, units, references, confidence/review fields, validators, and CATKINAS/Zacros export contracts exist.
