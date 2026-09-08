# Runtime Data

This directory is intentionally lightweight. The CLIs create `surfaces/`, `adsorbates/`, `candidates/`, `relaxed/`, `reports/`, and `vasp_ready_adsorption/` only when requested.

Generated JSONL, VASP structures, and relaxed outputs are runtime artifacts and remain ignored unless a concise reviewed result is explicitly promoted.

`surfaces/Fe5C2_010/site_manifest.yaml` and `surfaces/Fe3O4_001/site_manifest.yaml` are staged templates. They must be filled with indices and labels from the exact slab; empty templates do not enable candidate generation.

For vacancy sites, use `site_role: vacancy_O` inside the explicit site record and set both the site and `high_risk_sites.oxygen_vacancy` validation flags. Atom indices remain 1-based and must refer to the exact source structure.
