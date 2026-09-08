# Baseline Mean-Field MKM

## Purpose

Solve the non-coverage-self-consistent mean-field mechanism for coverages, rates, TOF, selectivity, and degree of rate control.

## Primary Software

- CATKINAS is the preferred local mean-field MKM tool; its verified path, runtime, and I/O contract are in `configs/postprocessing_software.yaml`.
- The quickstart proves software execution only, not project-specific scientific validity.

## Entry Gate

- balanced reaction network
- validated free-energy barriers and prefactors
- temperature, pressure/feed, site density, and rate-law conventions
- CATKINAS input file generated from traceable kinetic records, not manual untracked values

## CATKINAS Input Scope

- reaction mechanism equations and site notation
- activation/free-energy inputs or approved scaling/BEP parameters
- gas pressure or concentration conditions
- initial/frozen coverages when specified
- calculation mode: single, curve, or map
- optional DRC and plotting settings

## Outputs

- steady-state solution and site/mass-balance residuals
- TOF, selectivity, coverage, and DRC tables
- reproducible solver settings and provenance
- CATKINAS `result_INPUT*` folder metadata and parsed outputs, when execution is enabled

## Done Criteria

Mass/site balances close and the CATKINAS inputs, solver settings, rates, coverages, selectivity, and DRC outputs are reproducible and traceable.
