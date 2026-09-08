# Convergence Workflow

## Purpose

Select transferable VASP numerical and slab settings for a precisely defined material model and accuracy target.

## Inputs

- structure family and magnetic state
- candidate ENCUT, k-mesh, smearing, vacuum, and slab-thickness ranges
- comparison quantity, normalization, and tolerance
- reviewed retrieval evidence when an external model or parameter range is adopted

## Gates

- Keep geometry, pseudopotentials, functional, magnetism, and comparison convention consistent.
- Lock `GGA=PE`, the approved PAW-PBE POTCAR family, and `ENCUT=400 eV` across each adsorption-energy dataset. Use `ISPIN=2` for Fe-containing magnetic systems and `ISPIN=1` without `MAGMOM` for closed-shell gas-phase CO. Metals and oxides may have separate convergence-backed `EDIFF`/`EDIFFG`, smearing, magnetic, and DFT+U branches, but one reported energy difference cannot mix branches.
- Within one surface family, converge and then lock the lateral cell, slab thickness, vacuum, fixed-layer rule, dipole policy, and slab k-mesh for every clean, adsorbed, endpoint, and TS state.
- Use a suitable energy quantity for smearing comparisons and normalized surface energies for slab thickness.
- Do not transfer Fe(110) settings to chi-Fe5C2 or Fe3O4 without system-specific evidence.

## Outputs and Handoff

- convergence tables, selected routine settings, high-accuracy settings, limitations, and source paths
- registry records for every sweep job, input, output, and extracted result
- downstream handoff to adsorption, NEB, and static-energy workflows

## Corrected True Fe(110) Result

- Jobs `9554557-9554562` completed normally for bulk and 4-8-layer clean slabs.
- All slabs retain flat Fe(110) layers, negligible lateral motion, and zero fixed-layer drift.
- Clean-surface geometry supports five layers as the active production model and seven layers as a validation reference.
- Five layers are locked for the production dataset by explicit user decision. Any later matched five- and seven-layer CO/C+O comparison is validation-only; it must be stored as a separate compatibility branch and cannot switch production automatically.
- Seven versus eight layers differs by `0.0008 A` in top interlayer spacing and `0.0106 J/m2` in surface excess.
- Clean-surface convergence does not replace matched adsorbate/reaction observables for quantifying the production model's remaining thickness uncertainty.
- Curated results: `results/fe110_true_facet_thickness_20260628.csv`.

## Reusable Utilities

- `scripts/convergence/setup_alpha_fe_bulk_smearing.py`: alpha-Fe smearing campaign.
- `scripts/convergence/setup_true_fe110_thickness_retest.py`: corrected true bcc Fe(110) four-to-eight-layer relaxation/static campaign and surface-excess summary.

These scripts have distinct scopes. Submission flags require task-level review and registry setup before use.

Old wrong-facet generator scripts have been removed from the repository.

## Done Criteria

Selected settings, tolerance, transfer scope, source paths, limitations, and registry records exist for every accepted campaign.
