# Compute-pool setup helpers (2026-11-17)

One-off software setup only; no scientific submission authority.
The supported daily entry is `python -m scripts.gpu_resources --include-cpu`.
Runtime paths, final hashes, allocated CUDA verification and remaining limits
are recorded in `docs/COMPUTE_POOL.md`.

- `build_reference_runtime.py` created the verified reference archive on MZ73
  without modifying its working environment. The relocated launcher required
  the explicit site-packages and dependency-precedence adjustments documented
  in COMPUTE_POOL; this archive builder alone is not a ready installer.
- `deploy_reference_runtime.py` preserves the initial slow local relay attempt.
  That software-only transfer was stopped and its partial files retained.
  Final deployment used a direct authenticated LAN copy with restricted,
  source-IP-bound, expiring read-only keys; both temporary authorizations were
  removed after verified extraction. Do not rerun old setup writes in place.
- `verify_runtime.py` is the bounded import/checkpoint verifier deployed to the
  servers. `--cuda` requires an allocated Slurm GPU; it checks dense/scatter/
  sparse operations, one CUDA device and NVML UUIDs. It does not submit work,
  train a model, calculate a DFT label, promote a checkpoint or accept a TS.

Per-host deployment/import/failed-attempt/control-allocation receipts are local
runtime evidence and are excluded from the source release. Environment archives,
weights and credentials must not be committed. Existing working environments,
scientific inputs and running calculations were preserved.
