---
name: chemical-plausibility-gate
description: Classify whether a relaxed adsorption, coadsorption, gas, endpoint, or candidate structure still represents the intended chemical species. Use after geometry exists and before result promotion, Excel entry, registry review, endpoint reuse, or full-site expansion decisions; especially for dissociation, desorption, site migration, orientation flips, H transfer, C-O/O-H/C-H bond changes, and duplicate chemical outcomes.
---

# Chemical Plausibility Gate

## Scope

Use this skill to answer one question:

> What chemical state does this final structure actually represent?

It does not build structures, submit jobs, choose VASP parameters, decide KPOINTS
compatibility, or compute adsorption energies. Ownership is defined by
`configs/skill_routing.yaml`; this gate consumes structures from
`surface-adsorption-builder` and compatibility decisions from
`dataset-compatibility-gate`.

## Required startup

Read the minimum current state before judging:

1. `tasks/current_task.md`
2. The relevant current branch section of `docs/02_CURRENT_STATE.md`
3. The owning module README, usually `modules/adsorption_workflow/README.md`
4. `docs/11_DATA_PROVENANCE_PROTOCOL.md` when the result may be promoted

Use local/remote calculation files and compact geometry parsers when available.
Do not infer a final chemical state from the folder name alone.

## Required inputs

For every judged structure, collect or mark missing:

- intended species and exact label, for example `H2`, `2H`, `CHO_formyl_Cend`,
  `CH3O_methoxy_Oend`, or `CH4O_methanol_Oend`;
- initial site and orientation;
- final site class, if a slab system;
- final internal bonds and key angles;
- nearest surface contacts and minimum adsorbate-slab distance;
- whether atoms exchanged, dissociated, recombined, desorbed, buried, or changed
  coordination;
- source path, job ID, and structure file used for the judgment.

If a required piece is absent, report `Needs confirmation` rather than guessing.

## Output fields

Use these fields consistently in reports, registry rows, and Excel promotion
prep:

- `initial_species`: intended starting species.
- `final_species`: chemically interpreted final species.
- `initial_site`: starting site or orientation label.
- `final_site`: final classified site, or `gas_like`, `desorbed`,
  `coadsorbed`, `dissociated`, or `Needs confirmation`.
- `chemical_event`: controlled label from the list below.
- `plausibility_status`: `PASS`, `NEEDS_REVIEW`, `RECLASSIFY`, or `REJECT`.
- `reason_code`: short machine-readable reason.
- `review_note`: concise human explanation.

## Status definitions

- `PASS`: intended chemical identity is preserved and geometry is chemically
  reasonable.
- `NEEDS_REVIEW`: plausible but ambiguous, weakly bound, strongly migrated,
  unusual coordination, or missing one key check.
- `RECLASSIFY`: calculation converged to a different usable chemical state, such
  as `H2* -> 2H*` or `CHO_Cend -> CHO_Oend-like`.
- `REJECT`: structure is not a usable state for this dataset because of severe
  overlap, unphysical geometry, wrong branch, broken target chemistry without a
  meaningful product assignment, or clear desorption when adsorption was the
  target.

`RECLASSIFY` is not failure. It means the result may be useful under a different
species/state label.

## Chemical event labels

Use the narrowest applicable event:

- `intact_adsorption`
- `site_migration`
- `orientation_flip`
- `dissociation`
- `recombination`
- `h_transfer`
- `dehydrogenation`
- `hydrogenation`
- `c_o_cleavage`
- `o_h_cleavage`
- `c_h_cleavage`
- `near_desorption`
- `desorption`
- `buried_adsorbate`
- `surface_reconstruction`
- `duplicate_chemical_state`
- `unclear_chemical_identity`

## Fe(110) adsorption checks

For the active true Fe(110) branch:

- Initial site is provenance only. Final site and final species control the data
  row.
- H2 with stretched or separated H-H is `2H` coadsorption, not molecular H2
  adsorption.
- H2O that migrates from bridge/hollow to top remains an H2O final state only if
  both O-H bonds and H-O-H angle remain chemically intact.
- CO remains CO only if the C-O bond remains intact; if C and O separate, mark
  `c_o_cleavage` and reclassify or reject according to the final state.
- CH, CH2, CH3, and CH4 must retain the expected C-H count unless the product is
  deliberately reclassified.
- CH4 with no meaningful Fe contact is `near_desorption` or `desorption`, not a
  stable adsorbed intermediate.
- CHO/formyl C-end and O-end starts may flip; final orientation must be recorded
  separately from the initial label.
- CH2O/formaldehyde may remain molecular, bind eta2-like through C/O, or drift;
  mark ambiguous eta2 cases `NEEDS_REVIEW`.
- CH3O/methoxy should usually be O-bound; C-O cleavage or H transfer is a
  different chemical event.
- CH4O/methanol weak binding is expected; mark O-H activation, C-O activation,
  and desorption explicitly.

Distance thresholds are screening aids, not universal proof. If a threshold and
chemical identity conflict, report `NEEDS_REVIEW` with the measured evidence.

## Handoff to other gates

Pass these outputs to `dataset-compatibility-gate`:

- final species;
- final site;
- plausibility status;
- chemical event;
- duplicate/reclassification notes.

Only `PASS` and selected, explicitly reviewed `RECLASSIFY` states can proceed
toward final static, adsorption energy, registry, Excel, endpoint, or kinetics
promotion. `NEEDS_REVIEW` stays out of final data until resolved.
