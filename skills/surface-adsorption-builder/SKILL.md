---
name: surface-adsorption-builder
description: Build reviewed slab-adsorbate starting structures when the user asks for new configurations, different adsorption sites, or a missing adsorbed transition-state endpoint. Start with the repository adsorption evidence gate before constructing coordinates or pre-relaxing them with MACE or another model.
---

# Surface Adsorption Builder

Use `modules/adsorption_workflow/README.md` as the canonical procedure.
Use `configs/skill_routing.yaml` as the canonical ownership and rule-source map;
this skill does not redefine those policies.

Locate the current project root from its routing config and owning module.
If those repository files are missing, report the missing project context;
do not fall back to a standalone placement algorithm in the global skill.

## Evidence Gate

- Use verified local slabs and endpoints first.
- Use accepted `catalysis-data-retrieval` records for confirmed motifs. Use the
  retrieval review's supporting references to justify local hypotheses when
  confirmed coverage is short.
- Do not perform an independent literature or web search.

## Build and Review

Requests to add missing adsorption poses or to find three different sites use
the AdsMind plan even when the user names a particular pre-relaxation model.
If the task specifies distinct site classes, pass
`--require-distinct-site-classes` to the generator. Report a source-evidence
shortfall and review any proposed local starting hypotheses through the
existing template bundle before pre-relaxation. Route new work based on
historical structures through the same plan. Keep test fixtures and archived
exploratory scripts out of routine scientific intake.

Run the evidence-gated AdsMind plan, generate only its build-ready candidates,
apply the geometry checks from the owning config, and hand results to the
adsorption module for scientific review. The detailed rules remain in the
config paths declared by `configs/skill_routing.yaml`.

## Repository Entry Points

Run these modules from the verified project root:

- `scripts.adsmind_lite.plan_adsorption_candidates`: evidence-gated planning.
- `scripts.adsmind_lite.detect_surface_sites`: canonical site dictionary.
- `scripts.adsmind_lite.generate_adsorption_candidates`: generation from the
  reviewed plan and site JSON, including supported reviewed templates.
- `scripts.adsmind_lite.validate_candidates`: owning geometry checks.

Fe(110) topology comes only from `scripts/adsorption/build_fe110_adsorption.py`.
Do not implement pair selection or slab/adsorbate placement inside this skill.
The module READMEs own command details and the distinction between site
dictionaries, initial-mode coverage, configurations and final stable minima.

The legacy `scripts/place_fe_co_candidates.py` path is a CO-only compatibility
launcher: `python scripts/place_fe_co_candidates.py PATH_TO_POSCAR`. It finds
the unique project above the current directory or POSCAR, asks the repository
to detect fresh sites, and uses `plan.json` or `prescreen_plan.json` beside the
POSCAR. Without a sidecar, the repository planner prepares a draft; missing
evidence or review still blocks candidate generation and retains the inputs.
Output defaults to a new numbered directory under
`modules/adsmind_lite/data/candidates/co_candidates`; existing results are
never overwritten. `--repo-root`, `--sites`, `--plan` and `--outdir` remain
optional explicit selections. Ambiguous projects/plans require a selection.
Old site-name lists, height/bond-length overrides and fixed-site sweeps remain
unsupported. No draft is automatically approved.

## Handoff

For an authorized ML/VASP handoff, follow `configs/execution_backends.yaml`.
Every predicted GPU result returns to `work` for chemistry/geometry/provenance
review before VASP preparation. Predictions cannot remove an evidence-required
motif, establish adsorption stability, or supply reportable adsorption energy.

This skill builds candidates; it does not retrieve evidence, choose an accepted endpoint by itself, or submit jobs automatically.
