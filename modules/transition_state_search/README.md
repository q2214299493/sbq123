# Transition-State Strategy Engine V3

## Purpose

Own one continuous transition-state workflow from endpoint validation through
NEB and optional DIMER refinement. NEB and DIMER are methods selected inside
this module, not separate scientific modules.

The local strategy-learning extension is documented in [LEARNING.md](LEARNING.md).
It captures the current workflow as a baseline, records immutable attempts and
reviewed outcomes, exposes AQCat25/BA-Sella as a reference candidate branch,
and compares bounded strategy variants. VASP submission preflight checks its
exact-input failure history; learning never creates execution or TS authority.

## Entry Inputs

- mapped IS/FS structures with identical cell, identity atom order, species
  order, and Selective Dynamics;
- one reaction-contract YAML/JSON containing full atom map, numeric reaction
  atoms, indexed broken/formed bonds, endpoint registry IDs, and the complete
  material/surface/method compatibility branch;
- optional reviewed external path evidence from
  `modules/catalysis_data_retrieval/`;
- project-approved VASP settings and optional accepted TS templates.

Unknown mapping, endpoint chemistry, template transferability, magnetic state,
or material compatibility is `Needs confirmation`.

## Stable-Product Endpoint Reuse

Do not reject or accept the lowest-energy product solely because it is the
global minimum. It may be reused as the NEB endpoint only after atom mapping,
periodic mapping, local stability, intended reaction-event purity, and path
connectivity pass. Generate a separate TS endpoint when the stable product
contains an additional independent event, fails one of those checks, or a more
path-compatible locally stable endpoint exists. The additive implementation is
`modules/ts_endpoint_generator.py`; the rule authority is
`AGENT_RULE_TS_ENDPOINT.md`.

Endpoint responsibilities are kept separate. `modules/ts_endpoint_evidence.py`
loads structures and returns raw displacement/connectivity evidence without
status or reason codes. `modules/ts_endpoint_validator.py` is the sole endpoint
scientific-validation authority. `modules/structure_purpose_manager.py`
orchestrates purpose selection, generation, validation, routing, and explicitly
authorized persistence. `modules/ts_endpoint_database.py` is a transaction and
serialization adapter; it does not re-run scientific validation and does not
implicitly migrate the registry. The endpoint extension revision is complete,
but direct SQL and non-empty rollback remain prohibited. Applying the validated
migration API to a real registry requires separate path-specific authorization;
see `MIGRATION_REVISION_BACKLOG.md`.

## Execution Backends

`configs/execution_backends.yaml` is the machine-readable backend contract.
The local `work` repository owns contracts, review, handoff, registry, and
acceptance. `BUCT(sbq)` / `MZ73` may run AQCat25 inference, endpoint ML
relaxation, IDPP, ASE ML-NEB/ML-CI-NEB path optimization, BA-Sella candidate
search, and approved force-only or relative-energy-preserving force-model
fine-tuning. Its
outputs remain predicted candidates. `sunboquan-codex` alone runs VASP/VTST.
Every GPU artifact must return through `work` and pass structure, path,
provenance, compatibility, and VASP-input gates; direct GPU-to-VASP transfer
and automatic submission are forbidden.

All AQCat25 transfers use `configs/aqcat25_handoff.schema.json` and
`scripts/aqcat25_handoff.py`. The current Fe45 calibration in
`configs/aqcat25_domain_gate.yaml` covers near-relaxed adsorption structures
only; it does not calibrate off-equilibrium paths, saddles, BA-Sella, DIMER, or
NEB images. Those GPU candidates must return `uncalibrated` until compatible
VASP path/saddle force labels establish a separate TS-domain gate.

### Active-Learning and Complete-Path Acceleration

The implemented sequential active-learning controller is part of the unified
`scripts.ts_strategy_engine.cli` command surface and is governed by
`configs/aqcat25_ts_active_learning.yaml`. Its state, scheduler evidence,
force-prediction request/result, training manifest, and fine-tune result are
validated by `configs/aqcat25_ts_active_learning.schema.json` through
`scripts/aqcat25_ts_schema.py`. The legacy BA-Sella branch validates one
selected structure per round. The path branch consumes a complete, hash-bound
GPU ML-NEB manifest and handles all selected images as one batch. Each round
is hash-bound and uses this sequence:

1. accept only a returned `predicted_transition_state_candidate_only` BA-Sella
   structure;
2. prepare a reviewable static VASP force-label folder for
   `sunboquan-codex` without automatic submission;
3. capture LSF evidence with `capture-lsf-evidence`; ingestion verifies the
   stored raw `bjobs -a` output/hash and re-queries the same job ID before it
   accepts `DONE`. It then requires OUTCAR normal completion,
   the final electronic step meets `EDIFF` before `NELM`, atom order matches,
   and a complete force block exists;
4. prepare a hash-bound work-to-MZ73 prediction request and compare AQCat25 and
   VASP forces on the exact same structure/checkpoint;
5. treat that comparison only as a local fine-tuning trigger, never as TS-domain
   calibration;
6. when it fails, train with all accepted TS labels plus adsorption replay,
   retain a disjoint adsorption regression set, and reject any checkpoint that
   cannot load, returns non-finite values, or fails held-out regression;
   adsorption retention uses a tiered gate: component RMSE, vector RMSE, and
   p95 remain hard non-regression guards, while a vector-maximum increase no
   larger than both `0.005 eV/A` and `2%` is a reviewable soft warning. A soft
   warning may enter candidate evaluation but never authorizes checkpoint
   promotion or a complete-path rerun;
7. rerun BA-Sella or the complete ML-NEB path, according to the source
   candidate kind, only through a new checkpoint-bound handoff;
8. require a disjoint VASP-labeled TS validation set spanning rising-path,
   near-saddle, and falling-path structures before reporting TS-domain
   validation. The production TS gate remains `uncalibrated` until those real
   labels produce bootstrap metrics and an explicit, hash-bound calibration
   review registers thresholds no looser than the configured safety ceilings.

Independent TS-domain validation is trigger-based, not repeated mechanically
for every acceptable NEB path. Bootstrap at least five held-out structures when
the TS domain is uncalibrated. Revalidate after a checkpoint or compatibility
change, an out-of-scope reaction domain, a failed novelty/uncertainty gate, or
a scheduled audit. An unchanged checkpoint on an in-domain path may reuse the
existing calibration. Existing VASP force evidence may also be reused when the
exact structure hash, DFT compatibility, normal completion, electronic
convergence, complete force block, and scheduler evidence all match; an
energy-only value is insufficient. Held-out validation hashes are excluded
from all TS training rounds and adsorption replay data.

These rules are implemented in `active_learning_domain.py`,
`active_learning_calibration.py`, the shared JSON Schema, and the unified CLI.
After local force agreement, a matching calibrated
checkpoint enters `awaiting_ts_domain_reuse_decision`; a Schema-validated reuse
context must prove the exact checkpoint/compatibility, in-scope reaction domain,
passed novelty/uncertainty review, and that no periodic audit is due. Otherwise
the controller requires a new independent validation set. An uncalibrated
bootstrap assessment never makes acceleration ready by itself.

Implementation and tests do not constitute production calibration evidence.
The active Fe45 TS domain remains `uncalibrated` until real, disjoint VASP force
labels pass the bootstrap review and registration sequence above.

The implemented complete-path runner is `scripts/aqcat25_ml_neb.py`, with the
MZ73 wrapper `scripts/aqcat25_ml_neb_job.sh`. Its GPU acceleration product is a
complete ML-NEB path rather than one isolated saddle guess. A qualifying path manifest records every image hash,
checkpoint hash, predicted energy, physical force, projected NEB force, spring
force, reaction-coordinate value, adjacent-image RMSD, periodic mapping, and
domain/uncertainty review. Ordinary ML-NEB is used first; ML-CI-NEB is optional
only after a continuous single-peak ML path exists. Waypoints are conditional:
use them when endpoint-only IDPP misassigns, under-resolves, or discontinuously
maps the intended event, not as a universal fixed step. Representative VASP
labels are chosen adaptively from the peak triad, rising/falling regions,
committee disagreement when available, and any continuity anomaly.
`model_disagreement` is valid only for an actual ensemble/committee. A single
checkpoint may contribute path coverage, structure novelty, and measured VASP
error, but must not report model disagreement or call its own output
uncertainty.

The dual-model TS-path executor is `scripts/dual_model_ml_neb.py`, with the
MZ73 wrapper `scripts/dual_model_ml_neb_job.sh`. For the reviewed Fe-C-O-H
routing branch it uses MatRIS as the path-optimization primary and AQCat25 as
an exact fixed-path secondary evaluator. Optional finite bilateral harmonic
bond restraints may precondition a chemically resolved seed, but the executor
must prove that every temporary internal-coordinate restraint is removed
before ordinary ML-NEB. The restrained stage is never an MEP. AQCat25 must not
relax the returned MatRIS path; both models are compared only on identical
structure hashes, within-model relative energies, and movable-atom forces.
Their disagreement is a VASP-label sampling score, not calibrated uncertainty.
Bounded MZ73 job `1317` passes the executor, release, provenance, and geometry
smoke gates; its two-step path is intentionally unconverged and has no TS,
DIMER-parent, VASP, or barrier status. A production GPU run remains a separate
hash-bound request requiring explicit user authorization.

Temporary restraint-release stages distinguish an advisory force target from
final ML-NEB convergence. A request may retain legacy `fail` behavior or select
`warning_continue` for `nonconverged_stage_action`. In warning mode, exhausting
the stage step limit above its requested `fmax` records a warning and may
continue only when forces are finite and the per-step bond, collision,
continuity, atom-step, and periodic-branch guards still pass. Each release
stage writes recent `fmax` history plus separate primary-model physical,
temporary-restraint, and projected NEB force maxima. This exception applies
only to restrained path preparation: every temporary restraint must still be
removed before ordinary ML-NEB, and the final unrestrained geometry and
ordinary/CI convergence requirements are unchanged.

`scripts/aqcat25_ml_path_committee.py` evaluates an already fixed path with at
least three unique checkpoints, loaded serially to limit GPU memory use. It
reports per-image energy and force disagreement. That quantity becomes
calibrated uncertainty only after a disjoint VASP validation set demonstrates
that disagreement predicts actual force error. Same-checkpoint repeats and a
snapshot-only set are not accepted as the primary committee evidence.

For MatRIS-primary TS paths, `configs/dual_model_ts_active_learning.yaml`
defines the automatic local active-learning branch. Runtime failure is handled
outside this scientific branch. A path or failure boundary enters training
consideration only after atom mapping, periodic unwrap, endpoint/cell/fixed-mask
compatibility, minimum-distance, and adjacent-continuity gates pass. Preserve
the last geometry-valid point and first geometry-valid failure point as a
hash-bound pair when both exist; a failed path does not by itself prove model
error.

Optional standard Sella peak refinement now joins this same MatRIS/VASP loop;
see [SELLA_BRANCH.md](SELLA_BRANCH.md) for method selection, inputs, failure
handling and new-checkpoint reruns. The complete-path NEB default and the
existing AQCat25 BA-Sella branch remain available. Sella output is a separate
prediction candidate and cannot replace the NEB/Dimer execution or TS gates.

The optional [reviewed rough-path local-peak entry](SELLA_LOCAL_PEAK.md) reuses
a saved complete MatRIS path without another NEB run. It allows unconverged,
globally multi-peak parents while requiring one reviewed local peak per bounded
request, unchanged geometry/identity gates, and work-side candidate review.
It does not relax the existing automatic converged-single-peak refinement gate.

Every GPU path-failure review must expose two explicit downstream choices:
exact-structure active-learning diagnosis and direct VASP path/refinement. If
the hash-bound last-valid/failure-boundary pair passes the active-learning entry
gate, prepare the MatRIS/AQCat25/VASP comparison first. MatRIS error above any
registered screening ceiling routes to replay fine-tuning plus a new-checkpoint
complete-path rerun; a passed MatRIS screen retains the checkpoint and routes
to path repair or local VASP micro-NEB. If active-learning entry fails, report
the failed prerequisite and use the reviewed VASP/path-repair branch. This is
a diagnosis/preparation priority only and does not authorize any GPU, VASP,
fine-tuning, rerun, micro-NEB, or Dimer submission.

Prefer a real committee of three to five independently trained,
production-accepted checkpoints of the same MatRIS architecture. AQCat25 may
audit the exact same structures but is not a MatRIS committee member. When the
committee prerequisite is unmet, use the MatRIS-primary/AQCat25-audit/VASP-error
fallback and do not report uncertainty. Candidate sampling ranks available
committee force and relative-energy disagreement, descriptor novelty, TS
proximity, failure-boundary proximity, and reaction-coordinate backtracking;
raw quantities with different units are converted to within-batch percentile
ranks rather than directly summed. Exact hashes are deduplicated and descriptor
clusters are used when available, with reaction-coordinate bins as fallback.

The small VASP label set preferentially retains the last valid point, first
valid failure point, maximum committee disagreement, maximum reaction-coordinate
backtrack, TS-like point, and rising/falling representatives when distinct.
Peak neighbors are not universal active-learning labels; the exact peak triad
is reserved for VASP refinement or the Dimer parent gate. Labels are `NSW=0`
compatible static calculations and require normal/electronic completion,
complete all-atom forces, total and atom-resolved magnetic moments, and the
active DFT fingerprint before training. With a real committee, disagreement
versus actual MatRIS-VASP error is routed through four cases: high/high trains,
high/low calibrates conservatism, low/high is a blind spot and trains with
expanded novelty sampling, and low/low is covered or held-out. Fine-tuning must
use TS/adsorption replay, preserve relative energies and force tails, produce a
new versioned checkpoint, rerun the complete path, and pass disjoint held-out
VASP TS validation. These local steps may be prepared automatically; GPU,
VASP, fine-tuning, path-rerun, micro-NEB, and Dimer submissions remain separate
authorized actions.

Every completed VASP NEB/CI-NEB path failure also receives a mandatory local
closeout without waiting for a separate reminder. Collect scheduler,
electronic, ionic/force, final-geometry, and path-continuity evidence; register
the hash-bound failed strategy attempt and outcome; and block an exact-input
retry. When the final VASP force block can be matched to the exact evaluated
structure, use it only for a MatRIS/AQCat25 error screen unless the label also
contains every training-required magnetic field. A failed MatRIS screen
prepares new training-eligible `NSW=0` static labels before fine-tuning; a
passed screen retains the checkpoint and prepares path repair or local VASP
refinement. Finish by preparing a fresh execution gate. These closeout and
preparation steps are automatic and local; they never authorize remote GPU,
VASP, fine-tuning, NEB, Dimer, or frequency submission.

Every MatRIS training request must carry a file-hash-bound manifest produced
and validated by `scripts/matris_training_exclusions.py`. Before optimizer
construction, the guard rejects both exact structure-SHA overlap and rounded,
translation-invariant geometry-SHA overlap with any frozen held-out sample.
Sample renaming cannot bypass this gate. Held-out labels remain excluded from
training and replay after later checkpoint changes.

Before any MatRIS fine-tuning, run
`scripts/prepare_matris_finetune_request.py` with the active state and the
caller-supplied exclusion-manifest SHA-256. The preflight also verifies the
trigger assessment, quality-passed VASP training labels, active policy, and
base checkpoint. A non-triggered decision, stale binding, or hash mismatch
produces no training request. A passed request remains non-executable until a
separate fine-tuning authorization is recorded; this script never submits a
GPU job.

The runner attaches one loaded AQCat25 calculator serially to every image using
ASE `allow_shared_calculator=True`; every image therefore uses the same exact
checkpoint without multiplying GPU model memory by the number of images. It
writes atomic restart images and runtime state at a configurable interval.
Ordinary ML-NEB always runs first. `--ml-ci auto` enables ML-CI-NEB only after
ordinary convergence, one strict internal peak, and the adjacent-RMSD
continuity screen pass. `on` cannot override a failed readiness screen, and
`off` retains the ordinary ML-NEB path.

GPU output is deliberately `needs_work_review`. It contains all image
structures and hashes, predicted energies, physical forces, projected NEB
forces, spring forces, reaction progress, key bond distances, adjacent RMSD,
numeric geometry screens, and adaptive VASP-label candidates. After the path
returns to `work`, review the generated
`gpu_ml_neb_path_review.draft.json` and save the accepted, checksum-bound copy
as `gpu_ml_neb_path_review.json`.
`ml-neb-path-finalize` is the only command that writes
`accepted_for_vasp_validated_dimer_parent`. The accepted path still needs the
exact VASP peak triad and force-agreement/domain branch required by the Dimer
gate.

Local candidate force agreement is not active-learning convergence. VASP label
energies are `force_label_only`, and ML energies/forces remain predictions.
Neither class enters final energy tables. Failed GPU/VASP stages are recorded
and resumable in the state machine; none of these commands submits a job.
The candidate still proceeds through VASP NEB/CI-NEB or DIMER, source-method
TS validation, and compatible IS/TS/FS final-energy gates. DIMER acceptance requires
convergence plus vibrational validation; connectivity is optional diagnostic
evidence for DIMER.

The path controller prepares all selected VASP single-point directories and a
single batch manifest together. It also ingests a complete batch of hash-bound
LSF `DONE` evidence and aggregates exact-structure AQCat25/VASP force errors
over every selected image. This removes per-image manual state transitions,
but it does not submit calculations. One bounded user authorization may cover
the reviewed batch; direct GPU-to-VASP transfer and open-ended automatic VASP
submission remain forbidden.

```powershell
python -m scripts.ts_strategy_engine.cli active-learning start --ts-workdir TS_WORKDIR
# If a TS directory contains more than one returned candidate, disambiguate:
python -m scripts.ts_strategy_engine.cli active-learning start --ts-workdir TS_WORKDIR --candidate-manifest GPU_RESULT --handoff-root ROOT
python -m scripts.ts_strategy_engine.cli active-learning prepare-label --ts-workdir TS_WORKDIR --destination LABEL_DIR
python -m scripts.ts_strategy_engine.cli active-learning capture-lsf-evidence --job-id JOBID --output LSF_DONE.json
python -m scripts.ts_strategy_engine.cli active-learning ingest-label --ts-workdir TS_WORKDIR --scheduler-evidence LSF_DONE.json
python -m scripts.ts_strategy_engine.cli active-learning prepare-prediction --ts-workdir TS_WORKDIR --destination PREDICTION_REQUEST
python -m scripts.ts_strategy_engine.cli active-learning assess --ts-workdir TS_WORKDIR --prediction AQCAT_FORCES.json
python -m scripts.ts_strategy_engine.cli active-learning prepare-finetune --ts-workdir TS_WORKDIR --destination TRAINING_PACKAGE
python -m scripts.ts_strategy_engine.cli active-learning prepare-rerun --ts-workdir TS_WORKDIR --destination RERUN_HANDOFF
python -m scripts.ts_strategy_engine.cli active-learning assess-domain --ts-workdir TS_WORKDIR --manifest HELD_OUT_TS_VALIDATION.json
python -m scripts.ts_strategy_engine.cli active-learning register-domain-calibration --ts-workdir TS_WORKDIR --review CALIBRATION_REVIEW.json
python -m scripts.ts_strategy_engine.cli active-learning decide-domain-reuse --ts-workdir TS_WORKDIR --context REUSE_CONTEXT.json
python scripts/aqcat25_ml_neb.py --handoff HANDOFF/handoff.json --checkpoint MODEL.pt --schema configs/aqcat25_handoff.schema.json --output GPU_PATH
python scripts/aqcat25_ml_path_committee.py prepare --path-manifest GPU_PATH/gpu_ml_neb_path_manifest.candidate.json --member primary=MODEL_A.pt --member seed2=MODEL_B.pt --member seed3=MODEL_C.pt --output COMMITTEE_REQUEST.json
python scripts/aqcat25_ml_path_committee.py assess --path-manifest GPU_PATH/gpu_ml_neb_path_manifest.candidate.json --request COMMITTEE_REQUEST.json --output COMMITTEE_ASSESSMENT.json
python -m scripts.ts_strategy_engine.cli active-learning path-init --path-manifest GPU_PATH/gpu_ml_neb_path_manifest.candidate.json --contract CONTRACT.json --committee-assessment COMMITTEE_ASSESSMENT.json --destination ACTIVE_LEARNING
python -m scripts.ts_strategy_engine.cli active-learning prepare-path-labels --state ACTIVE_LEARNING/active_learning_state.json --destination VASP_LABEL_BATCH
python -m scripts.ts_strategy_engine.cli active-learning ingest-path-labels --state ACTIVE_LEARNING/active_learning_state.json --evidence-manifest VASP_BATCH_DONE.json
python -m scripts.ts_strategy_engine.cli active-learning prepare-path-predictions --state ACTIVE_LEARNING/active_learning_state.json --destination PREDICTION_BATCH
python -m scripts.ts_strategy_engine.cli active-learning assess-path --state ACTIVE_LEARNING/active_learning_state.json --manifest PATH_PREDICTIONS.json
python -m scripts.ts_strategy_engine.cli ml-neb-path-validate --manifest GPU_PATH/gpu_ml_neb_path_manifest.candidate.json
python -m scripts.ts_strategy_engine.cli ml-neb-path-finalize --candidate GPU_PATH/gpu_ml_neb_path_manifest.candidate.json --review GPU_PATH/gpu_ml_neb_path_review.json --output GPU_PATH/gpu_ml_neb_path_manifest.json
```

`init-from-ts` reads `reaction_contract.normalized.json` and writes
`active_learning/active_learning_state.json` below the same TS work directory.
The former `scripts.aqcat25_ts_active_learning` entry remains a compatibility
wrapper only.

## Unified Workflow

### Authoritative NEB Execution Gate

`scripts/ts_strategy_engine/execution_gate.py` is the sole authority for every
NEB action. Parsers, monitors, path-quality checks, strategy composition, and
workflow orchestration produce evidence only. The executor rejects an action
unless the current, hash-bound gate decision lists it in `ALLOWED_ACTIONS`.
Thresholds are part of the state hash. Before execution, the decision is
recomputed from its bound evidence; editing an action field or reusing a stale
decision cannot create authority.

The gate evaluates, in order: data/structure integrity, endpoints, electronic
convergence, reaction-coordinate continuity, elementary-step purity, ordinary
NEB convergence, CI readiness, DIMER readiness, source-method TS validation, and
resource/submission preflight. A lower-priority pass never overrides an earlier
failure. Its required output is `DECISION`, `REASON_CODES`, `EVIDENCE`,
`CRITICAL_IMAGES`, `ALLOWED_ACTIONS`, `FORBIDDEN_ACTIONS`,
`NEXT_REQUIRED_CHECK`, `SUBMISSION_ALLOWED`, `CI_NEB_ALLOWED`,
`DIMER_ALLOWED`, and `TS_CLAIM_ALLOWED`.

`configs/neb_path_quality_control_v2.yaml` contains only configurable evidence
thresholds. `path_quality_control.py` contains the sole scientific evaluator;
`path_quality_service.py` provides shared input/config/report orchestration for
the standalone CLI, unified workflow, and pilot adapter. Neither can authorize
continuation, stopping, rebuilding, submission, CI-NEB, DIMER, TS acceptance,
or a barrier claim.

The gate counts independent evidence families rather than duplicated flags.
Transient `NELM` exhaustion, early/nonpersistent high force, and one-frame
energy minima remain warnings. `STOP_JOB` additionally requires
blocker-specific parser artifacts, current hashes of their raw source files,
bound thresholds, and raw LSF query evidence. Underresolution also requires
the path-quality artifact. Inline JSON cannot authorize a real stop. These
semantics use gate Schema v2; prior gate decisions are not reusable.

The gate never uses CI-NEB to repair an invalid ordinary path and never treats
an intermediate image as an endpoint until an independent relaxation proves a
local minimum. DIMER may refine a candidate from either ordinary no-climb NEB
or CI-NEB; `LCLIMB` is not a DIMER eligibility condition. A high-energy image
is not a TS before the applicable frequency validation.
Geometry heuristics such as one-coordinate backtracking, large endpoint
motion, and surface penetration/desorption enter review rather than data-
integrity failure. Connectivity tolerance misses use the configurable
`configs/ts_connectivity_gate.yaml` policy and remain `NEEDS_REVIEW`.

The enforced action surfaces are:

- path rebuild: `generate_path.py`;
- ordinary NEB, diagnostic VASP, CI-NEB, DIMER submission and job stopping:
  `submission.py`;
- local DIMER handoff preparation: `handoff.py` with
  `PREPARE_DIMER_HANDOFF`; actual submission separately requires
  `START_DIMER` after DIMER preflight;
- Grade-A TS approval and final barrier registration: `evidence.py`.

An explicit job-bound user cancellation may authorize `STOP_JOB` for either
LSF `PEND` or `RUN` through file-bound scheduler and authorization evidence.
The executor re-queries the same job and rejects a status race; direct `bkill`
outside the executor remains forbidden.

### DIMER Candidate Gate

`configs/dimer_gate.yaml` and `scripts/ts_strategy_engine/dimer_gate.py` define
the DIMER candidate gate. The following are hard requirements before
`START_DIMER`:

- candidate, previous, and next structures have identical cells, elements,
  atom order, and Selective Dynamics;
- the candidate is an internal numbered image with two immediately adjacent,
  geometrically continuous neighbors;
- all three images have complete, normally terminated, electronically
  converged outputs with finite energies and atomic forces;
- reaction-center motion is continuous on one periodic branch. Numerical
  displacement checks and an accepted chemical review must exclude atom
  jumps, adsorption-site discontinuity, and mechanism switching;
- MODECAR has one finite vector row per candidate atom, all fixed components
  are zero, its norm is nonzero and normalized, and its dominant amplitude is
  on the reviewed target-reaction atoms;
- MODECAR, all three structures, the reaction contract, generation method, and
  gate policy are SHA-256-bound. The accepted review must assign the mode to
  the intended bond breaking, bond forming, or adsorption-site change.

The parent NEB being fully converged, a strict local energy maximum, clearly
reduced forces in the peak triad, absence of a real intermediate, and the
candidate lying between the IS and FS basins are recommended evidence, not
independent hard blockers. These recommendations guide candidate selection;
they cannot override a failed hard requirement.

Applicable parent/refinement cases include:

- ordinary no-climb NEB may proceed to either CI-NEB or a hard-gate-passing
  DIMER candidate;
- a coarse ordinary NEB whose other internal images are basically stable while
  the highest-energy image remains force-stalled may preferentially prepare a
  DIMER handoff. The default machine-readable recommendation requires at least
  20 peak-image ionic steps, peak force at least `0.5 eV/A` with a plateau or
  oscillating trend, and every other internal-image force at most `0.5 eV/A`;
  these values are configured in `configs/dimer_gate.yaml`;
- a slowly finishing CI-NEB peak may proceed to DIMER when its local triad
  passes the hard gate even if the whole CI path has not reached final force
  precision;
- a GPU ML-NEB path may proceed directly to DIMER only under the distinct
  `gpu_ml_neb_vasp_validated_triad` parent method. The complete GPU path must be
  hash-bound and pass geometry, periodic-branch, reaction-coordinate, and
  elementary-step review. The exact candidate and its two neighbors must each
  have normally completed, electronically converged, compatible VASP static
  energy/force labels whose structure hashes match the GPU images. The local
  AQCat/VASP force comparison must pass the configured thresholds, or the same
  checkpoint/reaction domain must have an accepted calibrated TS-domain gate.
  This validates a DIMER starting candidate only; it does not turn ML energies
  into DFT values or establish a TS/barrier;
- DIMER may refine one peak instead of repeating an expensive whole path;
- denser k-points or higher ENCUT may be used only as a separately reviewed,
  compatible refinement branch. Energies from incompatible branches must not
  be mixed.

The coarse-NEB peak-stall rule authorizes only
`PREPARE_DIMER_HANDOFF`. It does not prove that the stalled peak is a saddle
and cannot authorize `START_DIMER` until the local triad, electronic,
periodic-mapping, chemical-review, and MODECAR hard checks all pass.

A one-step, same-path pilot is optional diagnostic evidence for ordinary NEB,
not a production submission prerequisite. Use it only when the user selects it
for unresolved runtime, electronic, magnetic, restart, parallel-layout, or
immediate-geometry risk. When `neb_pilot_result.json` is supplied,
`pilot_validation.py` rebuilds its verdict from live LSF `DONE` evidence and
the hash-bound POSCAR/CONTCAR/OUTCAR/OSZICAR files for every internal image,
and the submission executor rejects stale or mismatched pilot evidence. The
validator records `MAGNETIC_CONTINUITY_RULE` as non-blocking `SOFT_WARNING`
evidence. Absence of a pilot does not block an otherwise reviewed, preflight-
passing, hash-bound ordinary-NEB submission. The executor uploads only files
in the preflight manifest; unrelated reports or directory contents are
excluded.

NEB-force warning and failure semantics are strict:

- `high_force_warning_threshold_eVA=1.5 eV/A` is a warning line, not a
  force-convergence target and not an early-step failure threshold;
- the first `min_ionic_steps_for_force_warning=5` ionic steps are an allowed
  startup window and are classified as `initial_high_force_allowed`;
- after that startup window, force above the warning line with a plateauing,
  oscillating, rising, or otherwise non-decreasing trend is warning evidence,
  not failure by itself;
- persistent high force becomes path-failure evidence only after
  `persistent_high_force_failure_min_ionic_steps=10` ionic steps without a
  decreasing trend;
- high NEB force also becomes path-failure evidence when accompanied by
  independently verified abnormal atomic displacement, periodic-image jump,
  or magnetic discontinuity. The geometry and magnetic evidence remains
  independently inspectable in the gate inputs;
- an `NSW=1` pilot checks input/runtime compatibility, electronic convergence,
  restart behavior, and immediate geometry sanity. It cannot establish ionic
  force convergence or persistent high-force failure.

1. Endpoint and atom-mapping guard; never repair mapping by interpolation.
2. Build a deterministic reaction fingerprint.
3. Retrieve successful Grade-A templates in this order: exact fingerprint,
   chemical identity, reaction event, and reaction family. Similar reactions
   may set `strategy_transferable=true` even when endpoint IDs or the exact
   method branch differ; their score must still pass the configured threshold.
4. `strategy_transferable` transfers only waypoint, interpolation, NEB, DIMER,
   and local-frequency method choices. `result_transferable` remains restricted
   to an exact compatible fingerprint and means only that the existing
   registered result may be referenced. Never copy endpoint coordinates,
   atom indices, MODECAR, restart files, image numbers, energies, or a barrier
   into a new calculation result.
5. If no usable template exists, use the family rules in
   `configs/ts_strategy_engine/families.yaml`.
6. Initialize and review the path. Use direct IDPP only when atom mapping,
   periodic continuity, geometry, and reaction-coordinate resolution pass.
   Add reviewed chemical waypoints and segmented IDPP when the direct route
   misassigns or under-resolves bond breaking/forming or another complex event.
   The project-specific prohibition on pure C/O endpoint interpolation remains
   in force.
7. Run endpoint/path geometry checks, `dist.pl`, and `nebmovie.pl 0`; obtain
   human approval before submission.
8. Run the GPU active-learning/path acceleration loop and review the complete
   path, then choose the least-cost VASP route from current evidence. Options
   include more labels and a GPU rerun, a bounded VASP micro/ordinary NEB,
   CI-NEB for an already continuous single peak, a qualifying GPU-local-triad
   DIMER handoff, or splitting a genuine multi-peak path. GPU acceleration may
   replace a routine VASP coarse NEB when its DIMER-specific VASP triad gate
   passes; it never replaces the VASP DIMER, frequency, or barrier evidence.
   Only the authoritative gate may select continuation, stopping, rebuilding,
   CI-NEB, or DIMER refinement.
   A passed result is `path_stage_valid`; it is never a scientifically
   validated TS before the applicable frequency gate.
9. DIMER starts only from a candidate that passes the local three-image and
   MODECAR hard gate above; the parent can be ordinary NEB, CI-NEB, or a
   `gpu_ml_neb_vasp_validated_triad` path that passes its additional exact-
   structure VASP and force-agreement checks. Inspect
   initial and final modes against their SHA-256-bound review records.
   Technical convergence also requires a valid source/final structure pair,
   `ICHAIN=2`, final electronic convergence, VASP maximum atomic-force
   convergence against `EDIFFG`, negative curvature, and Schema-validated raw
   LSF `DONE` evidence stored as `scheduler_evidence.json`. DIMCAR Force and
   Torque are soft diagnostics: missing either target requires a hash-bound
   human decision before frequency handoff. `allow_frequency_handoff` does not
   establish Grade A or final TS acceptance.

For this Dimer force gate, parse the last complete
`FORCES: max atom, RMS` record in `OUTCAR`. Compare its first numeric field
(`max atom`) with `abs(EDIFFG)` and retain the second (`RMS`) as supporting
evidence. An incomplete trailing record is ignored. The RMS field alone cannot
hide an outlying atomic force. Passing this force component permits the next
gate check; it does not override electronic completion, negative curvature,
mode/provenance or frequency requirements.
10. Run `nebmovie.pl 1` after a completed or stopped path. Send the final
    candidate to `modules/ts_vibrational_validation/`. For a DIMER candidate,
    acceptance requires DIMER convergence plus one accepted target imaginary
    mode; record the result after both pass.
11. Register the accepted IS/TS/FS final `OUTCAR` `TOTEN` values under the
    compatible `ISMEAR=1`, `SIGMA=0.20 eV`
    `fe110_converged_toten_sigma0p20_v1` convention, record the forward,
    reverse, and reaction energies, and atomically store the Grade-A learning
    record in the same transaction. `record-barrier` requires
    `--learning-record`; a successful barrier registration rolls back if its
    linked strategy record is missing, invalid, or incompatible. The learning
    record contains method strategy only and must not carry transferable atom
    indices, coordinates, MODECAR/restart content, image numbers, job IDs,
    energies, or barrier values. No additional single-point is required. Only
    successful Grade-A entries may be transferred as TS templates; failures
    contribute only failure constraints and correction advice.

For every DIMER branch, the fixed acceptance sequence is:

1. DIMER convergence: normal/electronic completion, converged VASP maximum
   atomic force, negative curvature, contract binding, and reviewed modes;
2. frequency validation: a complete contract-defined local partial-Hessian
   calculation with exactly one accepted target imaginary mode and acceptable
   TS geometry; a full movable-slab Hessian is not required by default;
3. result record: store the hash-bound DIMER and frequency evidence.

DIMCAR Force/Torque review is conditional: it is requested only when a soft
target is missed and is not a separate fixed workflow step. VFA grading is not
part of DIMER TS acceptance. Connectivity remains an optional diagnostic.

## Command Surface

```powershell
python -m scripts.ts_strategy_engine.cli plan --is IS --fs FS --contract reaction.yaml --workdir PLAN
python -m scripts.ts_strategy_engine.cli plan --is IS --fs FS --contract reaction.yaml --workdir PLAN --initialize-path --waypoint WAYPOINT
python -m scripts.ts_strategy_engine.cli path-review-draft --workdir PATH --dist dist.dat --nebmovie movie.xyz
python -m scripts.ts_strategy_engine.cli analyze --workdir PATH --contract reaction.yaml --path-review PATH/path_review.json
python -m scripts.ts_strategy_engine.cli dimer --source-image PATH/03 --previous-image PATH/02 --next-image PATH/04 --analysis PATH/neb_analysis.json --path-review PATH/path_review.json --contract reaction.yaml --destination DIMER
python -m scripts.ts_strategy_engine.cli dimer-analyze --workdir DIMER
python -m scripts.ts_strategy_engine.cli vfa-prepare --source-image DIMER --saddle-analysis DIMER/dimer_analysis.json --dimer-soft-gate-review DIMER/dimer_soft_gate_review.json --active-indices REACTION_CENTER_INDICES --contract reaction.yaml --destination VFA
python -m scripts.ts_strategy_engine.cli connectivity-prepare --help
python -m scripts.ts_strategy_engine.cli connectivity-analyze --help
python -m scripts.ts_strategy_engine.cli vfa-analyze --workdir VFA --contract reaction.yaml --review VFA/vfa_review.json
python -m scripts.ts_strategy_engine.cli validation-pipeline-status --help
python -m scripts.ts_strategy_engine.cli record-validation --validation-id ID --analysis VFA/vfa_analysis.json
python -m scripts.ts_strategy_engine.cli record-barrier --learning-record STRATEGY.json --help
python -m scripts.ts_strategy_engine.cli record --help
```

`path_review.json`, `mode_review.json`, and `vfa_review.json` become accepted
only after real visual/chemical review and reviewer/date entry. Generated-path,
`dist.pl`, `nebmovie.pl 0`, contract, atom-map, and compatibility hashes are
checked before advancement. No missing or altered evidence is inferred.
Grade A/B frequency output remains `Ungraded` while the meaningful-imaginary
and soft-mode thresholds in `configs/true_fe110_production.yaml` are null.

The unified workflow CLI never submits or stops jobs. The only submission
executor is `scripts.neb_agent.submission`; it requires a current gate decision,
recomputes the bundle hash, verifies MPI-rank divisibility and the remote
POTCAR hash, and rejects unlisted actions. Specialized numerical helpers remain
under `scripts/neb_agent/`; they are evidence backends, not workflow authority.

## Code Architecture

- `cli.py`: argument parsing and thin command adapters only.
- `workflow.py`: endpoint-to-path planning and NEB analysis orchestration.
- `execution_gate.py`: the only NEB action authority and action validator.
- `execution_decision.py`: pure decision-document construction and derived
  fields; it has no evidence priority, external I/O, or action authority.
- `scripts/neb_agent/path_quality_service.py`: shared path-quality application
  orchestration; it delegates every scientific decision to
  `path_quality_control.evaluate_quality`.
- `modules/ts_endpoint_evidence.py`: read-only endpoint geometry evidence;
  `modules/ts_endpoint_validator.py` remains the only endpoint scientific
  validator.
- `contract.py`, `fingerprint.py`, `strategy.py`: deterministic evidence and
  strategy composition; `strategy.py` delegates every execution decision to
  `execution_gate.py`.
- `path_evidence.py`: path/report/review file binding and SHA-256 checks.
- `registry.py`: the only SQLite connection, schema, timestamp, and
  compatibility-hash utility layer.
- `evidence.py`: endpoint, TS-validation, and compatible final-energy barrier records.
- `templates.py`: template validation, retrieval, and storage only.
- `handoff.py`, `dimer_analysis.py`: DIMER/VFA handoff evidence and DIMER
  convergence analysis.
- `active_learning_domain.py`, `active_learning_calibration.py`: independent
  TS-domain metrics versus reviewed calibration/reuse decisions.

Dependency direction is CLI -> workflow/domain/storage -> registry/backend.
Storage and numerical backends never import the CLI or workflow layer.

Routine NEB monitoring uses the compact backend summary:

```bash
bash scripts/neb_agent/check_neb_job.sh JOB_DIR
bash scripts/neb_agent/check_neb_job.sh JOB_DIR --detail 10
```

From the Windows `work` host, use the LF-stable SSH wrapper instead of piping
`Get-Content` into `ssh`; the latter appends a Windows line ending and can make
a successful monitor return a false nonzero exit code:

```powershell
python -m scripts.neb_agent.remote_monitor sunboquan-codex REMOTE_JOB_DIR
python -m scripts.neb_agent.remote_monitor sunboquan-codex REMOTE_JOB_DIR --detail 10
```

Use the first form by default. Use `--detail 10` only for a bounded diagnosis.
Always run `dist.pl` and `nebmovie.pl 0` before path approval, and
`nebmovie.pl 1` after a completed or stopped NEB before interpretation.

## Required Outputs

- endpoint check and reaction fingerprint;
- ranked template matches with provenance and transfer score;
- one strategy record specifying waypoints, interpolation, NEB sequence, DIMER
  decision, validation handoff, and user-confirmation gates;
- path geometry, energy, force, SCF, mode, and convergence evidence;
- accepted or rejected template-library record with source calculation IDs.
- registered compatible IS/TS/FS final-energy chain and derived barrier set.

## Done Criteria

The chosen NEB/CI-NEB/DIMER sequence is complete, the path and mode are
reviewed, TS validation is graded, provenance is complete, and the Grade-A
learning record has been atomically stored with the compatible final barrier.
No separate user request is needed for this automatic successful-TS strategy
registration. Failed or ungraded candidates are never reusable TS templates.

## B5 application ownership clarification

The sole execution authority remains `scripts/ts_strategy_engine/execution_gate.py`;
NEB submission remains `scripts/neb_agent/submission.py`. No acceptance rule changed.
`handoff.prepare_reviewed_dimer_handoff` applies current contract/path-review binding
before the existing DIMER handoff; CLI handlers only pass arguments.
`workflow.start_vasp_attempt` applies the existing preflight and records a learning
attempt without submitting. `active_learning_state.initialize_from_ts_workdir`
owns candidate discovery and contract-file fallback, rejecting ambiguous candidates.
Generic database connections now belong to `scripts/registry_connection.py`; the
TS registry module is a compatibility facade. Matched final-energy barriers share
`scripts/ts_validation/barrier_values.py` with Excel promotion. DIMER/VFA grading,
source binding, finite-number requirements and nonnegative barriers are unchanged.
