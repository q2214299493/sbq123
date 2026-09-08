# Current State

State updated: 2026-08-27 CST. This file is a compact snapshot, not a history.
Detailed job maps and old decisions live in `tasks/current_task.md`, module
READMEs, and the provenance protocols.

## Active Scientific Branch

Active dataset branch: `true_fe110_5layer_5x5x1`.

- System: corrected true Fe(110), latest relaxed five-layer Fe45 clean slab.
- Fixed atoms: bottom 18 Fe fixed.
- Vacuum: about `15 A`.
- KPOINTS: Gamma `5x5x1`.
- Method: `GGA=PE`, PAW-PBE, `ENCUT=400 eV`.
- Fe-containing systems: `ISPIN=2` with correct `MAGMOM` count.
- Closed-shell gas molecules: `ISPIN=1`, no `MAGMOM`.
- Formal Fe(110) surface-state energy: final `OUTCAR` `TOTEN` from a compatible,
  converged `ISMEAR=1`, `SIGMA=0.20 eV` production/DIMER calculation;
  convention `fe110_converged_toten_sigma0p20_v1`. No separate single-point is
  required. Existing `SIGMA=0.10 eV` statics are optional legacy evidence.
- Do not mix this branch with old fake-Fe(110)/Fe(211)-like material, the old
  failed clean static, `7x7x1`, or any incompatible slab/kmesh branch.

## Transition-State Workflow

NEB, CI-NEB, and DIMER now form one V3 workflow owned by
`modules/transition_state_search/`. The required order is endpoint/mapping
guard, reaction fingerprint, transferable Grade-A template retrieval or
family-rule fallback, reviewed path initialization, NEB/CI-NEB, optional DIMER
refinement, TS validation, and explicit success/failure learning storage.
`scripts/neb_agent/` remains only the numerical backend. No TS calculation was
started or changed by this repository refactor.
The versioned registry is at schema version 8. TS validation is bound to
the source saddle, frequency/displacement evidence files, reaction contract,
atom map, and method branch; compatible final-energy barrier sets are stored separately.
The 2026-09-05 read-only registry check found four TS-validation records,
three barrier records and three Grade-A success-template records. These are
record counts, not a fresh scientific revalidation. Schema 8 adds immutable
strategy variants, attempts and reviewed outcomes in `ts_strategy_events`.
The local learning extension is documented in
`modules/transition_state_search/LEARNING.md`; no new TS or barrier is created
by this software upgrade.

The optional MatRIS ML-NEB -> standard Sella candidate branch is now connected
to the existing exact-structure VASP error and checkpoint-rerun workflow; see
`modules/transition_state_search/SELLA_BRANCH.md`. The default complete-path
NEB route and historical AQCat25 BA-Sella route remain available. This is a
local extension with a bounded MZ73 component smoke test completed as job 1509:
one existing 50-atom structure, 3 Sella steps, 12 model evaluations, producer
exit code 0. All four returned structures passed work-side hash/constraint/cell
and smoke-geometry checks. The optimizer did not converge within the 3-step
budget; no VASP, training or TS acceptance occurred. See
`outputs/matris_sella_smoke_20260905/work_review.json`. Full-loop performance
on the current Fe reaction remains unmeasured.

## AQCat25 Execution Backends

`configs/execution_backends.yaml` is the authority for backend roles and
handoffs. `BUCT(sbq)` / `MZ73` may run AQCat25 adsorption and TS-candidate
acceleration; `sunboquan-codex` alone may run VASP/VTST calculations.
Every GPU result must return through `work` for provenance, geometry, domain,
and owning-module review. Direct GPU-to-VASP transfer and automatic remote
submission remain forbidden.
The current AQCat25 checkpoint passes the bounded near-relaxed Fe45 adsorption
force calibration. This supports reviewed candidate ranking only; AQCat25
energies and forces are not reportable DFT results.
The TS/path domain remains `uncalibrated`, so AQCat25/BA-Sella path and saddle
candidates are prediction-only and cannot establish a TS, validation grade, or
barrier. MZ73 still lacks durable `sacct` terminal records; hash-bound producer
exit records remain mandatory process evidence, not scheduler authority.
The complete-path implementation includes an ASE ordinary ML-NEB / conditional
ML-CI-NEB runner, resumable image/state checkpoints, per-image energy/force/path
evidence, and a work-side accepted-review finalizer for the GPU Dimer-parent
manifest. The versioned runner was deployed to MZ73 and real-checkpoint Slurm
smoke job `1190` completed successfully with three images and one ordinary
ML-NEB step. Its returned manifest passes the work-side hash validator. The
structure review accepts the runtime/artifact chain but rejects this smoke path
for scientific use: H moves about `1.59 A` across each link and the only
internal image has C-H `1.906 A`, so the contract's `1.3-1.8 A` interval is not
resolved. It remains an unconverged, uncalibrated prediction and is not an
accepted Dimer parent, VASP path, TS, or barrier.
After explicit user authorization, resolved production candidate job `1191`
was submitted on MZ73 with the reviewed C-H `1.70 A` waypoint, nine total
images, ordinary ML-NEB up to 200 steps, and conditional `ML-CI=auto`. It is
currently a running uncalibrated GPU prediction; no VASP action is authorized.

The local work-side active-learning controller now also supports complete-path
rounds: deterministic peak/neighbor/rising/falling/anomaly selection, one
hash-bound batch of VASP force-label inputs, batch DONE-evidence ingestion,
aggregate exact-structure AQCat25/VASP force comparison, all-label force-only
fine-tuning input, and rerouting to a full ML-NEB path with a new checkpoint.
A separate fixed-path committee evaluator accepts at least three unique
checkpoints and reports per-image energy/force disagreement. The current
production inventory still has only one AQCat25 checkpoint, so no real
committee or calibrated uncertainty is presently available. These are local
implementation/test results only; no label, fine-tuning, committee, VASP, or
additional GPU job was submitted by this change.

The reviewed Fe-C-O-H dual-model routing now uses AQCat25 as the adsorption
primary and MatRIS as the TS-path primary. `scripts/dual_model_ml_neb.py`
implements MatRIS restrained preconditioning, mandatory restraint release,
ordinary/conditional climbing ML-NEB, and AQCat25 evaluation of the exact fixed
MatRIS path. Bounded MZ73 smoke job `1317` passed the executor and geometry
checks with nine images; it was intentionally limited to two steps per stage
and is not a converged path. Production staged-release job `1324` preserved a
converged, geometry-valid 17-image restrained snapshot but stopped at the first
half-strength release because O-H `1.1-1.8 A` coverage fell from three internal
images to two. The snapshot is a round-0 diagnostic source, not an MEP or Dimer
parent. The active-learning adapter now preserves `pre_12` as the last valid
point and `fail_12` as the first valid failure-boundary point, giving an
18-structure exact MatRIS/AQCat25 prediction batch. It supports a preferred
three-to-five-member same-architecture MatRIS committee, but the current
inventory lacks three production-accepted checkpoints, so this round uses the
explicit MatRIS-primary/AQCat25-audit/VASP-error fallback without an uncertainty
claim. Candidate sampling ranks available disagreement, novelty, TS/failure
proximity, and reaction-coordinate backtracking, then clusters and deduplicates
at most seven labels. Compatible `SIGMA=0.20 eV`, `NSW=0`, `LORBIT=11` VASP
packages require complete forces and magnetic evidence before training. The
18-structure fallback batch is deployed and preflighted on MZ73 but has not
been submitted. No active-learning calibration, new checkpoint, VASP job,
accepted TS path, or barrier is established yet.

## Active Transition-State Gate

<!-- state-handoff:start active-fe-110-co-dissociation-test-current-gate -->
### Active Gate - 2026-08-27 GPU Job 1327 Failed; Revised Path Design Required

- Held-out VASP jobs `9731537`-`9731543` are `DONE` and quality-passed; frozen MatRIS passed the six-structure primary held-out gate, while AQCat25 remains a force/geometry auditor.
- MZ73 job `1327` produced exit code `1` during restrained preconditioning step `9`, before ordinary MatRIS ML-NEB and before the AQCat25 fixed-path audit.
- The required forming O-H `1.1-1.8 A` coverage fell from five to two internal images; at least three were required, so the geometry guard correctly stopped the run.
- O-H monotonicity, C1-C2 preservation, adjacent RMSD, maximum movable-atom step, minimum pair distance, and periodic-branch checks still passed.
- No complete GPU path, Dimer parent, VASP result, TS, barrier, fine-tuning, automatic retry, or resubmission exists.
- The completed seven-job VASP batch remains accepted held-out evidence; job `1327` is a separate failed GPU path attempt and does not invalidate that batch.

Next action: Prepare and review a revised preconditioning or resampling design that preserves at least three O-H interval images; require new explicit authorization before any rerun.
<!-- state-handoff:end active-fe-110-co-dissociation-test-current-gate -->

### Historical Evidence

The detailed chronology through the current gate was moved intact to `docs/history/active_fe110_co_dissociation_history_through_20260803.md`.

Current status and the next executable action are maintained only in the managed Current Gate above.

## Legacy Accepted Fe(110) Clean Static

Remote directory:
`sunboquan-codex:~/sbq/Fe110/adsorption/step12A/clean_static_v2`

- Accepted optional clean static: job `9574228`; it is not the active formal
  `SIGMA=0.20 eV` energy source after the 2026-08-07 convention change.
- Status: `DONE`, terminal, electronically converged, no detected fatal error.
- Energy: `TOTEN=-355.25046804 eV`.
- Branch: latest Fe45 slab, Gamma `5x5x1`, `ISPIN=2`, `ENCUT=400 eV`,
  `EDIFF=1E-6`, `ISMEAR=1`, `SIGMA=0.10`, dipole correction disabled.
- Replaces old invalid clean static `9558183`, which is rejected due unstable
  dipole correction and unphysical positive energy.

## Accepted Molecular/Gas Bases

Current accepted bases:

- H2 `9573527`
- CH `9573528`
- CH2 `9573529`
- CH3 `9573530`
- CH4 `9573531`
- H2O `9558015`
- CO `9733110`; `TOTEN=-14.81006485 eV`
- H `9733111`; doublet, `TOTEN=-1.11577066 eV`
- O `9733112`; triplet, `TOTEN=-1.55305836 eV`
- OH `9733121`; doublet continuation of incomplete-output job `9733113`,
  `TOTEN=-7.55587900 eV`
- C `9733114`; triplet, `TOTEN=-1.28003671 eV`
- CHO/formyl `9606863`
- CH2O/formaldehyde `9606864`
- CH3O/methoxy `9606865`
- CH4O/methanol `9606866`

Additional isomer gas references:

- COH/hydroxymethylidyne `9606898`: accepted after convergence, connectivity,
  and spin review; `TOTEN=-15.24666450 eV`.
- CHOH/hydroxymethylene `9606899`: accepted after convergence, connectivity,
  and spin review; `TOTEN=-19.67547998 eV`.
- CH2OH/hydroxymethyl radical `9606900`: accepted after convergence,
  connectivity, and spin review; `TOTEN=-24.84965807 eV`.

Gas branch: cubic `20 A`, Gamma `1x1x1`, `GGA=PE`, PAW-PBE, `ENCUT=400 eV`,
`EDIFF=1E-5`, `EDIFFG=-0.02 eV/A`, `ISMEAR=0`, `SIGMA=0.05 eV`, with
species-appropriate spin branches.

## Fe(110) Step 12A Adsorption Baseline

Remote root:
`sunboquan-codex:~/sbq/Fe110/adsorption/step12A`

- CO, H, O, OH, H2O, and C Step 12A adsorption relaxations completed.
- Site-generation authority: `scripts/adsorption/build_fe110_adsorption.py`.
- Site contract: one `top`, `short_bridge`, `long_bridge`, and true
  three-top-Fe `hollow`; no midpoint hollow.
- Final-site audit summary:
  - CO: hollow start migrated to long bridge.
  - H/O/OH: four site classes remain distinct.
  - H2O: short/long/hollow starts all migrated to top-like final structures.
  - C: hollow start migrated to long bridge.
- On 2026-08-28, all 24 relaxations were hash-audited and registered: the
  existing CO/top record plus 23 historical backfills. Nineteen unique final
  structures have accepted compatible `SIGMA=0.20 eV` relaxation `TOTEN`
  values; five duplicate final-site relaxations remain provenance-only.
- LSF history has expired for the 23 backfilled jobs, so their scheduler job
  IDs and scheduler terminal states remain `UNKNOWN`; OUTCAR/OSZICAR evidence
  independently establishes normal completion and electronic/ionic
  convergence.
- Compatible direct isolated CO/H/O/OH/H2O/C references are now accepted and
  registered. The formal convention is
  `Eads=E(Fe45+X)-E(Fe45)-E(X_gas/atom)`; negative is exothermic. All 19 unique
  Step 12A structures now have accepted electronic adsorption-energy records
  (`-8.00140758` to `-0.32231988 eV`). These values contain no ZPE, entropy, or
  finite-temperature correction.
- OH job `9733113` was scheduler `DONE` but its authoritative OUTCAR truncated
  during the final ionic step, so its energy was rejected. Same-method
  continuation `9733121` from the final CONTCAR passed normal-termination,
  electronic, ionic/force, spin, and geometry gates; the failed evidence is
  retained.

## Fe(110) H2/CHx Adsorption Pilot

Remote root:
`sunboquan-codex:~/sbq/Fe110/adsorption/pilot_h2_chx_20260704`

Initial pilot jobs:

- H2 top/short bridge: `9573948`, `9573949`
- CH top/hollow: `9573950`, `9573951`
- CH2 top/hollow: `9573952`, `9573953`
- CH3 top/hollow: `9573954`, `9573955`
- CH4 top/hollow: `9573956`, `9573957`

Full-site expansion jobs:

- H2 long bridge/hollow: `9599348`, `9599349`
- CH short bridge/long bridge: `9599350`, `9599351`
- CH2 short bridge/long bridge: `9599352`, `9599353`
- CH3 short bridge/long bridge: `9599354`, `9599355`
- CH4 short bridge/long bridge: `9599356`, `9599357`

User-authorized targeted completion runs (remote root
`~/sbq/Fe110/adsorption/pilot_h2_chx_completion_20260713`):

- CH2 tilted hollow relaxation `9622444`: scheduler `RUN` with `NSW=300`.
  Its superseded five-step precursor is archived as provenance only. C remains
  true hollow; H-C-H is `109.459 deg`, the
  two C-H distances are `1.1393/1.1394 A`, and the H height difference is
  `0.3231 A`.
- CH3 top screen `9622414`: scheduler `RUN`, unchanged with `NSW=80`.
- All use the active Fe45/PBE/Gamma `5x5x1` branch, bottom 18 Fe fixed,
  `EDIFFG=-0.02 eV/A`, and `NPAR=4`; their input structures passed the relevant
  site classifier, geometry audit, and input preflight.

Latest scheduler checkpoint: `9622414` and `9622444` are `RUN`. Job `9622444`
has read `NSW=300` and started electronic iterations but
has not completed an ionic step. Completed structures still need convergence, final geometry,
and final static/result promotion review before becoming final adsorption-energy
rows.

Known geometry conclusions:

- H2 often dissociates to two-H coadsorption states; molecular long bridge is
  far from the surface and should not be treated as stable H2 adsorption without
  review.
- CH and CH2 retain C-H bonds; some hollow starts migrate to long bridge.
- CH3 structures collapse into near-duplicate hollow-class final states.
- CH4 is weakly bound or near-desorbed; do not promote without explicit review.

## Oxygenated Main-Species Fe(110) Adsorption Pilot

Remote root:
`sunboquan-codex:~/sbq/Fe110/adsorption/pilot_oxygenated_main_20260708`

Submitted orientation pilot:

- CHO_formyl_Cend top/hollow: `9606914`, `9606915`
- CHO_formyl_Oend top/hollow: `9606916`, `9606917`
- CH2O_formaldehyde_Oend top/hollow: `9606918`, `9606919`
- CH3O_methoxy_Oend top/hollow: `9606920`, `9606921`
- CH4O_methanol_Oend top/hollow: `9606922`, `9606923`

Latest evidence checkpoint:

- On 2026-07-12--13, OUTCAR evidence showed nine technically converged results:
  `9606914`, `9606915`, `9606917-9606923`.
- `9606916` finished normally and electronically converged but did not reach
  ionic convergence after 300 steps.
- On 2026-07-13, `9606923` is scheduler `DONE`; its OUTCAR contains one ionic
  convergence marker and one normal-completion marker. Final relaxation TOTEN
  is `-385.88708675 eV`.
- Final `9606923` geometry is intact O-end methanol: C-O `1.4510 A`, O-H
  `0.9802 A`, three C-H bonds `1.0964-1.1019 A`, O-Fe `2.1669 A` (nearest Fe
  42), C-nearest-Fe `3.2354 A` (Fe 42), and bottom 18 Fe remain fixed. The
  shortest non-bonded contact after excluding molecular bonds is `1.7923 A`.

Scientific checkpoint for `9606916` (`CHO_formyl_Oend/top`):

- Scheduler `DONE`, but no ionic `reached required accuracy`; stopped at
  `NSW=300`.
- C-O remains intact at about `1.1909 A`, while C-H is stretched to about
  `1.4521 A` and H is close to Fe at about `1.6781 A`.
- Largest final force is on H at about `0.2798 eV/A`.
- Current verdict: `NEEDS_REVIEW`; likely H-transfer/dehydrogenation tendency.
  Do not promote this as a converged `CHO_formyl_Oend/top` adsorption result.

This is not a full four-site screen. Monitor for C/O-end switching, eta2 C/O
contacts, C-O cleavage, H transfer, desorption, duplicate final sites, and
weak methanol binding.

## AdsMind Lite and Surface Expansion

Module: `modules/adsmind_lite/`.

- Fe(110) remains the robust benchmark.
- Fe(100) and Fe(111) metallic detectors exist as staged metallic Fe expansion.
- Carbide and oxide support is manifest-gated only; no automatic
  high-confidence export is claimed for complex carbide/oxide surfaces.
- Low-confidence or `needs_review` structures remain report-only unless the user
  explicitly overrides.

## Fe(110) C/C2/O 11-Candidate Relaxations

Deduplicated remote roots:
`sunboquan-codex:~/sbq/Fe110/adsorption/pilot_c_c2_o_20260714` and
`sunboquan-codex:~/sbq/Fe110/adsorption/pilot_c_c2_o_missing_20260714`.

- `9622455`: `C*+O*/C@lb+O@h_adj`.
- `9622456`: `C₂O*/κ-Cα/lb_tilted`.
- `9622457`: `C₂O**/η²(Cα,Cβ)/h-lb-h`.
- `9622458`: `C₂**/η²(C,C)/h-lb-h`.
- `9622459`: `C₂**/η²(C,C)/h-lb-h+O@lb_adj`.
- `9622460`: `C*+O*/C@lb+O@lb/adj`.
- `9622461`: `C₂O**/η²-CαCβ/C₂-2-derived`.
- `9622462`: `C₂**/η²-CC/C₂-2-diagonal`.
- `9622463`: `C₂**/C₂-1+O@h/adj`.
- `9622464`: `C₂**/C₂-2-diagonal+O@lb/adj`.
- `9622465`: `C₂**/C₂-2-diagonal+O@h/adj`.

All 11 use Fe45, bottom 18 Fe fixed, Gamma `5x5x1`, PBE/PAW-PBE,
`ENCUT=400 eV`, `EDIFFG=-0.02 eV/A`, and user-directed `NSW=300`. All finished
normally, reached the required-accuracy marker, and have final maximum movable
forces below `0.02 eV/A`. Final connectivity, site, and duplicate review passed:
two `C*+O*`, three `C2O*`, two `C2*`, and four `C2*+O*` unique relaxations.
The coadsorbed C/O sets did not form new C-O bonds. Relaxation TOTEN and
sigma-to-zero E0 values are registered as interim values only.

## Fe45 CARE Eight-Isomer Starting Set

Local review set: `calculations/fe110_care8_isomers_20260716`.

- Contains one CARE `RELAX_FIRST` pose for each of four C2H2O and four C3H2O
  exact molecular graphs; no fixed site sweep was added.
- CARE Fe48 poses were mapped through the local Fe(110) surface basis onto the
  verified Fe45 slab. All eight preserve source connectivity and bond lengths,
  retain 18 fixed Fe atoms, and pass the initial collision/height gate.
- Raw candidates remain unchanged. Reviewed local revisions exist only for 01,
  05, 07, and 08. The revised 01 and 07 remove their short H-Fe contacts; 05
  and 08 have stronger, more balanced intended C/O-Fe contacts. All four
  revisions preserve molecular connectivity and pass the initial geometry
  gate without warnings.
- CARE model values are provenance for source-pose ordering only. No CARE
  energy was imported into the registry or Excel.
- Only candidate 04 (`[CH][CH][O]`, accepted raw pose) and candidate 08
  (`[C]O[CH][CH]`, revised pose) continued to Fe45 relaxation with `NSW=300`.
  Jobs `9627284` and `9627285` use
  `~/sbq/Fe110/adsorption/care_selected_4_8_20260716`. Both are scheduler
  `DONE`, electronically and ionically converged, and registered. Job `9627284`
  preserved the intended `[CH][CH][O]` connectivity and passed. Job `9627285`
  cleaved the target C-O bond and is reclassified as `CO*+C2H2*`; it must never
  be labeled intact C3H2O. Candidates 01, 05, and 07 are revised locally but
  unsubmitted; 02, 03, and 06 are unchanged, including the raw 06 short-H-Fe
  warning.
- A failure-informed intact candidate-08 rebuild is local at
  `calculations/fe110_care8_isomers_20260716/rebuilt/08_C3H2O_XXNRTDXE_cfg0_intact_vertical`.
  It preserves `[C]O[CH][CH]`, anchors only the terminal CH carbon on a top Fe,
  keeps the other heavy atoms at least `3.02 A` from Fe, retains `10.28 A`
  effective periodic vacuum, and passes the structure gate without warnings.
  A second user-directed `h-lb-h`-like dual-end rebuild keeps C48 away from the
  surface while setting C46-Fe/C47-Fe/O49-Fe/C48-Fe to
  `2.10/2.10/2.21/3.20 A`; it also passes without warnings. The two `NSW=80`
  screening jobs are `9629858` and `9629859` under
  `~/sbq/Fe110/adsorption/care_c3h2o_rebuild_pair_20260717`. Both were `PEND`
  at submission on 2026-07-17 21:25 and both were `RUN` at 21:28. Neither has
  a stability claim.

## Registry, Excel, and Deduplication Gate

Current bottleneck: result tracking and deduplication, not just structure
building.

- Registry schema exists in `modules/calculation_registry/schema.sql`.
- The local database was transactionally migrated through schema v7. The v7
  migration added immutable workflow-status correction history; the pre-v7
  backup is
  `data/backups/project_registry_before_v7_step12a_20260828.sqlite3`.
- `data/project_registry.sqlite3` currently contains 128 calculations, 129
  jobs, 212 status events, 1,481 file records, 1,486 result fields, 246
  reviews, 70 compatibility records, 27 workflow-status history rows, and 22
  Excel-promotion receipts. Foreign-key and SQLite integrity checks pass.
- Jobs `9606918-9606923`, `9622414`, `9622444`, `9622455-9622465`, and
  `9627284-9627285` have current technical, geometry, chemistry, site,
  duplicate, energy, and promotion records.
- The Step 12A backfill originally recorded 18
  `reference_tuple_incomplete` unique states and five duplicates. After the
  compatible direct gas/atomic reference tuple was accepted, all 19 unique
  calculations received accepted adsorption energies and are now
  `workflow_status=excel_promoted`; the five duplicate final states remain
  provenance-only.
- The accepted CH+H frequency calculation and the accepted C+H DIMER/frequency
  calculations now consistently project `workflow_status=energy_accepted`;
  every correction retains its expected old status in immutable history.
- Under the 2026-08-07 policy, a compatible converged relaxation `TOTEN` may be
  formally accepted as `energy_accepted` under
  `fe110_converged_toten_sigma0p20_v1`. Existing registry rows remain at their
  recorded states until their scheduler, convergence, geometry, output-hash,
  and reference evidence is reviewed; missing references still block an
  adsorption-energy claim.
- On 2026-07-18, the canonical workbook
  `outputs/adsorption_topic1_20260702/课题一吸附_最终.xlsx` was updated in place
  from `A1:H53` to `A1:H55` with only jobs `9627284` and `9627285`. The first is
  the intact C2H2O `[CH][CH][O]` relaxation; the second retains C3H2O as its
  input provenance but is recorded by its actual final identity `CO*+C2H2*`
  after C-O cleavage. Relative energies remain blank and no second workbook
  version was created.
- On 2026-08-28, the canonical workbook remained one eight-column worksheet.
  Its legacy H-column same-species relative-energy field was migrated to
  `吸附能 Eads (eV)`, and the 19 unique Step 12A rows were populated from
  accepted registry results through a sequential workbook-hash chain. Rows 6,
  20, 21, 22, and 26 are duplicate final states and therefore remain blank in
  the Eads column. Nineteen SQLite/JSON promotion receipts and nineteen
  immutable `energy_accepted -> excel_promoted` status changes were recorded.
- Use `skills/chemical-plausibility-gate/` to assign final species, chemical
  event, and plausibility status before promotion.
- Use `skills/dataset-compatibility-gate/` before comparing energies, computing
  adsorption energies, promoting rows to Excel, or reusing endpoints.
- Machine-readable promotion rules live in
  `configs/adsorption_result_promotion.yaml`.
- Initial site is provenance only; final site class and duplicate status decide
  whether a structure becomes a distinct dataset row.

## Next Actions

1. Keep `9622414`, `9622444`, and `9606916` out of the workbook because ionic
   convergence or final chemistry remains unresolved.
2. Require a complete accepted reference tuple and an unpromoted registry ID
   before any additional adsorption row is written.
3. Do not submit replacement statics solely for energy promotion. Review the
   existing converged `SIGMA=0.20 eV` relaxation outputs and register only those
   that satisfy the active compatibility convention.

## Chemistry-Aware Adsorption Pre-Screen

- Candidate planning is now motif-first rather than a mandatory four-site
  sweep. The geometric Fe(110) site detector remains unchanged.
- External evidence is now a strict two-stage gate: approved whitelist first;
  authoritative-journal literature only after `NO_WHITELIST_MATCH`. A usable
  whitelist match forbids the literature stage.
- Candidate count equals the number of unique stable motifs supported by
  accepted evidence. There is no default 2/3/4-site cap or padding rule.
- External evidence is restricted to motif selection, stability ordering, and
  initial geometry references such as bond lengths and orientation. Its
  energies cannot enter local results, the registry, or Excel.
- H2O defaults to two O-bound top-like orientations because all four Step 12A
  starts relaxed into one top-like final site class.
- CHO/formyl prioritizes the user-reported side-on C/O dual-center `h-lb-h`
  hypothesis. Automatic construction is blocked until an exact reviewed
  structure template and provenance are registered.
- `CHO_formyl_Oend/top` is suppressed by default because job `9606916` exhausted
  `NSW=300` while showing H-transfer/dehydrogenation tendency.
- Pilot input preparation now defaults to an `NSW=80` screening stage.
  Continuation from `CONTCAR` requires scientific review;
  live jobs are never stopped automatically.
- Iron Fischer-Tropsch ranking now uses exact connectivity, carbon coordination
  demand, radical localization, oxygen functional role, steric accessibility,
  and Fe(110) row direction. Formula-only C/O anchor selection is rejected.
- User-reviewed calibration: CH2O uses eta2(C,O) then tilted O-top; COH uses
  C-long then C-short bridge with eta2 third; CHOH uses C-long bridge, eta2, and
  an H/OH orientation variant; CH2OH uses C-top, C-bridge, and eta2.
- These are pre-calculation ranking rules, not accepted global-minimum energies.
  Machine-readable authority: `configs/adsmind_lite/iron_fts_prescreen.yaml`.
- C2 extension now distinguishes `di_sigma_long`, `di_sigma_short`,
  `eta2(C,C)`, `pi-top`, terminal-radical C anchoring, C2 carbonyl modes, and
  neutral-alcohol O-top chain orientations. Multi-center structures remain
  blocked until reviewed templates exist.
- Hard scope: this complete motif/site-ranking rule is valid only for the active
  true Fe(110) branch. Fe(100), Fe(111), carbide, and oxide inputs are rejected
  with `fe110_only_rule_not_transferable`; no automatic transfer is allowed.
