# 06_C failure-boundary force labels: three structures for review

Status: **PREPARED_NOT_SUBMITTED**. The user's “可以” authorizes local selection
and input preparation, not GPU inference, VASP submission or another fine-tune.

## Selected structures

All atom indices and ML frame indices below are zero-based. Frame0 is the raw
seed, not the first VASP ionic step. Every structure is the unmodified saved
ML geometry, not a re-optimized candidate or an accepted adsorption minimum.

| Label | Saved ML frame | Purpose | C45–O47 / A | C46–O47 / A | C45–H48 / A | Min pair / A |
|---|---:|---|---:|---:|---:|---:|
| 06C_before_003 | 3 | Before persistent target-graph loss | 1.2721 | 1.7033 | 1.1435 | 1.1435 |
| 06C_after_004 | 4 | First persistent target-graph loss | 1.2891 | 1.8805 | 1.2160 | 1.2160 |
| 06C_final_057 | 57 | Final predicted CO+C+H geometry | 1.1866 | 3.4439 | 2.4193 | 1.1866 |

| Label | C45 nearest Fe (index; A) | C46 nearest Fe | O47 nearest Fe | H48 nearest Fe |
|---|---|---|---|---|
| before003 | 44;2.4619 | 43;1.7138 | 41;2.9595 | 39;2.6160 |
| after004 | 44;2.2017 | 43;1.6012 | 41;2.9658 | 44;2.6475 |
| final057 | 44;1.8270 | 41;1.7939 | 41;2.9573 | 44;1.7131 |

The existing covalent-radius graph first changes at3→4. This is a descriptive
sampling boundary, not a newly imposed physical bond-breaking threshold.
C46–O47 stays outside the original graph thereafter and reaches3.4439 A;
C45–H48 later leaves the graph at36→37. Selection retains both sides of the
first persistent change and the final error geometry instead of repeating the
complete optimization or assigning a TS to these frames.

Saved candidate ML movable fmax is3.5358,5.4497,0.0930 eV/A respectively.
These are predictions, not measured DFT errors. The short1.6012 A C46–Fe43
contact in after004 is retained as failure-diagnosis evidence, not approved as
a stable adsorption bond. All selected points pass finite/order/cell/fixed-mask
and noncollision checks. Changed chemistry is intentional diagnostic scope;
the fragmented final structure is not accepted into the adsorption database.

## Source and overlap checks

Source: `calculations/fe110_c2_adsorption_06_10_20261012/adsorption_validation_2185_20261018_v2/returned/output/candidate/06_C/seed/optimization.traj`.
The returned manifest binds the58-frame trajectory and final output; the
checkpoint and seed/failure records were rechecked. ASE POSCAR round-trip
maximum coordinate change is1.78e-15 A; atom order and fixed Fe0–17 remain intact.

Twenty-seven compatible, same-order49-atom existing frames were checked with
clean-slab symmetries, xy PBC and absolute height retained; no COM/Kabsch fit.
The closest existing-frame adsorbate RMSDs are0.4148,0.3678,1.3548 A. None is
inside the current0.20 A near-duplicate warning or near the old frozen heldout
set. These screened, intentionally related diagnostic points are nevertheless
not independent heldout samples. No training or replay ingestion is authorized.

The first local overlap-review attempt mistakenly included50-atom07_B and
stopped before creating the output directory. The composition/order filter was
corrected; no geometry or calculation result was changed and no job was run.

## Inputs and execution boundary

The repository `build_fe110_active_learning_force_label` builder generated all
three packages from `configs/true_fe110_production.yaml`. No historical INCAR
was copied and no parameter recovery was attempted.

- PBE/PAW-PBE,ENCUT400 eV,Gamma5×5×1,ISPIN2,Fe45 fixed-bottom18 branch.
- ISMEAR1,SIGMA0.20 eV,ALGO Fast,EDIFF1e-6,NELM200,LORBIT11,NPAR4.
- NSW0,IBRION−1: exact-structure static forces, not ionic optimization.
- Species-resolved MAGMOM:45×2.2 followed by four non-Fe zero moments.
- Each job32 MPI ranks; the shared launcher requests32 ranks per node.
- Only `sunboquan-codex`/LSF may execute. The existing Fe/C/O/H POTCAR source
  and hash are bound in the batch; its actual remote hash still needs recheck.

Canonical local diagnostic-static preflights passed3/3. INCAR Custodian ran
read-only3/3 with no blockers or changes; it grants no submission authority.
No files were uploaded and no GPU/VASP/training job was submitted.

Package: `calculations/fe110_c2_adsorption_06_10_20261012/adsorption_06c_boundary_labels_20261018_v1/`.
Each label directory containsPOSCAR,INCAR,KPOINTS,POTCAR.spec,script.lsf,
source-frame force evidence, input-profile record and local preflight.
Batch files include`selection_review.json`,`batch_request.json`,
`exact_prediction_plan.json`,`selected_structures.png`,`boundary_trajectory.png`.
The GPU prediction plan is local and non-executable; it binds original AQCat25
and frozen2185 for a later identical-POSCAR comparison, with no optimization.

## Required next step and uncertainty

Review these three geometries, then separately authorize exactly these three
VASP static jobs. Execution still requires a current hash-bound
SUBMIT_DIAGNOSTIC_VASP gate, POTCAR verification and duplicate protection.
No gate decision or user submission approval was fabricated during preparation.

After normal/electronically converged VASP completion, compare full per-atom
forces, force tails and C–O/C–H projected force directions on identical POSCARs.
The frozen2185 saved forces are preserved; fresh exact-POSCAR model inference
is separately authorized when needed. Only then decide whether a localized
model error warrants replay fine-tuning. Even good agreement at three points
does not prove the complete trajectory, basin stability, energy barrier or
VASP step/time acceleration. No hard zero-error training threshold is added.

## Tests

Python compilation/imports and targeted Ruff passed.28 related tests passed
(boundary selection/source integrity,VASP builders,INCAR Custodian), plus the
canonical static-preflight regression passed separately:29 tests total.
Both generated scientific figures were visually inspected. VASP SCF behavior,
DFT forces, magnetic convergence and actual runtime remain unverified.
