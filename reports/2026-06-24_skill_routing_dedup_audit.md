# Skill Routing Deduplication Audit

## Scope

Checked the repository and installed calculation skills for duplicate pre-calculation literature or external-data retrieval behavior.

## Finding

The repository retrieval implementation was already singular, but the installed legacy `vasp-catalysis-workflow` still instructed future threads to read old memory and invoke up to five general literature skills before calculations. `neb-path-builder` and `surface-adsorption-builder` also used literature language without an explicit owner boundary.

General academic-search and paper-reading skills remain installed because they serve explicit scholarly tasks outside calculation setup. They are not automatic project fallbacks.

## Resolution

- Added `configs/skill_routing.yaml` with one retrieval owner: `catalysis-data-retrieval`.
- Added repository-backed thin VASP, adsorption-builder, and NEB-path-builder skills and synchronized them to the installed skill directories.
- Removed independent literature search and memory-first behavior from those calculation skills.
- Added contract tests that reject a second owner or a return of the retired literature-skill chain.
- Corrected one duplicate user-preference ID found during the audit.

## Verification

- Installed calculation skill hashes match repository copies.
- Active repository search found no legacy literature-first chain or second retrieval implementation.
- `python -m pytest -q`: 12 passed.

Connector completeness remains separate work: CatApp and OC20NEB/CatTSunami machine access, plus several source-specific schemas, still require confirmation.
