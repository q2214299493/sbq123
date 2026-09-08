# Catalysis Data Retrieval

## Purpose

Provide the single external-data gate before any new catalysis calculation, including convergence campaigns, slab/adsorbate construction, adsorption and coadsorption states, endpoints, NEB/CI-NEB, DIMER, frequency setup, reaction networks, and kinetic-model parameter sourcing.

Monitoring or post-processing an already defined calculation does not rerun this gate unless a new external structure, path, or parameter is introduced.

## Source Boundary

First-stage whitelist searches may use only the sources and URL scopes in
`skills/catalysis-data-retrieval/references/sources.yaml`:

- Catalysis-Hub and CatApp
- Open Catalyst Project OC20/OC22
- OC20NEB and CatTSunami
- Materials Project Catalysis Explorer
- Materials Cloud Archive
- ioChem-BD
- NOMAD Catalysis

Local verified project files remain valid inputs. Official VASP/VTST
documentation may be used for software syntax and method behavior, but not as
an external structure/path database. Authoritative-journal literature is a
second-stage source only after the whitelist stage records
`NO_WHITELIST_MATCH`.

## Skill Routing

`configs/skill_routing.yaml` is the machine-readable authority. This module owns external structure/path/data retrieval; VASP, adsorption, NEB, DIMER, frequency, and kinetics skills only consume reviewed output.

For adsorption motifs only, this module may invoke chemistry literature
retrieval at that second stage. The article must be primary research in an authoritative peer-reviewed
chemistry/materials/catalysis journal with verified DOI and publisher URL,
exact surface and adsorbate matching, direct stable-structure evidence, and a
reviewed transferable geometry. Other scholarly work remains explicit-only.

## Gate

1. Define the target material, surface/facet, adsorbate/reaction, calculation stage, and desired data type.
2. If an image is supplied, inspect it and save reviewable visible features and uncertain inferences before producing text query terms. Never infer elements from display colors alone.
3. Ingest only whitelist-valid records with source URL, record ID, retrieval time, data type, license/access note, and scientific metadata.
4. Rank with BM25 plus a real sentence-embedding cosine score. Lexical-only mode is diagnostic and does not pass the production gate.
5. Return at most five results. Preserve component scores and explain local-system mismatches.
6. Human-review transferability before using any structure or path. Retrieved data never bypass endpoint, convergence, geometry, or TS validation.
7. If a usable whitelist motif exists, stop; literature retrieval is forbidden.
8. For an adsorption-site task with no usable motif, record
   `NO_WHITELIST_MATCH`, then search only authoritative journals under
   `configs/adsmind_lite/evidence_gate.yaml`. Other task types remain blocked.
9. Deduplicate by stable motif, not nominal site name. Return all and only the
   supported stable configurations; never pad to a fixed site sweep.
10. Rank the accepted motifs and extract only structure references needed to
    reduce local computation: sites, binding atoms, bond lengths, angles,
    surface heights, and orientations. Mark every reported external energy as
    relative-order reference only.

## Outputs

- normalized source records as JSONL
- image-query JSON when applicable
- `retrieval_top5.json` with BM25, semantic, and hybrid scores
- source/access warnings and transferability review
- a calculation-module handoff containing only accepted constraints or candidate references
- an evidence-gate decision recording whitelist stop or literature fallback,
  DOI/journal provenance, stable motifs, and rejected transferability claims

## Boundaries

This module does not perform DFT, accept a structure, infer missing scientific
values, or claim that database similarity proves transferability. It never
imports external energies into local results, the calculation registry, or
Excel. The owning scientific module keeps its own geometry, numerical, and
acceptance gates.

## Done Criteria

- every first-stage URL passes the whitelist validator
- literature is absent when a usable whitelist match exists
- every accepted fallback article has verified DOI/publisher provenance and an
  exact stable-motif match
- every result has traceable source metadata
- production output uses both BM25 and semantic ranking and contains at most five items
- image-derived claims are separated into visible facts and uncertain interpretations
- no scientific module contains a duplicate web/literature search implementation
