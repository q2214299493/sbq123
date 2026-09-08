# Archived history from Active Fe(110) CO Dissociation Test

- Source: `docs/02_CURRENT_STATE.md`
- Source SHA-256 before compaction: `f6eee7315643818ddd25c238bc18db07598db7ef48227fda1fdb2f603f8b71ed`
- Compaction event: `state-history-compacted-7ca5604cfc573d419007f891`

### Historical Evidence

- The user authorized one complete Topic-1 CO dissociation workflow on
  2026-07-18. The local root is
  `calculations/fe110_co_dissociation_neb_20260718`.
- IS is Topic-1 job `9558184` CO/top. FS is the lower-energy reviewed C*+O*
  structure from job `9622455`, mapped only by exact 3x3 surface translation
  and element/fixed-mask preserving Fe reordering. The mapped endpoint passes
  the structure and endpoint gates with C/O displacements `1.989/2.463 A` and
  C-O `3.237 A`.
- The whitelist has no transferable Fe(110) path; the Fe(211) Catalysis-Hub
  record is reaction-class evidence only, and no external structure or energy
  was imported.
- Matched-static jobs `9631646` (IS) and `9631647` (FS) completed normally,
  passed electronic/hash/geometry/compatibility gates, and are registered as
  accepted matched statics at `TOTEN=-371.99321585/-372.71083562 eV`. Their
  endpoint-only reaction energy is `-0.71761977 eV`; it is not a barrier.
- MZ73 AQCat25+BA-Sella job `737` returned successfully. Its uncalibrated
  predicted candidate has C-O `1.7503 A`, preserved atom order/cell/fixed
  atoms, and passed the work geometry gate. It is used only as an elongated-CO
  waypoint, not as an accepted TS or energy result.
- The initial three-image path failed the adjacent-image jump gate. The revised
  five-image ordinary no-climb job `9631737` reached step 86 but was stopped on
  2026-07-23 by the new path-quality evidence. C-O distances were
  `1.176/1.181/1.218/1.299/2.317/2.768/3.237 A`; the 03/04 gap persisted and
  increased while image 04 moved deeper into the product basin. Conditions
  B/C/D/E/G/H were true over repeated cycles. Image 02 also repeatedly
  exhausted `NELM=200`. Final projected NEB forces were
  `0.464035/0.320476/0.090064/0.241284/0.055847 eV/A`; no image met the
  ordinary-NEB force criterion.
- Required stopped-job evidence, `nebmovie.pl 1`, structures, input files,
  trends, and hashes are under
  `calculations/fe110_co_dissociation_neb_20260718/output/ordinary_neb_5img_stop_20260723_1311`.
  The path is classified `STOP_UNDERRESOLVED_PATH` with a higher-priority
  electronic remediation requirement. It cannot authorize CI-NEB, DIMER, TS,
  downhill, or a barrier.
- Image-02 diagnostic `9638221` was stopped prematurely after buffered output
  appeared stale; its final flush showed continued progress, so it remains
  failed process evidence rather than an SCF conclusion. Replacement
  diagnostic `9638230` is LSF `DONE`; its OUTCAR records normal completion and
  EDIFF termination with the same DFT basis, fresh charge, `ALGO=Normal`, and
  linear mixing. OSZICAR truncation/NUL padding cannot override that
  authoritative OUTCAR marker.
- The accepted replacement path has eight internal images and preserves the
  full IS/FS contract. Its C-O sequence is
  `1.176/1.181/1.218/1.299/1.750/2.000/2.317/2.768/2.970/3.237 A`;
  all adjacent maximum displacements are below `1.0 A`. The path passed
  structure review, `dist.pl`, and `nebmovie.pl 0`. It is ordinary no-climb
  input only, not a TS.
- Replacement one-step same-path pilot `9640399` is LSF `DONE`. All eight
  internal images passed normal completion, EDIFF, exactly one ionic step,
  path/POSCAR hashes, and production-input compatibility. Their final total
  moments are `105.0202-107.0277 muB`; no adjacent pair exceeds the `2.0 muB`
  magnetic-continuity warning threshold. Schema-v2 pilot evidence is stored in
  the production directory.
- Production ordinary no-climb NEB job `9640936` was stopped with explicit
  user authority on 2026-07-27 and is LSF `EXIT`. The current hash-bound
  authoritative decision was `STOP_UNDERRESOLVED_PATH`; `STOP_JOB` and
  `REBUILD_PATH` were the only allowed actions. At the final scheduler
  checkpoint all eight internal images had reached 203 ionic steps, remained
  electronically normal, and none met the ordinary-NEB force criterion.
  Images 05/06 persistently skipped the required `1.50-2.10 A` C-O interval:
  their final reviewed C-O distances were `1.408/2.765 A`, with the gap
  increasing over the last five sampled frames. Stopped-job evidence,
  `nebmovie.pl 1`, the authoritative gate decision, and endpoint checks are
  under
  `calculations/fe110_co_dissociation_neb_20260718/output/ordinary_neb_8img_stop_20260727_1223`.
  The accepted IS/FS and NEB 00/09 endpoints pass geometry, fixed-mask,
  atom-order, and mapping checks; the blocker is the underresolved path, not
  endpoint corruption. CI-NEB, DIMER, frequency, downhill, and barrier
  promotion remain unauthorized.
- The user authorized a local IDPP rebuild on 2026-07-27. The new full-IS/FS
  candidate at
  `calculations/fe110_co_dissociation_neb_20260718/path/rebuild_segmented_idpp_12img_20260727`
  has 12 interior images and uses only the accepted endpoints plus the reviewed
  `C-O=2.0 A` geometry waypoint. Minimum-image C-O distances progress through
  `1.491/1.620/1.792/2.000/2.138 A`, but a raw-coordinate audit found periodic
  branch changes at 06/07 and 12/13. These create spurious whole-cell Fe motion
  in XYZ/Jmol despite physical per-step Fe motion below `0.041 A`. Reject this
  candidate for submission and rebuild it on one continuous coordinate branch.
  `dist.pl`, `nebmovie.pl 0`, human review, VASP input preparation, and
  submission remain pending and unauthorized.
- The corrected local candidate at
  `calculations/fe110_co_dissociation_neb_20260718/path/rebuild_segmented_idpp_12img_continuous_20260727`
  sequentially unwraps all images onto one minimum-image branch and copies the
  bottom 18 fixed Fe coordinates exactly from image 00. It has zero periodic
  branch changes, maximum raw fractional/Cartesian steps of
  `0.04217/0.30866 A`, endpoint geometry errors below `1.3e-11 A`, and a
  `PASS` geometry verdict. The user approved this exact path for submission on
  2026-07-27. `dist.pl` and `nebmovie.pl 0` completed, and the contract-bound
  14 POSCAR files are byte-identical to the approved candidate.
- Both local input preflights passed for a one-step ordinary no-climb NEB
  pilot. LSF rejected the first NP=192 request before job creation because it
  exceeded the account's job-slot limit. The identical path was re-gated with
  NP=96 (`12 images x 8 ranks/image`) and submitted through the sole executor
  as job `9645737` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/ordinary_neb_12img_continuous_idpp_pilot_np96_20260727`.
  The job was `PEND` at the 2026-07-27 16:10 checkpoint. Local/remote input
  hashes and the locked POTCAR hash agree. Production NEB must wait for this
  exact-path pilot gate; CI-NEB, DIMER, frequency, downhill, and barrier
  promotion remain unauthorized.
- The user subsequently rejected the projected 12-image ordinary-NEB/CI-NEB
  cost and authorized a local reduction to nine internal images. The candidate
  at
  `calculations/fe110_co_dissociation_neb_20260718/path/plan_continuous_idpp_9img_cost_reduced_20260727/path_candidate`
  retains source images `02,04,05,06,07,08,10,11,12` from the continuous
  12-image path. It preserves all five C-O points from `1.491` through
  `2.138 A`, has maximum adjacent displacement `0.617189 A`, no raw periodic
  branch change, exact fixed-Fe coordinates, and a `PASS` geometry verdict.
  `dist.pl` and `nebmovie.pl 0` completed. Standard XYZ, the complete POSCAR
  path, geometry CSV, and a zipped review package exist locally.
- The user explicitly selected the complete nine-image path for a one-step
  trial and authorized cancelling the queued 12-image pilot. Hash-bound
  scheduler and user-authorization evidence produced `STOP_USER_REQUESTED`;
  the sole executor cancelled job `9645737` from `PEND`, and LSF confirmed
  `EXIT` before it ran. Nine-image `NSW=1` pilot job `9646067` was submitted at
  NP=72 under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/ordinary_neb_9img_cost_reduced_pilot_np72_20260727`
  and was stopped at the user's request after image 07 was rejected. A current
  file-bound authorization and scheduler evidence produced
  `STOP_USER_REQUESTED`; the sole executor stopped the job and LSF confirmed
  `EXIT`. No ionic step completed, all CONTCAR files remained empty, and
  `nebmovie.pl 1` consequently failed; force and relaxed-path checks are
  unavailable.
- The stopped pilot shows that the omitted source image 09 caused the critical
  image 06->07 O displacement to be `0.617189 A`, with C-O
  `2.137821 -> 2.514489 A`. Image 07 also independently suffered a magnetic
  SCF instability: its last electronic-step energy change was `0.28618 eV`
  and its last-12 magnetization span was `35.56 muB`; the other eight internal
  images reached last-step energy changes below `1e-5 eV`.
- The preferred paused repair is the existing ten-internal-image candidate
  `path/plan_continuous_idpp_10img_cost_reduced_20260727/path_candidate`.
  Restoring source image 09 makes image 06/07/08 C-O
  `2.137821/2.311849/2.514489 A`, limits both adjacent O steps to about
  `0.309 A`, and changes Fe36-O continuously
  `2.133/2.386/2.652 A`. Its refreshed geometry diagnosis is `PASS`; the
  bottom 18 Fe are exact.
- The user authorized only the sequential repaired-image 07 then image 08
  `NSW=0` electronic-branch preflight on 2026-07-28. Image 07 passed geometry,
  INCAR, generic-input, and executor preflights. Its current gate allows only
  `SUBMIT_DIAGNOSTIC_VASP`; job `9646608` was submitted at 32 cores and is
  running under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/repaired_10img_image07_08_scf_branch_20260728/image07_static_seed`.
  Local/remote inputs and the locked POTCAR hash match. The sequential rule
  required image 07 `DONE`, normal completion, EDIFF, stable magnetization,
  and non-empty CHGCAR/WAVECAR before image 08. No whole-path NEB was
  authorized by this diagnostic.
- Image-07 job `9646608` subsequently finished `DONE` and passed all sequential
  gates: normal completion, no fatal output, DAV-62 EDIFF convergence,
  final total magnetization `105.3424372 muB`, last-12 span
  `0.3493404 muB`, reference difference at most `0.1743628 muB`, unchanged
  exact structure, and non-empty hash-bound CHGCAR/WAVECAR. Repaired image 08
  then passed its structure, INCAR, two input preflights, restart hashes, and
  current diagnostic-submission gate. The sole executor submitted job
  `9646670`; remote VASP confirms that the image-07 WAVECAR is being read.
  Image 08 remains diagnostic-only and no whole-path NEB is authorized.
- Image-08 job `9646670` subsequently finished `DONE` and passed all diagnostic
  gates. It reached `EDIFF=1E-5` at DAV 24, normally completed without fatal
  output, and ended at `105.4450488 muB`; its last-12 magnetization span is
  `0.0570777 muB` and its stable-neighbor reference difference is at most
  `0.0754488 muB`. The exact structure is unchanged within `8.2e-14 A`;
  C-O/C-Fe/O-Fe are `2.514489/1.777337/1.664289 A`, and the final CHGCAR and
  WAVECAR are non-empty and hash-bound. The image-07->08 electronic-branch
  preflight is complete. These statics do not authorize a whole-path NEB.
- The user then authorized one full-path test of the repaired ten-internal-image
  candidate. Its refreshed geometry, `dist.pl`, `nebmovie.pl 0`, INCAR,
  strict generic-input, executor-preflight, and hash-bound execution gates all
  passed. Ordinary no-climb `NSW=1` pilot job `9647154` is running at 80 cores
  under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/ordinary_neb_10img_repaired_branch_pilot_np80_20260728`.
  Only image 07/08 contain their validated WAVECARs; runtime OUTCAR evidence
  confirms `ISTART=1` there and `ISTART=0` on all other internal images. This
  job is diagnostic-only. Formal ordinary NEB, CI-NEB, DIMER, frequency, and
  barrier reporting remain forbidden pending the complete pilot verdict.
- A separate user-authorized, cost-neutral reconstruction of stopped 203-step
  job `9640936` replaced only images 03-06, retaining eight internal images.
  Exact stopped-job structures were pulled and source/local hashes agree. The
  constrained segmented-IDPP segment is anchored by stopped images 02/07 and
  gives C-O `1.376600/1.656190/2.000000/2.325773 A`; its central maximum
  adjacent displacement is `0.648845 A`, with all 18 fixed Fe exact.
  `dist.pl` and `nebmovie.pl 0` completed under
  `path/rebuild_old203step_central4_20260728/path_candidate`. The full
  candidate remains `REVIEW`, because the unmodified old image 07->08 still
  moves O by `1.251678 A` and changes its Fe adsorption coordination. This
  candidate is not authorized for VASP submission.
- Repaired ten-image `NSW=1` pilot job `9647154` is LSF `DONE`, but every
  internal image exceeds the `1.5 eV/A` force gate; image 01 has the largest
  latest atomic/NEB forces at `9.795983/13.250641 eV/A`. It cannot authorize a
  production NEB. The user instead authorized an independent local-stability
  relaxation of the old 203-step image 07 as a `TS_ENDPOINT`. Its starting
  geometry passes with C-O/C-Fe/O-Fe `2.7033/1.7589/1.7998 A`, 18 fixed Fe,
  and no collision. Endpoint validation retains large-migration/surface-motion
  warnings but has the intended C-O break, no unexpected bond/site changes,
  and only reviewed Fe-C/O site-coordination changes. Exact
  `routine_production.endpoint_relaxation` inputs passed generic and strict
  preflights; all remote input and approved POTCAR hashes match. Job `9647798`
  is LSF `DONE` at 32 cores under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/ts_endpoint_local_product_img07_relax_20260728`.
  It completed normally in 61 ionic steps, met final EDIFF at iteration 9/200,
  reached the ionic stopping criterion, and ended at maximum force
  `0.016035 eV/A` without fatal output. Its final C-O distance is `3.1131 A`,
  with C at long bridge and O at a local hollow. The fixed 18 Fe remain exact,
  mobile Fe motion is local, and the full trajectory has no coordinate jump
  or independent O-site hop. Post-relaxation endpoint validation has no
  missing/unexpected bond or site event and assigns all Fe-C/O changes to
  expected site coordination. Mandatory displacement warnings remain, so this
  is a locally stable `TS_ENDPOINT` candidate, not yet an approved production
  NEB endpoint. Full IS-to-candidate path connectivity is the remaining gate.
- The shortened seven-internal-image IS-to-local-endpoint candidate at
  `path/plan_shortened_local_endpoint_7img_20260729/path_candidate` now passes
  geometry and accepted side/top/`dist.pl`/`nebmovie.pl 0` review. C-O is
  monotonic from `1.175632` to `3.113136 A`, the maximum adjacent single-atom
  displacement is `0.924950 A`, and the fixed 18 Fe remain exact. The user
  authorized submission on 2026-07-30. A compatible endpoint `NSW=0`
  matched-static prerequisite was submitted through the sole executor as LSF
  job `9649924` at 32 cores under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/local_endpoint_matched_static_9647798_20260729`.
  It is `DONE`, normally/electronically converged at step `78/200`, has final
  TOTEN `-372.63138838 eV`, and preserves the static structure within
  `7.8e-14 A`. It is registered as `accepted_matched_static`; repeated
  insertion is idempotent and foreign-key validation passes.
- The local-endpoint contract now binds accepted matched statics
  `9631646/9649924`. The contract-bound seven-internal-image path is
  byte-identical to the accepted candidate and passes refreshed geometry,
  `dist.pl`, `nebmovie.pl 0`, INCAR, and submission preflights. The sole
  executor submitted the 56-core `NSW=1` ordinary no-climb pilot as job
  `9650404` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/ordinary_neb_7img_local_endpoint_pilot_np56_20260730`.
  Local/remote root inputs, all nine POSCAR files, and approved POTCAR hashes
  match. Job `9650404` is LSF `DONE` after one ionic step, but the pilot fails:
  image 05 exhausted `NELM=200`, images 02-07 exceed the `1.5 eV/A` force
  warning threshold, and image 04 has the largest atomic/NEB force at
  `5.723840/8.589121 eV/A`. No production NEB is submitted.
- The original-POSCAR image-05 candidate under
  `path/local_repair_image05_between_04_06_20260731/path_candidate` remains
  preserved but is superseded and unsubmitted. The accepted low-cost
  replacement uses the electronically converged one-step `04/CONTCAR` and
  `06/CONTCAR` from job `9650404` as exact anchors and excludes the old
  nonconverged image 05. It is at
  `path/local_repair_image05_between_04_06_step1_20260731/path_candidate`.
  Full-system IDPP gives C-O `1.629904 -> 1.950039 -> 2.322951 A`;
  `dist.pl` is symmetric at `0.694506/0.694506 A`, fixed Fe remain exact, and
  geometry plus reviewed `nebmovie.pl 0` checks pass. The sole executor
  submitted the authorized one-internal-image, 32-core, `NSW=1` ordinary
  no-climb micro-NEB diagnostic as LSF job `9651766` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/local_micro_neb_image05_step1anchors_pilot_np32_20260731`.
  It is now LSF `DONE` after one ionic step, with normal program termination
  and no fatal keyword, but the diagnostic fails. The internal image used all
  `NELM=200` electronic iterations, retained atomic/NEB force
  `2.783761/4.944003 eV/A`, and its total magnetization fell to about
  `65.68 muB` from the roughly `93-96 muB` neighboring branch. C-O remained
  continuous at `1.629904 -> 1.937835 -> 2.322951 A`; fixed Fe drift is
  negligible and minimum-image adjacent motion remains about
  `0.553/0.551 A`. VASP wrapped mobile Fe atoms 36 and 42 across the raw
  periodic coordinate branch, so the strict post-run geometry diagnosis is
  `STOP` until the output path is returned to one continuous branch. The
  corrected copy at
  `diagnostics/image05_micro_neb_recovery_20260731/postrun_continuous`
  now restores one continuous branch and passes the strict geometry check
  without changing minimum-image geometry. Electronic review also shows that
  anchors 04/06 ended at `106.5281/95.9363 muB`, whereas the new image 05
  collapsed to `65.6843 muB`; the remaining blocker is magnetic/electronic
  continuity rather than a physical Fe jump. Custodian first produced a
  local-only `ALGO=Fast`, `NELM=300` recommendation under
  `diagnostics/image05_micro_neb_recovery_20260731/electronic_diagnosis`.
  The user explicitly reduced `NELM` to `200` and authorized continued
  testing. A fixed-geometry `NSW=0`, `ALGO=Fast`, `NELM=200` image-05
  electronic recovery test that saves CHGCAR/WAVECAR passed geometry, INCAR,
  diagnostic-static preflight, and the authoritative execution gate, then
  was initially submitted through the sole executor as LSF job `9652050` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/image05_static_electronic_recovery_fast_nelm200_20260731`.
  The user clarified that the intended test was the single-interior-image
  micro-NEB, not a static. Job `9652050` was therefore stopped through the
  hash-bound `STOP_USER_REQUESTED` gate and sole executor and is confirmed
  LSF `EXIT`. The corrected `IMAGES=1`, `NSW=1`, `ALGO=Fast`, `NELM=200`,
  32-core ordinary no-climb micro-NEB passed geometry, INCAR, review,
  preflight, and the authoritative `READY_FOR_NEB_PILOT` gate, then was
  submitted as LSF job `9652055` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/local_micro_neb_image05_step1anchors_fast_nelm200_pilot_np32_20260731`.
  All local/remote inputs, three POSCAR files, and POTCAR hashes match. Job
  `9652055` is now LSF `DONE`, but it failed before completing one ionic step:
  RMM reached the user-capped `NELM=200` with final `dE=-4.45E-3 eV`, no
  nonempty CONTCAR, and no complete atomic/NEB-force output. OUTCAR is not
  normally complete. The last electronic magnetization is about `84.93 muB`,
  still far below anchor 04 (`106.53 muB`). Together with the earlier
  `ALGO=Normal` failure, this proves that changing the cold-start algorithm
  alone does not recover the intended magnetic/electronic branch. This
  diagnostic is not a production NEB and cannot authorize one.
- The user authorized the lower-cost sequential branch-seeding scheme on
  2026-07-31. The fixed-coordinate image-04 high-spin seed uses `NSW=0`,
  `ALGO=Normal`, `NELM=200`, `ISTART=0`, `ICHARG=2`, and writes
  `CHGCAR/WAVECAR`. Image-04 job `9652224` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/image04_highspin_restart_seed_normal_nelm200_20260731`
  is LSF `DONE`, normally/electronically converged at DAV `58/200`, with final
  magnetization `106.5867362 muB` and last-12 span `0.1995683 muB`.
  POSCAR/CONTCAR positions agree within `9.1e-14 A`; nonempty CHGCAR/WAVECAR
  and all retrieved outputs match their remote hashes. The fixed-coordinate
  image-05 restart uses the accepted path image 05 with `ISTART=1`,
  `ICHARG=1`, `ALGO=Normal`, and `NELM=200`; structure, INCAR, restart files,
  diagnostic-static preflight, and the current hash-bound execution gate pass.
  The sole executor submitted 32-core LSF job `9652245` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/image05_highspin_restart_from_image04_normal_nelm200_20260731`;
  it is LSF `DONE`, normally/electronically converged at DAV `28/200`, and
  explicitly read the image-04 WAVECAR. Its final magnetization is
  `106.3166324 muB`, its last-12 span is `0.1023079 muB`, and its difference
  from image 04 is `0.2701038 muB`. POSCAR/CONTCAR positions agree within
  `8.4e-14 A`; nonempty CHGCAR/WAVECAR and all retrieved outputs match their
  remote hashes. The subsequent one-internal-image ordinary no-climb
  micro-NEB keeps the accepted 04-05-06 POSCARs byte-identical and adds only
  the validated image-05 restart files under internal image `01`. Geometry,
  fixed-Fe continuity, INCAR, accepted path review, submission preflight,
  restart hashes, and the current `READY_FOR_NEB_PILOT` gate pass. The sole
  executor submitted 32-core diagnostic LSF job `9652274` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/local_micro_neb_image05_step1anchors_seeded_normal_nelm200_pilot_np32_20260731`;
  all remote input, POTCAR, CHGCAR, and WAVECAR hashes match. It is LSF `DONE`
  after one ionic step, normally/electronically converged at DAV `23/200`,
  and explicitly read the image-05 WAVECAR. Final magnetization is
  `106.3703846 muB` with last-12 span `0.1560583 muB`; the electronic/magnetic
  branch-seeding objective therefore succeeds. Maximum atomic/NEB forces after
  this single requested step are `2.751293/4.624760 eV/A`, but this remains
  inside the allowed five-step startup window. `1.5 eV/A` is a warning line;
  path failure requires at least ten ionic steps of persistent non-decreasing
  high NEB force or accompanying independently verified geometry, periodic,
  or magnetic discontinuity. `NSW=1` cannot establish persistence. Raw DFT
  per-atom forces exceed `1.5 eV/A` only for Fe40,
  C46, and O47; the other 44 atoms are at or below that value. C-O moves only
  `1.950039 -> 1.938708 A`; image-01 maximum minimum-image displacement is
  `0.006878 A`, the fixed 18 Fe remain exact, and the path does not collapse.
  VASP writes Fe atoms 37 and 43 onto neighboring raw periodic branches, so
  the strict raw-coordinate geometry diagnosis is `STOP`; minimum-image steps
  remain continuous at `0.553118/0.550660 A`, identifying a representation
  wrap rather than physical Fe motion. The correct status is
  `ELECTRONIC_BRANCH_PASS_FORCE_TREND_NOT_ESTABLISHED`, not a high-force
  failure. No production NEB or downstream TS task is authorized by this
  one-step diagnostic alone.
- The user authorized the exact pilot-tested 04-05-06 local segment as a
  low-cost coarse ordinary no-climb NEB on 2026-07-31. The production input
  keeps all three POSCAR files byte-identical to job `9652274`, changes only
  `NSW=1 -> 50`, uses 32 cores, and initializes internal image 01 from the
  validated image-05 CHGCAR/WAVECAR. Geometry, INCAR, exact-path pilot reuse,
  submission preflight, restart hashes, and the current hash-bound
  `READY_FOR_ORDINARY_NEB_SUBMISSION` gate pass. The sole executor submitted
  LSF job `9652354` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/local_micro_neb_image05_step1anchors_seeded_normal_coarse_nsw50_np32_20260731`;
  all remote manifest files, POTCAR, CHGCAR, and WAVECAR hashes match. Its
  job is LSF `DONE` after exhausting `NSW=50`. It completed normally without
  fatal output; the final electronic cycle met `EDIFF=1E-5` at `8/200` and
  the final total magnetization is `106.159212 muB` with last-12 span
  `0.017003 muB`. Maximum atomic/NEB forces fell to
  `0.081380/0.175321 eV/A`; the last five NEB forces decrease monotonically
  with span `0.016572 eV/A`, so the low-force/electronic/magnetic criteria
  pass despite not reaching strict `EDIFFG=-0.05 eV/A`. The bottom 18 Fe are
  exact. However, final C-O distances across 04-05-06 are
  `1.629904 -> 1.308520 -> 2.322951 A`: image05 returned behind image04 and
  no longer lies between its anchors. Continuous-periodic-branch correction
  removes only the raw Fe36/42 wrap and leaves this `0.321385 A` physical
  reaction-coordinate backtrack unchanged. Hash-bound validation is
  `STOP_PATH_GEOMETRY_BACKTRACK`; no seven-image pilot or coarse NEB was
  submitted. CI-NEB, DIMER, frequency, and barrier reporting remain
  unauthorized.
- A new local-only seven-internal-image rebuild is accepted for input review
  at `path/rebuild_7img_seeded_image05_step1_20260801/path_candidate`. It keeps
  the contract-bound 00/08 endpoints, uses job `9650404` one-step CONTCARs for
  images 01-04 and 06-07, and replaces only image05 with the electronically
  validated high-spin one-step CONTCAR from job `9652274`; the rejected
  50-step image05 is excluded. C-O increases monotonically as `1.175632,
  1.180789, 1.205788, 1.350187, 1.629904, 1.938708, 2.322951, 2.704261,
  3.113136 A`. Geometry and all nine structure audits pass; maximum adjacent
  single-atom displacement is `0.924901 A`, all 18 fixed Fe are exact, and no
  raw periodic jump, collision, or independent O-site jump is present.
  `dist.pl`, `nebmovie.pl 0`, top/side review, checksum-bound path review, and
  reaction-contract binding pass.
- The user authorized the accepted path's exact-path low-cost pilot on
  2026-08-01. A 56-core ordinary no-climb `NSW=1` pilot was prepared at
  `runs/ordinary_neb_7img_seeded_image05_step1_pilot_np56_20260801`; the nine
  POSCARs remain the accepted path, and only image05 receives the validated
  high-spin CHGCAR/WAVECAR seed from job `9652245`. Geometry, structure,
  INCAR, input, restart, reaction-contract, and current hash-bound execution
  gates pass. The sole executor submitted LSF job `9653580` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/ordinary_neb_7img_seeded_image05_step1_pilot_np56_20260801`.
  Its scheduler state changed from `PEND` to `RUN`, using
  `32*gknew0221:24*gknew0433` and reached LSF `DONE`. All seven internal images
  completed one ionic step, terminated normally without fatal output, and met
  `EDIFF=1E-5` before `NELM=200` at DAV 55/69/68/58/18/89/148. Image05's
  OUTCAR confirms the supplied WAVECAR and initial charge density. The
  canonical pilot validator returns `PASS`, and the 32 retrieved structure,
  output, root-output, and post-run movie files match remote SHA-256 values in
  `pilot_output_manifest.json`. One-step NEB forces are
  `0.050897, 0.226061, 7.003637, 8.442591, 4.345470, 3.640410,
  0.672465 eV/A`; the high values remain startup warnings only. A separate
  continuous-periodic-branch diagnostic passes: C-O is monotonic from
  `1.175632` to `3.113136 A`, bottom 18 Fe are exact, and there is no physical
  periodic jump, endpoint collapse, or independent C/O site-coordination
  event. Magnetic continuity does not pass the current workflow requirement:
  image05->06 and image06->07 total-moment jumps are `4.5384` and
  `19.7585 muB`, ending at only `82.0736 muB` for image07. The formal magnetic
  rule remains a soft warning. The user clarified that this one-step evidence
  is not an independent blocker and authorized the coarse trend test.
  The first coarse submission, 56-core job `9654159`, remained `PEND`. At the
  user's request to double resources, a current `STOP_USER_REQUESTED` gate
  authorized the sole executor to terminate it; the scheduler now reports
  `EXIT`, and VASP never started. Since `script.lsf` is included in exact-path
  pilot compatibility, the completed 56-core pilot cannot authorize 112-core
  production. A same-path 112-core `NSW=1` pilot was prepared at
  `runs/ordinary_neb_7img_seeded_image05_step1_pilot_np112_20260801`; all nine
  POSCARs and the INCAR are byte-identical to the accepted 56-core pilot, with
  only `NP=112` changed. Geometry, input preflight, image05 job-9652245 restart
  hashes, and the current `READY_FOR_NEB_PILOT` gate pass. The sole executor
  submitted job `9654240` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/ordinary_neb_7img_seeded_image05_step1_pilot_np112_20260801`;
  it produced no complete ionic step: images 01-05 reached the electronic
  threshold, image06 showed repeated `BRMIX` and fatal `EDDDAV/ZHEGV` with
  runaway energies, and image07 exhausted `NELM=200`. The user then explicitly
  authorized stopping this failed pilot and running sequential fixed-coordinate
  image06-to-image07 electronic recovery. A current `STOP_USER_REQUESTED` gate
  authorized the sole executor; job `9654240` is now scheduler `EXIT`.
- Fixed-coordinate image06 recovery is submitted as 32-core diagnostic job
  `9654834` under
  `~/sbq/Fe110/ts/co_dissociation_topic1_20260718/image06_highspin_restart_from_image05_normal_nelm200_20260802`.
  Its POSCAR is byte-identical to exact-path image06, `NSW=0`, `IBRION=-1`,
  `ALGO=Normal`, `NELM=200`, and it uses the validated high-spin image05
  CHGCAR/WAVECAR from job `9652245`. Structure, INCAR, diagnostic preflight,
  restart hashes, remote inputs/POTCAR, and current diagnostic-submission gate
  pass. Job `9654834` reached scheduler `DONE`, but not normal VASP completion:
  DAV 30 shows an electronic `rms(c)` jump from `0.0359` to `15.3`, followed
  by `BRMIX`, subspace-matrix, and fatal `EDDDAV/ZHEGV`. No final force block
  exists and CONTCAR is empty. `image06_validation.json` is `FAIL`; image07,
  the 112-core pilot retry, and `NSW=50` coarse NEB remain blocked. No CI-NEB,
  DIMER, frequency, or barrier action is authorized.
- The active TS parameter policy fixes the Fe45 five-layer DFT basis, endpoint
  contract, PBE/PAW-PBE/400 eV/Gamma `5x5x1`, spin/MAGMOM, atom order, and
  constraint conventions across all DFT stages. Only approved stage-specific
  optimizer, convergence, image, frequency, and resource controls may vary.
  Final barriers require validated matched-static IS/TS/FS evidence and
  registration in `data/project_registry.sqlite3`.
