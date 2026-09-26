# IS-A → INT06 GPU1793: submission and bootstrap failure

User authorized the reviewed 11-frame path with “可以先拿去gpu加速吧”.
Request `6011d0a9b1a0430e3b273b9180f2d6484683589a81def2d168418696e8bf4d32`
freezes MatRIS epoch6 plus AQCat25 fixed-path audit, ordinary ML-NEB only,
400-step ceiling, fmax0.10 eV/Å, no added restraints, no automatic retry/VASP.
Local structure/review binding and remote image/runtime/checkpoint hashes PASS.

GPU job1793 was submitted once. Stored `scontrol show job1793` reports FAILED,
NonZeroExitCode, 2:0, runtime2 seconds. The actual producer failure receipt is
`producer_exit_record.failure.1793.1703571.json`. No runtime_state/restart,
optimizer log, model inference or path force output was produced in `output/run1`.
This is an execution failure, not evidence against the path or force model.

The wrapper calls the shared environment setup before model execution. Slurm's
TMPDIR=/tmp is outside the mandatory remote write boundary and causes its
remote-path check to return2. CPU-only job1794 (one CPU, no GPU/model) confirms
that scheduled environment value; all other relevant cache variables are unset.
Work-side remote preflight used an SSH environment without the Slurm TMPDIR,
so its PASS did not cover this batch-environment condition.

Minimal fix: explicitly export TMPDIR=/home/sbq/sbq/aqcat25/tmp in the next
submission. No structure, model, physical parameter, image count or optimizer
change. The helper's no-model setup check passes with that value. A fresh output
directory and submission receipt are required; failed outputs must be preserved.
Retry is prepared only and needs a separate user authorization; no second GPU
model run has been submitted. Future batch preflight must verify the effective
scheduled writable environment, not only SSH-side imports and file hashes.

A separate bounded shell-prefix diagnostic did not run models and generated
an artificial trap receipt in `output/dual_model_smoke_1793`; that directory is
excluded from scheduler/producer evidence. Only the original `output/run1`
receipt above describes the actual GPU allocation.

Package: `calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_is_a_int06_path_20260926/gpu_execution_20260926`.
