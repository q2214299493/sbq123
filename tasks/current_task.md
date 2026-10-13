<!-- state-handoff:start current_task -->
# Current Task

## Objective

Monitor the fifteen authorized Fe110 C2 adsorption/coadsorption VASP relaxations and review final chemistry/convergence before automatic eligible-result registration.

## Current Evidence Snapshot

- All15 GPU returned structures reviewed;12 target graphs intact and surface-symmetry nonduplicate;06_A/06_B predicted CO+C+H and09_B predicted CH2+CO retained by explicit user selection.
- All15 unchanged routine_production input preflights and current SUBMIT_VASP gates pass;32 MPI ranks/max32 per node;SIGMA0.20;NSW300;no added pilot.
- Canonical executor submitted real LSF jobs9848799-9848813 to sunboquan-codex;exact bundle/POTCAR verification and immutable receipts exist.
- First live snapshot:06_A/9848799 RUN,other14 PEND;queue status only. Electronic/ionic convergence and final VASP chemistry not yet assessed.
- Submission-only canonical registry batch applied for all15;no result energies accepted. Original CPU/GPU inputs and outputs retained.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Check these15 jobs with one bounded live scheduler/output checkpoint, separating queue,electronic,ionic and geometry state;do not repeat submission.

## Submission Boundary

User authorized this exact15-job batch only;no automatic retry,stop,new calculation,model promotion or final energy acceptance.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- All15 jobs have truthful terminal scheduler and electronic/ionic evidence.
- Final structures are reviewed for species/sites/duplicates and compatible VASP energies are automatically registered only when eligible.

## Constraints

- Retain the3 changed-chemistry inputs under reviewed coadsorbate labels rather than pretending original target graphs are intact.
- GPU predictions are not accepted DFT data;final VASP chemistry and convergence control registration.

## Authoritative References

- configs/execution_backends.yaml
- modules/adsorption_workflow/README.md
- modules/calculation_registry/README.md
- docs/reviews/fe110_c2_06_10_vasp_submission_20261013.md
<!-- state-handoff:end current_task -->
