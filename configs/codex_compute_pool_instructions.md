

<!-- BEGIN USER COMPUTE POOL 20261117 -->
## Shared compute resources

For future server-based compute tasks, consider the user's shared pool:
BUCT / MZ73, BUCT2 and BUCT3 (GPU), plus sunboquan-codex (CPU / LSF).
Canonical SSH endpoints and roles are in
`C:/Users/86177/Desktop/work/configs/execution_backends.yaml`.
Prepared runtimes and verification limits are in
`C:/Users/86177/Desktop/work/docs/COMPUTE_POOL.md`.
Before choosing a host, run `C:/Anaconda/python.exe -m scripts.gpu_resources --include-cpu`
with working directory `C:/Users/86177/Desktop/work`, then check the task's
software, model/input hashes, scheduler allocation, canonical write paths,
and existing scientific execution authority. Prefer an eligible available host.
Keep GPU task inputs, logs, temporary files, caches and outputs under that
host's `/home/sbq/sbq/`. CUDA and assigned GPU UUID must be checked inside an
allocation before model execution. BUCT2 CUDA is not yet validated because
its GPUs were busy during setup; pool membership does not prove readiness.
Resource registration does not authorize new expensive calculations, duplicate
jobs, cancellation, model promotion, protocol changes or transfer of a
host-bound authorization. Preserve running jobs and task-specific budgets.
Never read, display, copy or modify private-key contents.
<!-- END USER COMPUTE POOL 20261117 -->
