<!-- state-handoff:start current_task -->
# Current Task

## Objective

Prepare three distinct exploratory Fe110 adsorption candidates for each exact graph06–10, after whitelist/primary-literature review, for human structural review before computation.

## Current Evidence Snapshot

- Bounded whitelist search found no usable exact-target motifs; live Catalysis-Hub endpoint access failed. No production semantic-ranking success or exhaustive absence claim.
- Primary Fe110 papers concern CH2CO and CHCH2 but do not provide three verified stable configurations for each target; rare COC/OH graphs remain explicitly exploratory.
- Prepared candidates_v2:11 distinct local CARE pose transfers and4 user-authorized rigid reanchors;15 molecular graphs/H placements, slab/flags and hash checks passed;48 scoped tests passed.
- True Fe45 clean slab and Fe0-17 fixed preserved. Interleaved C/O records are reordered with an atom map; long molecular branches are unwrapped along bonds.
- Three soft seed warnings remain:06-A,07-A,09-B. Minimum selected seed RMSD0.487A under36 face-preserving slab operations; no height-only padding.
- No model run, GPU/VASP submission, accepted stable motif, adsorption energy registration or checkpoint promotion. Existing01–05 calculations remain untouched.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Human-review the fifteen candidates_v2 structures, literature scope and three soft warnings before preparing a separately authorized GPU batch.

## Submission Boundary

Local preparation only. GPU/VASP execution requires separate explicit authorization and current owning-module review/handoff; constructed hypotheses cannot bypass production evidence gates.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Five exact graphs each have three distinct geometry-audited candidate structures, source/construction provenance and reviewable figures/tables; submission remains unauthorized.

## Constraints

- Use the accepted Fe45 five-layer slab, exact element/coordinate maps and bottom Fe0-17 fixed.
- Do not replace COC by CCO, move OH hydrogen to carbon, or import literature/model energies as DFT results.
- This user's three-seed construction request is task-scoped exploratory authority, not a global change to stable-motif or execution rules.
- Do not promote the unvalidated fine-tuning checkpoint or alter existing calculations.

## Authoritative References

- configs/execution_backends.yaml
- modules/adsorption_workflow/README.md
- configs/adsmind_lite/fe110_c2_06_10_exploratory_20261012.json
- docs/reviews/fe110_c2_06_10_literature_20261012.md
- calculations/fe110_c2_adsorption_06_10_20261012/structure_review.md
- calculations/fe110_c2_adsorption_06_10_20261012/candidates_v2/candidate_review.json
- tasks/backlog.md
<!-- state-handoff:end current_task -->
