---
name: surface-adsorption-builder
description: Generate and screen reviewable slab-adsorbate starting structures from verified local structures and candidates accepted by the whitelist-first adsorption evidence gate.
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
- When external site/orientation data are needed, consume only accepted `catalysis-data-retrieval` records.
- Do not perform an independent literature or web search.

## Build and Review

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
launcher. It requires `--repo-root`, `--sites` (the repository site JSON),
`--plan` and `--outdir`; it delegates to the repository generator. Old site-name
lists and height/bond-length overrides are not supported. A missing plan or
repository blocks generation rather than running the retired fixed-site sweep.

## Handoff

For an authorized ML/VASP handoff, follow `configs/execution_backends.yaml`.
Every predicted GPU result returns to `work` for chemistry/geometry/provenance
review before VASP preparation. Predictions cannot remove an evidence-required
motif, establish adsorption stability, or supply reportable adsorption energy.

This skill builds candidates; it does not retrieve evidence, choose an accepted endpoint by itself, or submit jobs automatically.
