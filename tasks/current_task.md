<!-- state-handoff:start current_task -->
# Current Task

## Objective

Review Fe110 adsorption motifs for C2H, CCH2 and three C2HO hydrogen-placement isomers; prepare bounded AQCat25 pre-relaxation candidates.

## Current Evidence Snapshot

- Original local CARE C2 network contains three predicted Fe48 poses per exact species; all15 preserved and mapped with existing Fe110 mapper to the verified Fe45 clean slab.
- 14 initial geometry checks pass; CCH2 cfg0 is flagged by the adsorbate-height rule. This is not proof of a collision or a stability result.
- CHCO configs0/1/2 are height-only seed variants, not three distinct adsorption motifs. Surface symmetry equivalence of other poses remains unreviewed.
- Bounded whitelist search found no usable exact record; controlled literature fallback identified ACS JPCC2018 SI geometries for CCH, CCH2, CHCO and CCHO+H. No three-minimum literature claim or external energy import.
- MZ73 SSH connection closed remotely; GPU resource state unknown. No GPU or VASP submitted. Prior Dimer9833429 formal mode/frequency review remains deferred in backlog.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Review initial motif equivalence and CCH2 cfg0 height flag, then freeze the selected candidate list for an AQCat25 handoff; do not submit unreviewed inputs.

## Submission Boundary

User requests adsorption calculations with GPU preference. Preparation is authorized; expensive remote execution waits for reviewed hash-bound inputs and explicit bounded submission authority.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Exact identities, literature limits, candidate geometry and duplicate issues are reviewable before GPU/VASP submission.

## Constraints

- Use true Fe110 Fe45 five-layer branch, fixedFe0-17 and SIGMA0.20 production method.
- Do not substitute acetylene for CCH2 or mix the three C2HO graphs.
- Candidate counts follow distinct supported motifs; no blind three-site padding or ML global-minimum claims.
- AQCat25 is adsorption pre-relaxation primary; results return through work before VASP.

## Authoritative References

- archive/fe110_five_c2_adsorption_20261006/REVIEW.md
- archive/fe110_five_c2_adsorption_20261006/request_and_retrieval.json
- calculations/fe110_five_c2_adsorption_20261006/candidate_review.json
- archive/fe110_five_c2_adsorption_20261006/literature_review.json
<!-- state-handoff:end current_task -->
