# Fe(110) CO Dissociation Workflow

Current state: repaired ten-internal-image ordinary no-climb `NSW=1` pilot
job `9647154` is `DONE` but fails the force gate in every internal image.
Independent local TS-endpoint relaxation job `9647798` is `DONE` and provides
a locally stable endpoint candidate; full IS-to-candidate path connectivity
remains unvalidated. No production NEB or downstream TS calculation is
submitted.

Selected Topic-1 endpoints are job 9558184 CO/top and job 9622455 C/long-bridge + O/hollow. Both local CONTCAR hashes match the VASP server. The whitelist has no transferable Fe(110) path; an Fe(211) record confirms only the reaction class.

The raw lowest-energy product required an exact 3x3 surface-symmetry mapping to avoid combining dissociation with long-range diffusion. The mapped endpoint passes identity, fixed-layer, geometry, and displacement gates.

Matched-static jobs 9631646/9631647 completed, passed the result gates, and were registered at `TOTEN=-371.99321585/-372.71083562 eV`. The endpoint-only reaction energy is `-0.71761977 eV`; no barrier exists yet.

MZ73 job 737 returned an uncalibrated AQCat25+BA-Sella predicted candidate. It
passed the work return and geometry gates and was used only as the elongated-CO
waypoint. The five-image path was rejected after persistent underresolution. A
replacement eight-image path passed its input and pilot gates, but production
job 9640936 again evolved into an underresolved 05/06 gap after 203 ionic
steps. The user authorized stopping it on 2026-07-27; LSF confirmed `EXIT`.
The IS/FS and NEB 00/09 endpoints remain geometry- and mapping-valid. No CI-NEB,
DIMER, frequency, downhill, or barrier promotion is authorized.

The user authorized a local IDPP rebuild on 2026-07-27. A fresh full-IS/FS
segmented-IDPP candidate with 12 interior images is under
`path/rebuild_segmented_idpp_12img_20260727`. It uses only the accepted
endpoints and the reviewed `C-O=2.0 A` geometry waypoint, not relaxed images
from either failed NEB. Its minimum-image geometry samples the previously
missing `1.50-2.10 A` interval, but raw fractional coordinates change periodic
branches at images 06/07 and 12/13. Standard XYZ visualization therefore shows
spurious Fe translation. This candidate is not submission-ready and must be
rebuilt on one continuous periodic coordinate branch before `dist.pl`,
`nebmovie.pl 0`, human review, or input preparation.

The corrected candidate is under
`path/rebuild_segmented_idpp_12img_continuous_20260727`. Every image is
sequentially unwrapped onto one minimum-image branch, and the bottom 18 fixed
Fe coordinates are copied exactly from image 00. The rebuilt XYZ has no
periodic branch changes; the maximum raw fractional step is `0.04217`, the
maximum Cartesian step is `0.30866 A`, and the geometry gate is `PASS`.
The contract-bound path is byte-identical to this approved candidate.
`dist.pl`, `nebmovie.pl 0`, path approval, and both input preflights passed.
LSF rejected an NP=192 request before creating a job because it exceeded the
account job-slot limit. The unchanged one-step ordinary no-climb NEB pilot was
re-gated at NP=96 and submitted as job `9645737`. Production submission must
wait for the exact-path pilot result and a new authoritative gate decision.

The user then set calculation cost as a binding constraint and requested a
local nine-internal-image alternative. The candidate under
`path/plan_continuous_idpp_9img_cost_reduced_20260727/path_candidate` is an
exact subset of the continuous 12-image geometry, not a new endpoint
interpolation. It keeps source images `02,04,05,06,07,08,10,11,12`, so the full
critical C-O sequence `1.491/1.620/1.792/2.000/2.138 A` remains resolved while
only smoother regions are thinned. Geometry, fixed-Fe, periodic-branch,
`dist.pl`, and `nebmovie.pl 0` checks pass. The user then selected this exact
nine-image path for an `NSW=1` trial and explicitly authorized cancelling the
queued 12-image pilot. Job `9645737` was cancelled from `PEND` through the
hash-bound gate and is LSF `EXIT` without having run. Nine-image pilot
`9646067` was submitted at NP=72. The user then rejected image 07 and
explicitly requested a pause. The current hash-bound execution gate returned
`STOP_USER_REQUESTED` with only `STOP_JOB` allowed; the sole executor issued
the stop and LSF confirmed `EXIT`. No ionic step completed, so every CONTCAR
is empty and neither forces nor relaxed path geometry can be judged.

The input-path diagnosis shows that omitting source image 09 combined two
smooth O moves into one `0.617189 A` move at image 06->07. The existing
ten-internal-image candidate under
`path/plan_continuous_idpp_10img_cost_reduced_20260727/path_candidate`
restores that source image. Its image 06/07/08 C-O sequence is
`2.137821/2.311849/2.514489 A`, each adjacent O step is about `0.309 A`, and
Fe36-O lengthens continuously rather than changing site in one step. The
refreshed geometry gate is `PASS`.

The stopped SCF output also shows a separate electronic problem at the
`C-O=2.514489 A` geometry: the last electronic-step energy change was
`0.28618 eV` and the last-12 total-magnetization span was `35.56 muB`, while
all other internal images reached final electronic-step energy changes below
`1e-5 eV`. Therefore adding one image fixes structural continuity but does not
by itself prove electronic convergence. No whole-path or formal NEB is
authorized. The next calculation, only after separate user authorization,
should be a low-cost exact-geometry static branch-continuation preflight for
the repaired image 07/08 pair.

The user authorized that sequential preflight on 2026-07-28. Repaired image
07 passes the structure, INCAR, generic-input, executor-preflight, and current
execution-gate checks. The sole executor submitted 32-core `NSW=0` diagnostic
job `9646608`; remote input and POTCAR hashes match. It is a cold high-spin
start that saves CHGCAR/WAVECAR. Image 08 remains unsubmitted until image 07
proves normal completion, EDIFF, magnetic stability, and usable restart files.
This authorization does not include a whole-path NEB.

Image-07 job `9646608` finished `DONE` and passed: normal completion, no fatal
output, EDIFF at DAV 62, final total magnetization `105.3424372 muB`,
last-12 magnetization span `0.3493404 muB`, unchanged structure, and valid
hash-bound CHGCAR/WAVECAR. Repaired image 08 then passed all local input,
structure, restart-hash, and gate checks. The sole executor submitted
restart job `9646670`, and VASP confirms `found WAVECAR` followed by
`reading WAVECAR`. No whole-path NEB has been submitted.

Image-08 job `9646670` finished `DONE` and passed normal-completion, fatal,
EDIFF, magnetization, restart-read, structure, fixed-Fe, and restart-file
checks. It converged at DAV 24 with final total magnetization
`105.4450488 muB`; the last-12 span was only `0.0570777 muB`. Its unchanged
static geometry has C-O/C-Fe/O-Fe
`2.514489/1.777337/1.664289 A`. The sequential image-07->08 electronic branch
preflight is now complete. The next calculation remains blocked on new user
authority for any whole-path pilot.

The user authorized one repaired full-path test on 2026-07-28. The exact
ten-internal-image candidate passed refreshed geometry, `dist.pl`,
`nebmovie.pl 0`, INCAR, strict generic-input, executor-preflight, and
hash-bound execution-gate checks. The sole executor submitted 80-core
ordinary no-climb `NSW=1` pilot job `9647154`. VASP runtime evidence confirms
that only image 07/08 use their validated WAVECARs (`ISTART=1`); all other
internal images start independently (`ISTART=0`). Completion must still pass
SCF, 1.5 eV/A force, C-O ordering, endpoint-collapse, image-06/07/08 O-site,
and fixed/mobile-Fe checks. No formal NEB is authorized by submission of this
pilot.

Job `9647154` subsequently reached LSF `DONE` and all ten images completed the
single requested ionic step with electronically normal output. It fails the
pilot force gate: every internal image exceeds `1.5 eV/A`; the largest latest
atomic/NEB forces are `9.795983/13.250641 eV/A` at image 01. This path cannot
authorize production NEB.

The user then approved the explicit next step of testing whether the old
203-step image 07 is an independently stable local dissociated product. The
structure is routed as `TS_ENDPOINT`, not as a global adsorption minimum. Its
pre-relaxation geometry gate passes with C-O/C-Fe/O-Fe
`2.7033/1.7589/1.7998 A`, no collision, and exactly 18 fixed Fe. The endpoint
validator retains large-displacement and surface-motion warnings but finds the
expected C-O break, classifies all extra Fe-C/O edges as reviewed site
coordination, and finds no unexpected bond or site event. The exact
`routine_production.endpoint_relaxation` input passed generic and strict input
preflights. Remote input and approved POTCAR hashes agree; 32-core job
`9647798` completed normally under
`~/sbq/Fe110/ts/co_dissociation_topic1_20260718/ts_endpoint_local_product_img07_relax_20260728`.
It reached EDIFF and the ionic stopping criterion after 61 steps, with final
maximum force `0.016035 eV/A` and no fatal output. The final structure passes
geometry review at C-O `3.1131 A`, C long-bridge, and O hollow; the bottom 18
Fe remain exact and mobile-Fe motion is local. The full trajectory is
continuous, with maximum single-step O motion `0.1666 A` and no independent
site-hop event. Post-relaxation validation finds the intended C-O break, no
unexpected bond/site event, and only expected Fe-C/O coordination changes.
The mandatory large-displacement warning remains. Use this CONTCAR only as a
locally stable `TS_ENDPOINT` candidate until a complete IS-to-candidate path
passes path-connectivity review.

## Dimer and Vibrational-Mode Acceptance - 2026-08-06

Dimer job `9656664`, derived from the reviewed `9640399` image-03/04/05 triad,
passes the hard Dimer gate: normal and electronic completion, VASP maximum
atomic force `0.016036 eV/A <= 0.02 eV/A`, negative curvature
`-17.98604 eV/A^2`, contract binding, and accepted initial/final modes. DIMCAR
Force `0.05994 eV/A` and Torque `0.14817 eV/A` remain above their soft targets,
but decreased from `0.72183/11.58158`; their residuals are explicitly accepted
for TS validation in
`dimer_soft_gate_review_ts_acceptance_20260806.json`.

VFA job `9694935` completed normally with five real modes and one imaginary
mode, mode 6 at `537.451689 cm^-1`. C and O are the only moving atoms in this
partial Hessian, and their relative eigenvector projects `98.374%` onto the
C-O bond direction. Mode 6 is therefore formally accepted as the intended
Fe(110) CO-dissociation reaction coordinate. The additive review package is
`diagnostics/ts_validation_review_dimer9656664_mode6_20260806`; original Dimer
and VFA calculation outputs remain unchanged.

This establishes the Topic-1 Dimer acceptance step:
`Dimer convergence -> frequency validation -> TS result record`. Force/Torque
review is conditional on a missed soft target, not a fixed step. VFA grading
and bidirectional connectivity are not Dimer acceptance gates. The present
mode assignment is accepted and the TS result is accepted; C/O-only active-set
convergence remains a publication-method check. No barrier is reported.
