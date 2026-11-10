# C2 supplement closeout and CH+CO ordinary-NEB submission — 2026-11-10

## Reviewed adsorption outcomes

The ten previously submitted sources were collected as 100 files (364.84 MiB)
and checked against remote SHA256 values. Electronic convergence, final force
positions, chemistry, surface-aware duplicate matching and scheduler evidence
were reviewed separately. No adsorption job was restarted or added.

| Candidate / job | Ionic steps | Movable fmax, eV/A | Reviewed outcome |
|---|---:|---:|---|
| 05_S1 / 9963756 | 91 | 0.017214017 | Duplicate of accepted 05_cfg0, existing main row63 |
| 05_S2 / 9963757 | 109 | 0.016121469 | Accepted unique; scheduler UNKNOWN exception |
| 06_S2 / 9963758 | 9 | 5.195745889 | Previously user-stopped, native EXIT/TERM_OWNER; C-O cleavage |
| 07_S1 / 9963759 | 66 | 0.017839836 | Accepted unique; scheduler UNKNOWN exception |
| 11_S1 / 9963760 | 76 | 0.018809966 | Duplicate of accepted 11_B, existing row68 |
| 12_S1 / 9963761 | 49 | 0.017217893 | Accepted unique; scheduler UNKNOWN exception |
| 13_S1 / 9963762 | 294 | 0.018855685 | Accepted unique; native DONE |
| 14_S1 / 9963763 | 129 | 0.019235920 | Duplicate of accepted 14_B, existing row71; native DONE |
| 18_S1 / 9963764 | 300 | 0.077199763 | Normal end, electronically converged, not force converged; changed chemistry |
| 18_S2 / 9963765 | 113 | 0.015712324 | Accepted intact unique; native DONE |

The active deduplication evidence is `duplicate_review_v2.json`: 27 compatible
accepted final-energy references, including records whose workflow projection
is not literally `accepted`. Clean-slab symmetry and chemically constrained
atom mapping were used, not a free molecular Kabsch fit. The three matches have
adsorbate RMSD 0.055-0.075 A and compatible energy differences below 0.0015 eV.
The earlier ten-reference analysis is retained but superseded for this review.

### 18_S1 is a changed-chemistry, unfinished candidate

The intended `[CH]-O-CH3` C45-H48 distance changes from 1.26568 to 2.89281 A.
Final H48-Fe distances are 1.74696 and 1.78408 A: H48 adsorbs on the surface,
not into the vacuum. The other CH3 bonds remain intact. Its actual topology is
`[C]-O-CH3 + H*`; the largest final residual force is on C46. Exhausting 300
steps with 0.07720 eV/A does not establish a converged dissociation product.
Neither that product nor the original intact species is accepted from 18_S1.
18_S2 independently supplies an intact converged structure. No rerun is authorized.

### Scheduler-history exception is narrow and explicit

`bjobs -a -w`, `bhist -l` and `bacct -l` did not recover the old terminal
records for 9963757, 9963759 and 9963761. The user explicitly accepted these
three using complete hash-checked VASP evidence. They remain scheduler
`UNKNOWN`; no DONE/exit-code/runtime/accounting history is fabricated.
Inputs, structures, final TOTEN, SCF/force data and normal VASP termination
remain available. Scheduler disappearance alone is not scientific failure
or a reason to recalculate.

## Registry and workbook

The canonical scientific registry batch inserted 166 reviewed rows and made
12 workflow transitions. Independent readback checked all 166 rows, the ten
final workflow projections, SQLite quick_check and foreign keys.

Five canonical, separately approved Excel promotions wrote final compatible
OUTCAR TOTEN under `fe110_converged_toten_sigma0p20_v1`:

| Main row | Candidate / job | Final TOTEN, eV |
|---|---|---:|
| 76 | 05_S2 / 9963757 | -383.88718375 |
| 77 | 07_S1 / 9963759 | -388.02440744 |
| 78 | 12_S1 / 9963761 | -391.95801328 |
| 79 | 13_S1 / 9963762 | -391.18183549 |
| 80 | 18_S2 / 9963765 | -394.41627008 |

These are **not numeric adsorption energies**: compatible reference energies
are still missing and the Eads cells explicitly say so. E0 is not inferred.
Three duplicates and two ineligible sources were appended as metadata-only
rows31-35 of `已登记待接受`. Existing 780 cells retain their values, formulas,
styles and checked layout. Five promotion receipts and database rows match.
The owning Excel writer records promotions without changing the current
`accepted` workflow projection; no independent status backfill was performed.

Workbook: `outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx`.
Final SHA256: `767151bb3131ea002dba524d7998635ad6098c7f7e1b7911442e37545fd166b0`.

Evidence:

- `calculations/fe110_c2_site_supplement_20261106/final_review_20261110_v1/`
- `outputs/fe110_c2_completion_20261110_v1/verification.json`
- `docs/reviews/fe110_c2_completion_20261110_user_authorization.md`

## New CH* + CO* -> CH-C-O* calculation

Accepted endpoint jobs9839757/9842136 were reused with full compatible
SIGMA0.20 final-energy and mapping evidence. Zero-based roles are CH C45-H48,
CO C46-O47, forming C45-C46; the 49-atom order and bottom18 fixed Fe are retained.
The endpoint energy difference +0.65930803 eV is a reaction energy, not a barrier.

### Actual GPU execution and resolved device-selection failure

- MZ73 job12405: native FAILED/exit1 after 2:20. MatRIS actually used CUDA and
  converged the primary seven-image ordinary ML-NEB in60 steps. The subsequent
  AQCat25 guard failed before its predictions because the shared loader omitted
  the explicit CPU/CUDA selector. This is an engineering failure, not evidence
  that either model's force error exceeded a scientific threshold.
- The loader now passes `cpu=(device == "cpu")`. The primary path was retained;
  it was not rerun. Failed process/device evidence is preserved unchanged.
- MZ73 job12406: native COMPLETED/exit0 in17 seconds. Both MatRIS and AQCat25
  evaluated exactly the same seven returned structures with actual CUDA proof;
  zero NEB, relaxation or training steps. All54 returned files were hash-checked.
- MatRIS primary checkpoint is the original provider FeCOH checkpoint, not an
  unrelated O-H fine-tune. Model disagreement is a screening score, not calibrated
  uncertainty or DFT accuracy. No active-learning training was triggered.

### Work-reviewed VASP handoff

The primary ML path had a C-C sampling gap 2.313779 -> 1.458755 A. A full-atom
local IDPP point at 1.886229 A was inserted for the initial VASP seed, giving
eight total images00-07/six internal images. No direct Dimer handoff was made.
CH/CO preservation, fixed atoms, PBC, numerical geometry and actual top/side
views were reviewed. VTST `dist.pl` and `nebmovie.pl 0` ran. Native per-image
POSCAR.xyz outputs were concatenated byte-exactly into the compatibility
movie.xyz view; raw VTST movie and tool-source receipts are retained.

Owner input preflight and INCAR-custodian validation passed. The canonical
executor requires the local/remote leaf names to match and consumes the
canonical `submission_preflight.json`. Earlier local name/preflight failures
occurred before any reservation/submission; old bindings and failed preflight
were preserved, the current reviewed preflight published, and the existing
fresh binding consumed exactly once.

**LSF job9994246** submitted through the authoritative `SUBMIT_VASP` gate:

- `sunboquan-codex`, queue `Gkn_normal`.
- Remote `~/sbq/Fe110/ts/ch_co_to_chco_20261110/vasp_ordinary_neb_20261110_v1`.
- 96 MPI ranks,32/node,16/internal image,NPAR4; no pilot.
- Ordinary NEB,LCLIMB false,NSW300,EDIFFG -0.05 eV/A; unchanged production
  ENCUT400,Gamma5x5x1,ISPIN2,ISMEAR1,SIGMA0.20,ALGO Fast.
- Saved initial native state PEND; compact monitor found zero completed ionic
  steps. No electronic/force convergence, TS, frequency or barrier is accepted.

Two GPU jobs plus this VASP job were recorded in one canonical metadata batch:
60 rows, zero updates, zero accepted scientific results; full readback passed.

Evidence:

- `calculations/fe110_ch_co_to_chco_ts_20261109/gpu_20261110_v1/`
- `calculations/fe110_ch_co_to_chco_ts_20261109/gpu_fixed_path_audit_20261110_v2/`
- `calculations/fe110_ch_co_to_chco_ts_20261109/vasp_ordinary_neb_20261110_v1/`
- `calculations/fe110_ch_co_to_chco_ts_20261109/job_registration_20261110_v1/`

## Software checks and remaining boundary

- Syntax compilation:16 task-owned Python files passed.
- Ruff:changed shared calculator loader and its new device-selection test passed.
- Relevant tests:24 passed (device selection, dual-model ML-NEB, same-structure benchmark).
- Workbook original/final views were inspected; saved-file readback passed.
- No measured acceleration, final TS/barrier, adsorption Eads reference closure,
  new checkpoint or model promotion is claimed.
- One configured RSI invocation was blocked before model execution by a stale
  Codex executable path (WinError3). Zero model turns/actions/experiences were
  used; no automatic retry or runtime-policy change occurred.
- The final `repo-state sync --safe-only` reported the existing classification
  conflict for `sbq_catalyst_agent_workflow.egg-info/PKG-INFO`; managed state
  projection synchronization remains incomplete. No classification or managed
  task event was edited to bypass that conflict.

Next scientific step: inspect job9994246 at the next requested checkpoint and
review electronic convergence, per-image force trends and final path separately
from queue state. No CI/Dimer/frequency/retry is authorized by this report.
