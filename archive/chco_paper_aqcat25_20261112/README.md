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
worker has the same missing-metadata problem. No trained model, next candidate
or second DFT label exists. Preserve both submissions and prepare a reviewed
correction before any new execution. Runtime receipts and private artifacts
stay in the local case and the servers' `/home/sbq/sbq/` directories.
