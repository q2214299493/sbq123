---
name: catalysis-data-retrieval
description: Retrieve catalyst structures through a whitelist-first evidence gate. For adsorption motifs only, use authoritative-journal literature fallback after NO_WHITELIST_MATCH. Use before new adsorption, coadsorption, endpoint, NEB, DIMER, frequency, reaction-network, or kinetics inputs.
---

# Catalysis Data Retrieval

Use this skill as the only external structure/path retrieval owner for the project.
Ownership and rule-source precedence are defined by `configs/skill_routing.yaml`;
this skill implements that route and does not override its owning configs.

## Workflow

1. Read `references/sources.yaml`. Reject structure/path records outside its host and path scopes.
2. Define an English retrieval query containing material/composition, surface/facet, adsorbate or reaction, state/path type, and calculation stage. Preserve formulas and Miller indices exactly.
3. For an input image, inspect it with the available image viewer. Separate directly visible features from interpretations, never infer elements from color alone, and create JSON matching `references/image_query_schema.json`. Ask for confirmation only when uncertainty changes the search materially.
4. Normalize source records to `references/record_schema.json`. Preserve the original record ID, source URL, artifact URL, retrieval timestamp, units, license/access note, and any missing fields.
5. Run `scripts/validate_records.py` before ranking.
6. Run `scripts/hybrid_search.py` with a real sentence-embedding backend or reviewed precomputed embeddings. Production retrieval must combine BM25 and semantic ranks; never label TF-IDF or lexical-only output as semantic.
7. Return no more than five results. Include source, URL, matched system/reaction, available structure/path data, BM25 score, semantic score, hybrid score, and transferability cautions.
8. If a usable whitelist motif exists, stop; do not run literature retrieval.
9. For adsorption-site tasks only, if and only if the result is
   `NO_WHITELIST_MATCH`, apply
   `configs/adsmind_lite/evidence_gate.yaml` and search authoritative,
   peer-reviewed primary chemistry/materials/catalysis journals. Prioritize
   Nature-family journals, JACS/ACS Catalysis and relevant ACS journals,
   Science-family journals, Angewandte Chemie, Chemical Science, and Journal of
   Catalysis; the examples are not an exhaustive allowlist.
10. Verify DOI, publisher URL, journal authority, exact surface and adsorbate,
    stable-site geometry, and direct stability evidence. Reject review-only
    speculation and non-exact facet transfer as build-ready evidence.
11. Return every unique stable motif supported by the accepted evidence—two if
    two are supported, four only if four are supported. Never pad to a fixed
    top/bridge/hollow list.
12. Rank motifs by reported stability and extract only structure-selection
    guidance: site, binding atoms, bond lengths, bond angles, surface heights,
    and orientation. Label external energies as relative-order references only;
    never pass them as local adsorption energies or registry/Excel values.

## Scientific Gate

- Treat retrieved structures and paths as candidates, not accepted inputs.
- Compare composition, facet, coverage, cell, functional, spin, charge, solvation, and reaction definition with the local task.
- Do not transfer a reported barrier or TS geometry as a hard constraint across non-equivalent models.
- Send accepted candidates to the owning module for its normal convergence, geometry, endpoint, path, or TS checks.
- Require a reviewed structure template before generation. Distinct stable
  configurations at the same nominal site remain distinct motifs.
- Require compatible local relaxation and final statics for every reportable
  energy. External values may guide ordering but cannot validate local energy.

## Access

Use direct official APIs/downloads where available. No MCP server is required by this skill. Materials Project may require `MP_API_KEY`; other credentials and unverified endpoints remain `Needs confirmation`. Read `references/sources.yaml` for current connector status.

## Commands

```bash
python -m pip install ".[retrieval]"
python scripts/validate_records.py records.jsonl
python scripts/hybrid_search.py records.jsonl --query "Fe(110) CO dissociation transition path" --output retrieval_top5.json
```

Use `--query-vector` only for reviewed precomputed semantic vectors. `--lexical-only` is diagnostic and cannot satisfy the project production gate.
