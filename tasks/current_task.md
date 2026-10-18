<!-- state-handoff:start current_task -->
# Current Task

## Objective

Calibrate adsorption acceleration using existing compatible VASP structures/trajectories and the existing frozen AQCat25 candidate; preserve ongoing VASP work.

## Current Evidence Snapshot

- Existing training2185 completed with producer exit0;candidate SHA33b615feef2860e744d67ba964a27d1b60b9be7abdc9e754d5e264c10e96b160;not promoted.
- Original source package34train/12development/16heldout passed hash/source/mask validation;12development groups improve;C2adsorbate vectorRMSE0.222462→0.083809eV/A.
- No new model was run;old16heldout remain unconsumed. Development agreement does not establish better minima or measured VASP speedup.
- Recovered3 complete existing jobs06_C/07_B/08_A:24 exact-frame labels;SIGMA0.20/POTCAR/SCF/coordinates/force/energy/fixed-layer/graph checks pass;no cross-split near duplicates against old62rows.
- Four-job read did not complete within its180s budget;08_B missing,partial receipt preserved,no VASP rerun or repeated full collection. XDATCAR cell rounding handled using input lattice and printed precision.
- New24rows are future training candidates only. Existing15VASP jobs remain untouched;no new training,GPU/VASP submission or model-default change.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Prepare one hash-bound executable GPU validation request for frozen2185:16heldout exact-force comparisons plus bounded geometry drift/same-seed comparisons; obtain separate submission authority before execution.

## Submission Boundary

Local collection,preparation and review only. No new scientific execution,training,retry,promotion or existing-job stop authorized.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- Existing2185 producer/checkpoint/development evidence is retrieved byte-for-byte and reviewed without an independent-calibration or speedup claim.
- Available new trajectory labels are source/SCF/geometry/compatibility/split reviewed;missing08_B and original heldout isolation remain explicit.
- A separately authorized GPU validation has tested the frozen candidate on heldout forces and bounded DFT-minimum/same-seed geometry before adoption.

## Constraints

- Previously screened06_C/07_B/08_A are not pristine heldout data;do not train/select epochs on the frozen16.
- Force-only adaptation does not calibrate adsorption-energy ranking;do not loosen DFT criteria or claim acceleration without matched VASP timing.
- MatRIS remains an audit option and all backend roles remain unchanged.

## Authoritative References

- configs/execution_backends.yaml
- modules/adsorption_workflow/README.md
- docs/reviews/fe110_adsorption_calibration_20261018.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_calibration_20261018_v1/development_review.json
<!-- state-handoff:end current_task -->
