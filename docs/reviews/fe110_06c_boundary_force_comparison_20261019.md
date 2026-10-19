# 06_C actual ML failure boundary: exact-force comparison

## Outcome

Original AQCat25 and frozen2185 were freshly evaluated on the same three
unchanged POSCARs as VASP9896148/9896149/9896150. Pooled adsorbate force-vector
RMSE improves0.269503→0.228471 eV/A (15.225%). This is not a uniform improvement:
C46 becomes worse immediately before and after persistent graph loss,and the
final ML stationary candidate is not stationary on the DFT force field.

| Saved frame | Original adsorbate vector RMSE | Frozen2185 | Frozen2185 max adsorbate error |
| --- | ---: | ---: | ---: |
| before003 | 0.232212 | 0.177792 | 0.234470 |
| after004 | 0.296110 | 0.254448 | 0.383298 |
| final057 | 0.276209 | 0.245445 | 0.298920 |

All force/error units are eV/A. Vector RMSE is
`sqrt(mean_atoms(sum_xyz((F_ML-F_DFT)^2)))`,not component RMSE or a difference
between two scalar fmax values. Fixed Fe0–17 are excluded from aggregate
metrics;all raw49-atom force vectors remain preserved.

## Per-atom vector errors

Indices are zero-based. Each cell is original AQCat25 → frozen2185,in eV/A.

| Frame | C45 | C46 | O47 | H48 |
| --- | --- | --- | --- | --- |
| before003 | 0.243426 → 0.166958 | 0.121081 → 0.234470 | 0.356113 → 0.181226 | 0.122296 → 0.103659 |
| after004 | 0.252256 → 0.152527 | 0.234895 → 0.383298 | 0.476122 → 0.290640 | 0.072275 → 0.065731 |
| final057 | 0.254403 → 0.283901 | 0.258070 → 0.258372 | 0.409570 → 0.298920 | 0.078085 → 0.065305 |

Pooled C vector RMSE becomes0.232396→0.258324,whereas O improves
0.416836→0.262468 and H improves0.093590→0.080272. Movable Fe is essentially
unchanged/slightly worse:0.122765→0.123324. Thus the overall improvement is
mainly oxygen/hydrogen improvement,not general carbon/local-Fe improvement.

At final057,fresh candidate movable fmax is0.093003 eV/A but compatible DFT
fmax is0.337048 eV/A. This establishes a force/stationarity mismatch at that
particular saved structure;it does not establish that the fragmented chemical
basin has no DFT minimum.

## Bond-direction diagnostic

For the exact structures,compute
`Q_ij=0.5*(F_j-F_i).unit(r_j-r_i)` with minimum-image coordinates. Positive Q
does positive work under an equal/opposite virtual bond stretch;negative Q
opposes that virtual stretch. This is not a mass-weighted acceleration,a full
reaction coordinate,or proof of the cause of an optimization trajectory.

| Frame / pair | DFT Q | Original Q | Frozen2185 Q |
| --- | ---: | ---: | ---: |
| before003 C46–O47 | -0.229112 | -0.058325 | -0.061829 |
| after004 C46–O47 | -1.845169 | -1.577027 | -1.584599 |
| final057 C45–O47 | -0.292519 | 0.015468 | -0.027053 |
| final057 C46–O47 | -0.026043 | 0.048231 | 0.037494 |

At3/4,both models reproduce the sign opposing virtual C46–O47 stretching but
underestimate its magnitude. It is therefore incorrect to claim that these
two isolated force evaluations prove ML simply pushes that bond apart while
DFT does the opposite. At final057,the candidate greatly underestimates the
C45–O47 restoring projection,and the much smaller C46–O47 projection has the
opposite sign. These local discrepancies support targeted diagnosis,not a
single proven failure cause. C45–H48 and all other values remain in machine
outputs. Small-force directional cosines are not hard acceptance criteria.

## Label and execution verification

All three authoritative LSF records are DONE. Full original OUTCAR,OSZICAR,
CONTCAR and inputs were copied without overwriting the original package and
their hashes verified against a read-only remote manifest. Canonical parsers
confirm normal completion,EDIFF convergence at71/75/75 cycles,finite complete
49×3 forces and no fatal keywords. The raw force-table coordinates agree with
the exact POSCARs within their original printing precision;cell,order,fixed
mask and static final coordinates are unchanged. Actual remote POTCAR hashes
match the frozen Fe/C/O/H source. Inputs remain SIGMA0.20,NSW0,IBRION−1 and
the existing compatible Fe45 branch. No ionic convergence is required for
these force-only static labels.

Final total magnetic moments are105.346587,105.404564,105.769986 muB;all49 local
moments were retained. These three records do not establish absence of every
possible alternative magnetic solution.

The user separately authorized one three-structure/two-checkpoint GPU
inference batch. Remote preflight passed;actual model tensors for both
checkpoints ran on MZ73 GPU1 UUID
`GPU-450609b3-d1fd-ac33-d03a-79891be402da`,CUDA device0,PID2770826.
Producer exit0 covered2026-10-19 11:50:46–11:50:52 Asia/Shanghai (~6.58s).
This is direct process evidence,not a Slurm job or scheduler DONE state.
Nine returned files passed byte-hash checks. Fresh candidate forces agree
with the previously saved ML force components within4.67e-5 eV/A;only the
fresh exact-POSCAR predictions were used for this comparison.

Request SHA256:`c276ba6e46b2aa0e109c8fa9753c0ee2d4b838efd811b484a9bf4593d8b1835b`.
Baseline checkpoint:`e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50`.
Frozen2185:`33b615feef2860e744d67ba964a27d1b60b9be7abdc9e754d5e264c10e96b160`.
Review SHA256:`e1a2d952c4f7cf018542e7634ea3e47e814970bcd68be044941833f22bee4bd7`.

## Artifacts,tests and limits

Package:
`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_06c_force_comparison_20261019_v1/`.
`force_comparison_review.json` contains full grouped/per-frame metrics,bond
projections and worst atoms. `per_atom_force_errors.csv` contains294 distinct
structure/model/atom rows with original and predicted xyz forces,vector errors,
direction cosines and explicit fixed-atom flags. All pooled adsorbate RMSEs
were independently recomputed from that CSV and agree.

Compilation/import checks,focused Ruff and57 scoped tests passed;the new
static-kind adapter reuses the existing inference executor and does not invent
an XDATCAR for static labels. Raw statics and trajectory labels retain distinct
provenance keys. Test coverage includes geometry precision,force-table parsing,
immutable/source binding,scope expansion,CPU fallback rejection and bond-axis
PBC/sign checks. No full repository test suite was run. The analysis skill's
named report-quality-gate tool is unavailable;numeric/CSV/unit/provenance checks
above were used instead. No graph or image is required for this comparison.

The three intentionally selected related failure points are not pristine
heldout validation. Existing16heldout exclusions and24untrained frames are
unchanged. No training,checkpoint promotion,VASP calculation,accepted-energy
registration or quantitative acceleration claim occurred. The existing
near-relaxed-domain calibration thresholds are not automatically transplanted
into a hard training gate for these failed-trajectory structures.

Next recommendation: prepare a separately reviewable targeted carbon/local-Fe
force correction request with compatible adsorption replay and fixed validation
isolation. Further training requires separate user authority;three-point
improvement alone would not prove full optimization or VASP steps/time speedup.
