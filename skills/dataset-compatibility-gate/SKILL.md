---
name: dataset-compatibility-gate
description: Check whether VASP bulk, clean slab, gas, adsorption, static, endpoint, NEB, and Excel/registry records belong to one compatible dataset branch. Use before comparing energies, computing adsorption/reaction/barrier values, promoting results to Excel or registry, reusing endpoints, or mixing current Fe(110), carbide, oxide, or historical outputs.
---

# Dataset Compatibility Gate

## Scope

Use this skill whenever a result may become data: adsorption energy, reaction energy, barrier, endpoint, Excel row, registry row, NEB input, MKM/KMC input, or a ranked candidate.

This skill does not build structures and does not submit jobs. It decides whether existing results can be compared, promoted, or must stay as candidates.

## Required startup

Read the minimum active state before judging compatibility:

1. `tasks/current_task.md`
2. Relevant sections of `docs/02_CURRENT_STATE.md`
3. `modules/README.md`
4. Owning module README, usually `modules/adsorption_workflow/README.md`, `modules/transition_state_search/README.md`, or `modules/calculation_registry/README.md`
5. `docs/11_DATA_PROVENANCE_PROTOCOL.md`
6. `docs/01_METHOD_PROTOCOL.md` when method consistency is in question

Use project files, remote files, and scheduler/output evidence. Do not infer a missing value from chat.

## Branch compatibility checks

A result can be compared only inside one compatible branch.

### Structure identity

Check:

- surface family and facet
- true Fe(110) versus historical Fe(211)-like or other legacy material
- slab model, lateral cell, layer count, vacuum, and fixed-layer rule
- clean relaxed slab parent
- adsorbate identity, isomer, orientation, coverage, and coadsorption/dissociation state
- final site class and site migration

For the active Fe(110) branch, require the five-layer Fe45 slab, bottom 18 Fe fixed, about `15 A` vacuum, and Gamma `5x5x1` unless a new branch is explicitly declared.

### Method identity

Check:

- `GGA=PE`
- PAW-PBE POTCAR family and POSCAR/POTCAR element order
- `ENCUT=400 eV`
- compatible `EDIFF`, `EDIFFG`, `ISMEAR`, and `SIGMA`
- compatible KPOINTS and static/relaxation stage
- Fe-containing magnetic systems use `ISPIN=2`
- closed-shell gas references use `ISPIN=1` and no `MAGMOM`
- MAGMOM count equals total atoms when `MAGMOM` is present
- dipole policy, DFT+U policy, and smearing group when relevant

Do not mix `5x5x1` and `7x7x1` Fe(110) energies in one adsorption-energy branch.

### Reference chain

For adsorption energy, all required terms must pass the same branch gate:

- clean slab final static
- adsorbed final static, or explicitly marked relaxation energy if no static exists yet
- gas/reference molecule or approved alternative reference
- final geometry review and duplicate status

The old failed Fe(110) clean static with unphysical positive energy is rejected and cannot be used.

## Scientific status checks

Separate these judgments:

- scheduler status: `PEND`, `RUN`, `DONE`, `EXIT`, or unavailable
- electronic convergence
- ionic/force convergence
- geometry validity
- final site classification
- duplicate/superseded status
- downstream eligibility

`DONE` alone never means scientifically usable.

## Promotion states

Use these states consistently:

- `candidate`: generated or submitted but not terminally reviewed
- `submitted`: has job ID and remote path
- `converged_unreviewed`: terminal and apparently converged, geometry not fully reviewed
- `reviewed_valid`: geometry and convergence pass, but final static or reference may still be missing
- `duplicate`: chemically same as another final structure within the chosen tolerance
- `rejected`: invalid SCF, bad geometry, wrong branch, wrong structure, or unusable reference
- `static_needed`: relaxation is valid but final static is not yet available
- `static_accepted`: final static and reference chain are compatible
- `excel_promoted`: accepted row has been written to the project Excel/registry output

Do not put low-confidence or unreviewed results into Excel as final data.

## Output format

Report one of:

- `PASS`: comparable/promotable under the named branch
- `BLOCKED`: cannot compare or promote; give exact blocking fields
- `NEEDS_REVIEW`: evidence exists but chemistry, final site, duplication, or reference status is not settled

Always include:

- compatible branch ID or `Needs confirmation`
- accepted/rejected reference chain
- blocked fields
- next smallest action

## High-risk rules

- Historical fake-Fe(110)/Fe(211)-like outputs do not enter current true Fe(110) datasets.
- Near-desorbed structures may be converged but are not automatically stable adsorption states.
- Dissociated H2 is a two-H coadsorption state, not molecular H2 adsorption.
- Site-migrated structures are recorded by final site, with initial site retained only as provenance.
- Carbide and oxide surfaces default to medium or low confidence until explicit labels/site manifests are validated.
- Oxygen vacancies require explicit tags; do not guess vacancies.
- Hydroxylated oxide surfaces, C2+ multidentate adsorption, and ambiguous lattice/adsorbate C/O identity require review and are not automatically exported.
