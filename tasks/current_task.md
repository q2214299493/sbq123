<!-- state-handoff:start current_task -->
# Current Task

## Objective

Resolve06_C actual ML failure-boundary force errors before choosing targeted adsorption adaptation;do not replace force/geometry evidence with a low ML fmax claim.

## Current Evidence Snapshot

- User authorized local preparation only. Three frozen58-frame ML-trajectory samples selected:before003,after004,final057. No optimization or remote calculation was run.
- First persistent C46-O47 graph change3→4 has distance1.703323→1.880522A;final57 is3.443902A. C45-H48 later leaves the graph at36→37;final57 C-H2.419268A. Graph cutoffs describe sampling,not physical reaction thresholds.
- All3 finite/noncollision/order/cell/fixed-mask checks and canonical diagnostic-static preflights pass;POSCAR coordinate round-trip delta1.78e-15A. Actual changed chemistry remains diagnosis-only,not accepted adsorption.
- Inputs reuse active force-label builder:PBE/ENCUT400/Gamma5x5x1/ISPIN2/SIGMA0.20/ALGOFast/EDIFF1e-6/NSW0/IBRION-1/LORBIT11/NPAR4,32ranks each;species-resolvedMAGMOM49 entries. Custodian read-only checks pass3/3 with no changes.
- 27same-order49-atom references audited;closest adsorbateRMSDs0.4148/0.3678/1.3548A;no near old-heldout match at0.20A warning. Existing24frames remain untrained;three new points are screened diagnostics,not independent heldout.
- 29targeted tests pass and two figures were visually inspected. DFT error,magnetic/SCF behavior,basin stability and VASP acceleration remain unmeasured;POTCAR live hash and submission gates still required.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Review the prepared06C_before_003/06C_after_004/06C_final_057 geometries and obtain separate exact-three-job VASP static submission authority;then require the current canonical diagnostic gate and live POTCAR hash before execution.

## Submission Boundary

PREPARED_NOT_SUBMITTED:zero remote uploads or GPU/VASP/training jobs. Local preparation is not user geometry acceptance,not SUBMIT_DIAGNOSTIC_VASP authority and not model promotion.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- ActualML failure-boundary exact-structure VASP forces are normal/electronically converged,complete and compatibility/hash-bound.
- Identical-POSCAR originalAQCat25/frozen2185 errors and key-bond force directions are reviewed before choosing targeted adaptation or a basin/geometry strategy.
- Any adopted acceleration is checked against compatible matched VASP steps/time and reviewed final chemistry.

## Constraints

- Preserve saved source frames,element order,cell,PBC and fixedFe0-17;no bond constraint or geometry repair in exact-force labels.
- Keep observed16heldout excluded from training/replay/epoch selection;existing24new-domain frames and all3new diagnostic structures remain untrained.
- No automatic VASP/GPU/training submission,default-model change,unreviewed DFT parameter adjustment or accepted-energy/database promotion.

## Authoritative References

- configs/execution_backends.yaml
- configs/true_fe110_production.yaml
- modules/adsorption_workflow/README.md
- docs/reviews/fe110_06c_failure_boundary_labels_20261018.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_06c_boundary_labels_20261018_v1/batch_request.json
<!-- state-handoff:end current_task -->
