---
document_class: CURRENT_AUTHORITY
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: publication document at B5 baseline; observations retain original dates
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: CURRENT_CODE_STATE_AND_LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Project Brief

## Verified Project Type

Computational catalysis using VASP/VTST. The active production direction is the
corrected true Fe(110) workflow built from the accepted alpha-Fe bulk baseline.

## Long-Term Goal

Produce a reproducible, physically continuous Fe-surface CO-dissociation pathway from molecular CO to coadsorbed C* + O*, with the surface facet verified before adsorption, NEB, transition-state, or publication use.

Broader catalyst-agent or multi-reaction scope: **Needs confirmation**.

## Current Focus

Use the user-selected five-layer corrected true Fe(110) branch consistently
for the production adsorption and TS dataset. Any later matched five- versus
seven-layer CO/C+O comparison is validation-only and cannot switch the active
production branch automatically.

The alpha-Fe bulk foundation remains valid in
`modules/fe_convergence_baseline/`. Corrected true Fe(110) inputs are under
`modules/convergence_workflow/inputs/fe110_true_facet_thickness_20260627/`.

## Success Criteria

- Corrected slab geometry is independently verified as bcc Fe(110).
- Four-to-eight-layer relaxation/static results support an explicit production thickness or retain the limitation.
- Initial and final structures remain the verified molecular CO and C* + O* endpoints.
- The path follows molecular CO -> tilted/lying CO -> elongated TS-like geometry -> dissociated products.
- No atom-order changes, slab crossing, desorption, or unphysical C/O-Fe contacts.
- Ordinary NEB reaches a continuous path with declining forces and stable electronic iterations.
- A completed or stopped NEB is post-processed and reviewed before barrier interpretation.
- CI-NEB or another TS refinement is started only after the ordinary path is acceptable.

Publication-level force, frequency, and barrier acceptance thresholds: **Needs confirmation**.
