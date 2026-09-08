# MM-003 Migration Report

- Batch: `MM-003`
- Completed: 2026-06-23
- Scope: decisive NEB and DIMER history
- Accepted records: 15
- Scientific calculation files modified: none

## Result

The migration retains only failures that change future setup or stopping decisions. Repetitive parameter variants and obsolete running-state details were omitted.

## Verified Evidence

- Remote archive directories exist for the early DIMER failures, `9430977`, `9433782`, `9434479`, and `9434583`.
- Local postmortem folders exist for jobs `9455800` and `9532195`.
- The converged A endpoint review folder and endpoint-derived path precheck folder exist locally.

## Main Preserved Constraints

- Do not proceed to CI-NEB from a collapsed ordinary path.
- Do not use a TS-like structure as the product endpoint.
- Do not assume SCF stability implies path validity.
- Do not use a manually guessed C/O-only DIMER mode without inspecting it.
- Always analyze periodic endpoint branches before constructing adsorbate motion.
