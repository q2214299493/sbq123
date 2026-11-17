# Shared compute pool

The pool is registered in both project `AGENTS.md` and the user-level
`C:/Users/86177/.codex/AGENTS.md`, so future compute chats can discover it.
The exported user-rule block is `configs/codex_compute_pool_instructions.md`.

For every new compute task, consider all four configured resources. Run:

```powershell
C:\Anaconda\python.exe -m scripts.gpu_resources --include-cpu
```

The command only inspects resources. Its default without `--include-cpu`
retains the three-GPU check. A nonzero exit means at least one snapshot is
incomplete; inspect each host separately. SSH success and free device memory
are not task admission or a reservation.

| Resource | Backend | SSH | Hardware / scheduler | GPU task root |
|---|---|---|---|---|
| BUCT / MZ73 | aqcat_gpu | sbq, shared gateway port 36039 | 4 RTX 4090 / Slurm gpu | /home/sbq/sbq |
| BUCT2 | buct2_gpu | buct2-gpu (port 55909) | 5 A800 / Slurm gpu | /home/sbq/sbq |
| BUCT3 | buct3_gpu | sbq, shared gateway port 57396 | 4 RTX 4090 / Slurm compute | /home/sbq/sbq |
| CPU | vasp | sunboquan-codex | CPU cluster / LSF | account root /home_gkn/users/nsgkn_chengdj3 |

The shared gateway is defined in `configs/execution_backends.yaml`. Use strict
host-key checking and the configured identity/SSH aliases. Never copy private
keys between hosts. CPU login hostname is not the compute-node selection.
Existing reviewed CPU calculation paths retain their scope.

## Selecting a host

1. Read the fresh four-host snapshot. Scheduler allocation and device memory
   describe different facts. Login-session NVML denial under Slurm leaves
   device availability unknown; it does not prove a broken driver.
2. Check task software, input/model hashes, canonical paths, memory/CPU needs,
   scheduler partition and existing owning-module execution authority.
3. Prefer an eligible host with available capacity. Validate CUDA, the assigned
   GPU UUID and a bounded model operation inside its allocation before science.
4. Bind the task to that host and preserve logs/exit evidence. Changing hosts
   requires a fresh binding; never edit a submitted/frozen job in place.
5. Return candidates/results to `work` for the owning scientific review.

GPU pool roles cover ML inference, candidate relaxation/search and training.
General VASP/VTST stays on the CPU backend; explicitly authorized GPU-VASP
cases retain their scoped backend. Registration does not authorize arbitrary
new scientific jobs, duplicate execution, cancellation or model promotion.
The existing CHCO AQCat25 checkpoint is a development checkpoint and is not a
pool-wide production-model default.

## Runtime verification

2026-11-17 verified results:

- All four SSH connections, GPU work roots and scheduler queries passed.
- MZ73's existing environment completed a separately authorized 100-epoch CUDA
  training job. Its installed environment was preserved.
- BUCT2 and BUCT3 now have independent copies of the reference Python 3.10.12,
  PyTorch 2.4.1+cu121, graph extensions, ASE, Sella, Arkimede and AQCat25/FairChem
  dependencies. All 12 module imports passed; 11 entry-file hashes match MZ73
  and one module is a namespace package. The checkpoint
  has 4493 finite state tensors. This is not a full model-inference or training
  acceptance test on either newly deployed host.
- BUCT3 passed a controlled one-GPU Slurm allocation (job 433): one visible
  RTX 4090, CUDA dense/scatter/sparse operations, GPU UUID
  `GPU-c51e655f-5dca-d4a3-63ea-fcc4732ed064`.
- BUCT2's immediate controlled allocation (2584) could not acquire a GPU because
  the node was busy. CPU dependency/checkpoint checks passed; its CUDA execution
  remains unverified until a later allocated task preflight.
- CPU account root and LSF host/queue queries passed. This pool setup did not
  revalidate every task's CPU VASP/MPI binary or launch a VASP calculation.
- The software bundle and checkpoint hashes matched at both destinations. Two
  restricted, expiring LAN transfer authorizations were revoked after copying.

Prepared paths on BUCT2 and BUCT3:

```text
/home/sbq/sbq/compute_pool_20261117/deployed/runtime/python
/home/sbq/sbq/compute_pool_20261117/verify_runtime.py
/home/sbq/sbq/compute_pool_20261117/deployed/models/aqcat25_ft512_development.pt
```

The relocated Python launcher explicitly appends its venv site-packages while
preserving MZ73's extra/vendor precedence. Final launcher SHA-256:
`67d372f4548c1411fb41b282d6d093ed7677b1edef9dc80663c86a525d9b2b4f`.
Bundle SHA-256: `781b107cc851983ee566c5c7d4b04a90eca5a64fe218b3b5cd4a02691daa6b75`.
Development checkpoint SHA-256: `cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0`.

Set each task's TMPDIR and XDG/Torch/HuggingFace/CUDA caches within that host's
`/home/sbq/sbq/`. The verifier runs dependency/checkpoint checks by default;
`--cuda` additionally requires an existing one-GPU Slurm allocation. It does not
submit a job or establish scientific acceptance. Always use a fresh task-specific
model/input and execution binding rather than a stale setup receipt.

No GPU-VASP installation was found at MZ73's executable path on BUCT3. GPU-VASP
on BUCT2/BUCT3 is not admitted by this configuration; select the authorized CPU
backend or a separately verified and explicitly scoped GPU-VASP backend.


The CHCO paper continuation now has an explicit candidate-only BUCT3 binding
in `paper_continuation_job.py --backend buct3_gpu --host-preflight FILE`.
It preserves the frozen scientific worker, protocol, checkpoint identity and
iteration resources. A separate exact-state host preflight binds the actual
user request, controlled CUDA receipt and byte-verified checkpoint import.
Capture/return checks require the selected hostname and exact native job
identity. No BUCT3 VASP authority is added; DFT gates retain the MZ73 owner.
