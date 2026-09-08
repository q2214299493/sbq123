---
name: surface-adsorption-builder
description: Generate and screen reviewable slab-adsorbate starting structures from verified local structures and candidates accepted by the whitelist-first adsorption evidence gate.
---

# Surface Adsorption Builder

Use `modules/adsorption_workflow/README.md` as the canonical procedure.
Use `configs/skill_routing.yaml` as the canonical ownership and rule-source map;
this skill does not redefine those policies.

## Evidence Gate

- Use verified local slabs and endpoints first.
- When external site/orientation data are needed, consume only accepted `catalysis-data-retrieval` records.
- Do not perform an independent literature or web search.

## Build and Review

Run the evidence-gated AdsMind plan, generate only its build-ready candidates,
apply the geometry checks from the owning config, and hand results to the
adsorption module for scientific review. The detailed rules remain in the
config paths declared by `configs/skill_routing.yaml`.

After those gates pass, `configs/execution_backends.yaml` routes the candidates
to AQCat25 on `BUCT(sbq)` for predicted pre-relaxation and ranking. Every GPU
result returns to `work` for chemistry/geometry/provenance review before
`sunboquan-codex` may run VASP. AQCat25 cannot remove an evidence-required
motif, establish adsorption stability, or supply reportable adsorption energy.

This skill builds candidates; it does not retrieve evidence, choose an accepted endpoint by itself, or submit jobs automatically.
