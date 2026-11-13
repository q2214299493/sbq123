# CH+CO sequential force-label experiment

This case uses the paper's sequential single-label BA-Sella loop with the
user-selected AQCat25 FT512 checkpoint and project Fe(110) VASP settings. It is
an explicit model/DFT adaptation, not an unchanged eSEN/QE reproduction.

## GPU VASP label compatibility

GPU VASP 6.4.2 can print its final energy summary before the EDIFF termination
line. The canonical SCF parser keeps these in the same electronic cycle; a
genuine subsequent iteration still prevents reuse of an earlier convergence.
Force-table coordinates, forces, species and cell come from the bounded owner
parser, with CONTCAR and the exact submitted POSCAR independently compared.
No installed ASE package is patched.

The approved `transition_state.active_learning_force_label` stage inherits
EDIFF=1e-6 from `final_static`. The endpoint reaction contract retains EDIFF=1e-5.
Ingestion binds the approved profile bytes and requires the exact force-label
stage precision, no looser than the endpoint branch. These energies remain
`force_label_only`; this distinction does not authorize a reported energy
difference or a change to the reaction contract.

If native scontrol completion has already expired and accounting is disabled,
`scripts/slurm_controller_events.py` can verify the exact submit/allocation/
zero-exit/done events from the daemon-owned controller log, linked to an earlier
native submission snapshot. It records no reconstructed `COMPLETED` state.
The live controller events and all ordinary VASP, geometry, magnetic, input and
force-label checks remain mandatory. Missing, extra or ambiguous events fail.

## One authorized two-server training copy

`paper_training_job.py` owns the original one-job MZ73 submission and reservation.
`paper_training_replica.py` additionally requires the user's separately bound
MZ73 + BUCT2 authorization and a live resource/priority-queued primary job. It
permits one BUCT2 copy of the same logical round: byte-identical request, raw
DFT label, POSCAR, frozen model and 100-epoch recipe. Only the host and installed
Python environment change. The existing matching base model is copied
exclusively to the request's exact path; existing different data are rejected.
Both jobs retain the 1 GPU / 4 CPU / at most 16 GiB / 10-minute limit and no requeue.
UNKNOWN submission reservations prevent automatic repeats.

`reduce_pending_training_memory.py` can lower the still resource-queued primary
from 16 to 15 GiB, with native before/after records and no new job or scientific
input change. The original manifest remains frozen; its scheduler amendment is
recorded separately. This resolved MZ73's 0.52 GiB allocation shortfall.

Use the first result that passes the actual 100 optimizer-update, final-epoch,
raw-request, checkpoint-hash and CUDA checks. A scheduler exit or producer
receipt alone cannot select a winner. A duplicate physical copy does not add
an active-learning round, allow another label or promote the model/TS.

The first accepted DFT label (job 14003) has movable-atom fmax
0.1467082641 eV/angstrom, above the paper's strict 0.05 stopping criterion.
Training jobs 14279 (MZ73) and 2280 (BUCT2) were submitted on 2026-11-13.
Job 14279 started after the memory reduction and failed after 9 seconds during
dataset/sampler initialization: `UnsupportedDatasetError` because the newly
built singleton database lacked integer `natoms` metadata. It did not reach
the training loop. Job 2280 remained queued at this checkpoint; its identical
worker has the same missing-metadata problem. At that checkpoint there was no
trained model, next candidate or second DFT label. Both submissions were
preserved for the separately reviewed correction below. Runtime receipts and
private artifacts stay in the local case and the servers' `/home/sbq/sbq/`
directories.

## Prepared metadata correction

The corrected worker writes one integer `natoms=[49]` row to a fresh
`metadata.npz`, sets its explicit dataset path, and binds its SHA in the input
record. All original raw labels, 18 fixed / 31 free atoms, normalization,
zero energy-loss weight, optimizer, reset policy and 100 epochs remain the same.

`preflight_single_label_dataset.py` reproduced the missing-metadata error in
the actual MZ73 FairChem installation and then passed the repaired sampler and
batched-target checks on CPU. It used the exact original singleton database,
request and raw forces. It constructed no trainer or model and did no training.

`paper_training_metadata_recovery.py` prepares a separate fresh job directory.
It binds the failed native capture, original request and installed preflight.
Preparation carries no execution permission. Submission requires a new exact
user approval for one 1 GPU / 4 CPU / 15 GiB / 10-minute, 100-epoch recovery,
including retirement of the still-pending broken BUCT2 copy. The original
approved budget has `max_training_jobs=1` and `automatic_retries=0`; no recovery
or extra DFT execution is inferred from the previous submission permission.
Failed inputs/outputs and the original source worktree remain frozen.

The user approved that exact package. Recovery job 14292 completed 100 epochs
and 100 observed optimizer updates on CUDA/RTX 4090 in 518.807 scheduler seconds;
old copy 2280 is natively CANCELLED. A temporary Oray access restriction cleared.
Native controller zero-exit events were recovered after the terminal enum had
expired. Independent CPU inspection verified the real checkpoint (4493 finite
model tensors), singleton database, 18-fixed/31-free mask and original raw
forces. The frozen base is unchanged; the new candidate checkpoint SHA is
`209e7a50ce10beb515e19b945fbf12b25591f9ff89077acae6432ba3e16b9406`.
`collect_training_native_exit.py` and `inspect_trained_checkpoint.py` establish
these separate native-exit and checkpoint facts, without model promotion.

## Next candidate and exact DFT validation

`paper_continuation_job.py` reuses the previous trajectory's final geometry and
mode with the newly verified checkpoint; it performs no IDPP, training or VASP.
Job 14304 completed natively with exit 0. Its candidate movable fmax is
0.0093971436 eV/angstrom, C-C is 1.752437 A, and CH/CO remain intact. The 24-frame
trajectory has a maximum 0.05 A adjacent displacement and no fixed-atom drift.
Raw worker JSON/code/structure mappings and an actual top/side geometry review
were checked in work. No candidate overlaps the 513 protected geometries.

`prepare_next_label.py` reuses the first accepted label's exact INCAR, KPOINTS
and POTCAR family/bytes for the new POSCAR. The independently recomputed geometry
and exact-input execution gate allowed only `SUBMIT_DIAGNOSTIC_VASP`.
Canonical job 14307 is the second and final DFT job in the approved extension.
Its queued RAM request was reduced from 16 to 15 GiB
with native before/after evidence, retaining every scientific input and the
60-minute limit. The identical first VASP setup actually peaked at 4.394 GiB.
`monitor_static_label.py` records queue and electronic progress separately;
only final owning-module ingestion may accept a DFT force label. No additional
training, DFT job, vibration, barrier or model/TS promotion is authorized here.

## Accepted r001 label and external budget boundary

Job 14307 reached native Slurm COMPLETED / 0:0 in 47 minutes 15 seconds.
Original outputs returned byte-for-byte; all input and returned output hashes
matched MZ73 and remained unchanged after copying. The owning ingestion checked
normal completion, electronic convergence in 74 steps at EDIFF=1e-6, 49 finite
raw force vectors, the 18-fixed/31-free mask, paired evaluated coordinates and
finite total/atomic magnetic moments. Maximum coordinate difference was
7.8752161e-6 A, below the 1e-5 A tolerance. Total magnetization was
105.4270285 muB, a change of -0.1991487 muB from the prior label; this is not a
magnetic-ground-state determination.

The accepted movable-atom DFT fmax is **0.1098241639 eV/angstrom**, compared with
0.1467082641 before training. It remains above the strict 0.05 stopping target.
The raw paper label SHA is
`fca758bb1a552345d811d45e16f8e5766470bf6427687a6133b8e8b4ae9fe28b`;
the immutable `paper_state.v2.after_label14307.json` SHA is
`6d13b33b213a40904fb0ee5f32548625979b03597c075a755ab091790db2ce7c`.
The owner state is `awaiting_training_request`, with two accepted labels and
no force-converged candidate, validated TS, final energy difference or barrier.

The external user budget has consumed its two additional DFT jobs, 14003 and
14307. The original training failed before epochs; the separately authorized
recovery completed one logical 100-epoch fit and BUCT2 copy 2280 was cancelled.
No further calculation is authorized. A non-executing review proposal and the
owning module's latest-label-only training request are saved in the private
case at `proposals/r002_budget_after_label14307/`. The proposal requests one
100-epoch fit (10 minutes), one BA-Sella continuation (10 minutes) and one
reviewed GPU VASP single point (60 minutes), each at 1 GPU / 4 CPU / 15 GiB on
MZ73, with no retries or replicas. It is explicitly unapproved and requires
fresh resource checks, candidate review and an execution gate before any job.
