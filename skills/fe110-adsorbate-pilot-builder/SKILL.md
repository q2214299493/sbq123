---
name: fe110-adsorbate-pilot-builder
description: Build chemistry-ranked true Fe(110) adsorption pilots for iron Fischer-Tropsch and related C/H/O species from accepted clean-slab and reference structures. Use when predicting binding motifs, adding Fe(110) adsorbates/isomers/orientations, generating VASP inputs, checking site and multi-anchor placement, or deciding the smallest calculation set before expansion.
---

# Fe(110) Adsorbate Pilot Builder

`configs/skill_routing.yaml` is the canonical ownership and rule-source map.
This legacy-named skill is a consumer of the AdsMind planner and surface builder;
it is not the owner of evidence retrieval, motif policy, or structure generation.

## Scope

Use this skill for the current true Fe(110) adsorption workflow only. It is a pilot-builder and pre-submission checker, not a final-energy promoter and not a registry writer.

Hard scope boundary: do not apply this skill, its site rankings, calibration
profiles, or `iron_fts_prescreen.yaml` to Fe(100), Fe(111), any other metallic
Fe facet, iron carbide, or iron oxide. Return
`fe110_only_rule_not_transferable` instead. A different surface requires a
separate user-approved rule set and calibration; do not create one implicitly.

Use `dataset-compatibility-gate` before comparing energies, promoting results to Excel/registry, or reusing endpoints downstream.

## Required startup

Read the minimum active state before acting:

1. `tasks/current_task.md`
2. The Fe(110) and active adsorption sections of `docs/02_CURRENT_STATE.md`
3. `modules/README.md`
4. `modules/adsorption_workflow/README.md`
5. `docs/01_METHOD_PROTOCOL.md` only when starting or changing a calculation method
6. `modules/catalysis_data_retrieval/` output when external site evidence is
   required; whitelist first, authoritative literature only after
   `NO_WHITELIST_MATCH`

Do not reconstruct calculation state from chat when repository or remote files exist.

## Fixed active Fe(110) branch

For the current Fe(110) dataset, keep this branch unless the user explicitly starts a new compatibility branch:

- true Fe(110), not historical Fe(211)-like material
- latest relaxed five-layer Fe45 slab
- bottom 18 Fe fixed
- vacuum about `15 A`
- Gamma `5x5x1`
- `GGA=PE`, PAW-PBE, `ENCUT=400 eV`
- Fe-containing systems: `ISPIN=2` with correct `MAGMOM` count
- closed-shell gas molecules: `ISPIN=1`, no `MAGMOM`
- slab adsorption relaxations: keep the current Fe(110) `EDIFF`, `EDIFFG`, `ISMEAR`, and `SIGMA` branch

Do not mix `7x7x1`, old failed clean-static branches, old fake-Fe(110)/Fe(211)-like records, or non-matching slab models into this branch.

## Pilot workflow

### Mandatory pre-calculation decision contract

For an iron Fischer-Tropsch C/H/O intermediate, read
`references/iron-fts-prescreen.md` and use
`configs/adsmind_lite/iron_fts_prescreen.yaml` before applying generic rules.

Before generating any adsorption structure, report and record:

- exact species, isomer, charge/spin branch, and conformer;
- likely and forbidden binding atoms;
- monodentate, bidentate, multidentate, and plausible dissociative modes;
- orientation families and symmetry-equivalent duplicates;
- ranked adsorption-motif hypotheses and the evidence tier for each;
- excluded motifs with migration, duplication, reaction, desorption, or failed
  convergence evidence;
- selected candidate count, confidence, and manual-review needs.

Reuse compatible reviewed local structures when they already exist. For a new
or missing adsorption motif, run `catalysis-data-retrieval`: search the approved
whitelist first and stop when it provides a usable exact match. Only a recorded
`NO_WHITELIST_MATCH` permits the authoritative-journal fallback. If neither
stage provides an accepted stable motif, return `NEEDS_REVIEW`; do not create a
blind site sweep.

Chemical reasoning may formulate retrieval terms and review transferability,
but it cannot seed a calculation by itself. Candidate count is exactly the
number of unique stable configurations supported by the selected evidence;
there is no complexity-based minimum, maximum, or budget expansion.
Use accepted stability order to prioritize candidates and use reported bond
lengths, angles, heights, and orientations only as initial-geometry references.
External energies never become project results; compatible local calculations
alone determine reportable adsorption energies.

Eliminate symmetry-equivalent rotations, starts known to converge to the same
state, and single-anchor approximations of multidentate bonding.

1. Confirm the adsorbate identity.
   - Use an explicit species label, for example `CHO_formyl_Cend`, `CH2O_formaldehyde_Oend`, `CH3O_methoxy_Oend`, or `CH4O_methanol_Oend`.
   - Separate isomers, end-on orientations, dissociated states, and coadsorption states. Do not collapse them under a bare formula.

2. Confirm the gas/reference base.
   - Prefer an accepted optimized gas/reference structure from the current branch.
   - If no accepted base exists, run the catalysis-data whitelist gate or create a reviewable gas optimization first.
   - Record spin branch, job ID, remote path, and final geometry before using it as an adsorbate base.

3. Run the chemistry-aware pre-screen before choosing pilot size.
   - Use `configs/adsmind_lite/prescreen_rules.yaml` and
     `python -m scripts.adsmind_lite.plan_adsorption_candidates`.
   - Keep geometric site classes as a surface dictionary; do not interpret them
     as a mandatory four-job list for every adsorbate.
   - Select adsorption motifs first: binding denticity, binding atoms,
     orientation, intact/dissociative state, and only then the required surface
     projection(s).
   - Search whitelist sources first; only `NO_WHITELIST_MATCH` permits the
     authoritative-journal fallback owned by `catalysis-data-retrieval`.
   - Use every unique stable motif accepted by the evidence gate and no others.
     Never impose a fixed two- or four-candidate count.
   - Use reviewed local migration and duplicate outcomes to suppress starts that
     repeatedly collapse to the same final state.
   - A multidentate motif must use a reviewed multi-anchor structure template;
     never approximate it with one atom placed over one geometric site.

4. Generate sites only through the project Fe(110) site contract.
   - Use `scripts/adsorption/build_fe110_adsorption.py` or wrappers that call its site logic.
   - Do not hand-code `top`, `short_bridge`, `long_bridge`, or `hollow` coordinates.
   - `hollow` must be a true three-top-Fe centroid, not an Fe-Fe midpoint.
   - Site generation must depend only on the clean relaxed Fe(110) slab, not on the adsorbate.

5. Add adsorbates through metadata only.
   - New species require name, exact chemical meaning, atom order, anchor atom/index, internal geometry, orientation rule, recommended Fe-anchor distance, and selected pilot sites.
   - Do not change site-generation logic just to support a new adsorbate.

5a. Apply known Fe(110) candidate reductions.
   - H2O: use only top-like molecular O-bound starts with at most two
     symmetry-inequivalent orientations. Step 12A already showed that bridge and
     hollow starts collapse into the same top-like final class.
   - CHO/formyl: prioritize the side-on, C/O dual-center `h-lb-h` hypothesis
     reported by the user. It is blocked from automatic construction until its
     exact atom-to-site structure template and provenance are registered.
   - Do not default to `CHO_formyl_Oend/top`; job `9606916` exhausted `NSW=300`
     while developing H-transfer/dehydrogenation character.

6. Prepare inputs and check before submission.
   - Check POSCAR uses the latest clean relaxed slab and preserves bottom fixed layers.
   - Check vacuum, KPOINTS, INCAR, POTCAR order/link, POSCAR element order, and MAGMOM count.
   - Check anchor-to-Fe distance, internal bonds/angles, C/O/H orientation, no Fe-adsorbate overlap, and site identity.
   - Check `job.sh` syntax.
   - Do not submit unless the user explicitly asks.

6a. Use staged relaxation instead of an unconditional 300-step pilot.
   - First screening stage: `NSW=80`, with scientific review targets at ionic
     steps 20, 40, and 80 when compact monitoring evidence is available.
   - Continue from `CONTCAR` only for plausible, nonduplicate candidates that
     still show meaningful force/energy progress.
   - Stagnation, duplicate-site migration, desorption, or unintended chemistry
     triggers review; it does not trigger automatic stopping or deletion.

7. Report in three groups.
   - Submit-ready tasks.
   - Blocked tasks with exact reason.
   - Needs-review tasks where chemistry or site identity is plausible but not guaranteed.

## Adsorbate placement rules

- CO: C anchor, C end toward Fe, C-O about `1.15 A`, Fe-C about `1.8-2.1 A`.
- H: H anchor, Fe-H about `1.55-1.8 A`.
- O: O anchor, Fe-O about `1.8-2.1 A`.
- OH: O anchor, H above O and away from Fe, O-H about `0.97 A`, Fe-O about `1.9-2.2 A`.
- H2O: O anchor, H atoms above O, preserve optimized O-H and H-O-H geometry, Fe-O about `2.1-2.5 A`.
- C: C anchor, Fe-C about `1.75-2.05 A`.
- CH/CH2/CH3: C anchor, preserve optimized C-H geometry and intended spin branch.
- CH4: weak binding is likely; pilot as one-H-down/H-anchored or other explicitly named orientation, then mark desorption risk.
- CHO/formyl: test C-end and O-end separately when needed.
- CH2O/formaldehyde: usually O-end first; watch eta2 C/O contact.
- CH3O/methoxy: O anchor; watch C-O cleavage and H transfer.
- CH4O/methanol: O-end weak adsorption; watch desorption and O-H/C-O activation.

## Completion handoff

After submission, update `tasks/current_task.md` and the compact current state with:

- remote root
- job IDs
- species/site/orientation mapping
- branch parameters
- monitoring risks
- next checkpoint

After completion, do not promote energies directly from this skill. Run `dataset-compatibility-gate` first.
