# Fifteen C2 adsorption candidates: verified CUDA restart

User explicitly approved: “同意停止并修正后 GPU 重启”. This supersedes the
pending-stop question in the earlier direct-trial report; that report and all
v1/v2 artifacts remain unchanged.

## Previous CPU attempt preserved

PID114670 had already exited before the authorized stop check. No signal was
sent. Its original producer record reports exit0 and all15 candidates completed
between 2026-10-13 10:24:51 and 10:47:52 Asia/Shanghai. This is CPU producer
completion, not scientific adsorption acceptance. Sixty POSCAR/result/manifest/
exit-record files were hash-inventoried remotely and registered as predicted
outputs; nothing was deleted or converted into an accepted energy.

## Actual GPU run

- Run ID: `direct-fe110-c2-0610-20261013-v3`, not a Slurm job number.
- Detached parent PID: `121917`; scheduler NONE, scheduler job ID null.
- Started 2026-10-13 11:36:36 Asia/Shanghai on MZ73.
- Physical GPU1 UUID: `GPU-450609b3-d1fd-ac33-d03a-79891be402da`.
- `execution_device.json` proves actual model parameter device `cuda:0`.
  CUDA_VISIBLE_DEVICES limits visibility to physical GPU1, so logical cuda:0
  means that physical GPU, not physical GPU0.
- A live compute process was observed on this UUID, using about2700MiB;
  GPU1 aggregate usage was2723MiB and utilization36% at the startup checkpoint.
- 06_A completed71 LBFGS steps at predicted fmax0.060894eV/angstrom, below the
  unchanged ML target0.10. No fatal model error appeared at that checkpoint.
  This is not VASP force convergence or evidence of the intended final chemistry.

All15 original initial POSCARs, checkpoint, optimizer and80-step budgets remain
unchanged. They run serially on one GPU; there is a7200-second parent bound and
a cooperative lock, not an administrator reservation. Shared services and other
users' jobs were untouched. VASP submission remains separately authorized.

## What changed and what was verified

The corrected candidate runner sets `cpu=False` and asserts actual model tensors
are CUDA-resident before optimization. The parent rejects an entrypoint with no
explicit CUDA keyword and requires each successful producer to retain matching
CUDA/physical-UUID evidence. No numeric scheduler ID is invented.

Local syntax compilation and25 device/backend/handoff tests passed again. The
same parent code's162 scoped runtime/device tests passed in the preceding turn;
the current turn did not rerun that full set. Remote frozen-input/no-model
preflight passed, followed by actual CUDA model loading and LBFGS inference.
Canonical registry readback shows old CPU workflow done and new GPU workflow
running; quick_check=ok, no foreign-key violations. Predictions remain outside
accepted calculated-result tables.

## Evidence and handoff

- `gpu_direct_v2/user_authorized_stop_receipt.json`: PID identity/exit check,
  explicit authorization and no-signal disposition.
- `gpu_direct_v2/direct_batch_exit_record.json`, `cpu_output_inventory.json`:
  preserved original CPU completion and60 output hashes.
- `gpu_direct_v3/direct_request.json`, `restart_review.json`, manifest and
  remote preflight: fresh bound CUDA execution package.
- `gpu_direct_v3/direct_launch_receipt.json`, `direct_started.json`,
  `startup_checkpoint.json`: exact producer/startup/device/process evidence.
- `gpu_direct_v3/registry_input_*`, `registry_launch_*`: canonical append-only
  preservation, input and actual-launch receipts; one new GPU batch calculation
  tracks15 candidates, not112 new physical structures.

Next: collect the completed GPU producer records and structures, then review
convergence, graph/H placement, surface contacts and duplicate classes in work.
Do not infer fifteen stable configurations, reportable adsorption energies,
VASP acceleration benefit or scientific acceptance from GPU completion alone.

Existing global state-sync PKG-INFO conflict remains unrelated and unrepaired.
