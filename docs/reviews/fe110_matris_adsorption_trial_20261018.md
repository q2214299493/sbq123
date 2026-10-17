# Fe(110) MatRIS-primary adsorption GPU trial — 2026-10-18

## Scope and actual execution

The user explicitly approved direct execution on an idle GPU2 after being told
that MZ73 Slurm was down: “你尝试一下 授权”. Authorization is preserved in
`archive/fe110_matris_adsorption_trial_20261018/authorization.md`.

Six existing original seeds: **06_C, 07_B, 07_C, 08_A, 09_A, 10_A**.
These are the exact raw inputs used by the prior AQCat25 batch, not its
relaxed outputs. Local structure review, provenance, atom order, Fe45 cell and
bottom-18-Fe fixed mask are retained. No new motif or external data is introduced.

- Primary: provider-baseline `MatRIS_4M_FeCOH_compliant.pth.tar`, SHA256
  `1e6a85b33db075ad1637eca7537084024a694b1340358911212d8a5c518c6601`.
- Not the OH-specific epoch6 checkpoint. AQCat25 results remain comparison data.
- Same ASE LBFGS, fmax0.10 eV/Å, maximum80 steps; no additional bond restraints.
- One GPU2, physical UUID `GPU-7ec6ab8a-91a2-450d-04c1-a0d472452b5b`;
  serial candidates,4 CPU threads, maximum1800 seconds under the controller.
- Remote root:
  `/home/sbq/sbq/aqcat25_ts_pilot/fe110_c2_matris_adsorption_trial_20261018_v1`.
- Execution ID: `direct-fe110-matris-adsorption-20261018-v1`.
- Launch receipt: PID2398967,2026-10-17T16:19:43.389193+00:00
  (2026-10-18 00:19:43 Asia/Shanghai). This is **not** a Slurm/LSF job ID.
- Request SHA256:
  `0eedaf3fa3b820bf4e88d0388fdfc17b66692ed234ecd833c648dcdd2c942a3f`.

## Checks actually performed

The CPU-only file/model-hash, six source handoffs, fixed-mask, source geometry
and package preflights passed. The remote checked GPU2 had no compute process
and at least20GB free before launch; no other process or service was modified.
The launch is write-once and is guarded by a per-UUID file lock, another GPU
availability check and a walltime-bound child process group.

Each model process must prove CUDA parameter placement and the physical UUID.
No CPU fallback is accepted. The legacy graph converter fallback seen in the
provider runtime is logged; it does not imply CPU model inference.

Python syntax and scoped Ruff passed. The47 related tests passed: backend
contract, schema-v2 handoff, direct batch, MatRIS adapter, existing same-structure
benchmark and adsorption execution adapter. The original AQCat25 dispatch remains
the default for its old request.
No VASP, training, promotion or existing-job change was performed.

## Completed GPU trial and returned review

The canonical batch receipt records exit0, all six producers returned, finishing
2026-10-17T16:20:43.111986+00:00 (2026-10-18 00:20:43 Asia/Shanghai).
Total batch runtime was **59.653618 seconds**. All six returned schema-v2
handoffs, source hashes, actual CUDA GPU2 bindings, cell/order/fixed-layer
invariants passed local checks. No emergency Fe–adsorbate overlap was found.

| Candidate | AQCat same-seed ML steps | MatRIS ML steps | MatRIS fmax eV/Å | Review |
|---|---:|---:|---:|---|
|06_C|27|80|0.275277|Not ML-converged; predicted CO+C+H, not intact C–O–CH|
|07_B|19|36|0.096194|ML-converged; graph preserved|
|07_C|40|77|0.090252|ML-converged; graph preserved|
|08_A|48|63|0.096599|ML-converged; graph preserved|
|09_A|39|63|0.090357|ML-converged; graph preserved|
|10_A|43|54|0.090401|ML-converged; graph preserved|

06_C now has C45–O47=1.200243Å and C46–O47=3.724365Å; the C–H bond is
also lost in the full geometry graph. The original pair-distance contract alone
said pass, so the work-side full-graph check is retained and this result is
explicitly reclassified as a prediction, not accepted as the intended species.

Five of six passed the model force criterion and preserved the complete graph.
MatRIS took more ML steps than the matched AQCat run on every tested seed;
this does not determine downstream DFT convergence or total VASP acceleration.
No default-model switch is justified solely by the present GPU test.

## Interpretation and next checkpoint

Outputs are predicted candidates only; their returned handoffs deliberately say
`uncalibrated`. ML optimizer success, graph preservation and engineering success
are reviewed separately. A changed graph is recorded, not hidden by constraints.
All initial/final per-atom predicted forces and optimization trajectories are
retained. Final energies are not registered as DFT adsorption energies.

The canonical receipts and all six outputs have been collected under
`returned_v1/`, with `returned_review.json` and `returned_summary.csv`.
Do not compare raw absolute energies across the two models. New-pose
VASP agreement and actual VASP-runtime speedup remain unverified until a later,
separately authorized matched DFT comparison. Existing15 VASP jobs are untouched.

## Files

- Package: `calculations/fe110_c2_adsorption_06_10_20261012/matris_direct_v1/`.
- Immutable package manifest and direct request; initial `trial_review.json`;
  `remote_preflight_record.json`; canonical `direct_launch_receipt.json`.
- Source preparation/deployment and authorization:
  `archive/fe110_matris_adsorption_trial_20261018/`.
- Adapter: `scripts/adsorption/matris_adsorption_relax.py` and its shell wrapper.
- Controller: `scripts/adsorption/direct_gpu_batch.py`; the exception is scoped
  by exact candidate names, backend, provider checkpoint, optimizer limits,
  GPU identity and walltime in `configs/execution_backends.yaml`.
