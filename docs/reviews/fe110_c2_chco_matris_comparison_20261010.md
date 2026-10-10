# CH–C–O repair review and same-structure force comparison

User scope: review the anomalous CH–C–O configuration, then compare MatRIS
and AQCat25 on existing exact VASP label structures. No production-model
replacement, model training, VASP parameter change or additional VASP submission.

## CH–C–O geometry

Live read-only snapshot: `calculations/fe110_five_c2_adsorption_20261006/chco_reassessment_20261010/review.json`.
Atom indices below are zero-based; C45–C46–O47, with H48 attached to C45.

| Candidate | Scheduler | Latest C–C / C–O / C–H (Å) | Interpretation |
|---|---|---|---|
| Original direct VASP 9839757 | RUN | 2.760969 / 1.201483 / 1.109468 | No longer intact CH–C–O |
| Alternative 9842107 | RUN | 1.432429 / 1.281365 / 1.105730 | Intact at this snapshot, not yet accepted |
| Existing repaired input 9842136 | PEND | 1.396793 / 1.307043 / 1.096964 | Reviewed intact GPU candidate, VASP not started |

The existing repair changes the central-carbon anchor to short bridge and
reorients the chain parallel to the Fe rows. It adds no bond/site restraints;
atom order, cell, bottom-18-Fe fixed mask and DFT protocol are unchanged.
Its submitted POSCAR is exactly the previously reviewed GPU2176 output
(`605b1ca29790b04236e9d70512a8106928a35d188bdd14c4f4a784dbabc754ae`).
Reused this correction rather than generating/submitting a duplicate.

The original placement fragmented in both GPU and VASP trajectories. This
does not establish that every intact CH–C–O state is unstable, nor that the
failure is solely a force-model error. No live job was stopped or modified.

## Frozen comparison

MatRIS inference job **2180**: producer exit 0, ten exact predictions returned.
MZ73 lacks durable Slurm terminal accounting; producer completion is not a
scheduler DONE claim. Legacy graph converter fallback was used successfully.

- MatRIS: provider Fe–C–O–H baseline, SHA256
  `1e6a85b33db075ad1637eca7537084024a694b1340358911212d8a5c518c6601`.
  The O–H-specific epoch-6 checkpoint was not silently promoted to adsorption.
- AQCat25: saved job2177 predictions, checkpoint SHA256
  `e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50`.
- Exact same ten POSCAR/CONTCAR bytes, atom order, ASE PBC and fixed mask;
  no relaxation. Fixed Fe0–17 excluded identically, giving 306 movable vectors.
- Five existing jobs' paired initial/final structures: 01_cfg2, 01_cfg1,
  02_cfg2, 04_cfg0, 05_cfg0. **No species03 CH–C–O coverage.**

Vector RMSE, eV/Å:

| Group | AQCat25 | MatRIS baseline |
|---|---:|---:|
| All movable atoms, both stages | 0.142569 | 0.101360 |
| Initial adsorbate | 0.264832 | 0.159047 |
| Final adsorbate | 0.185275 | 0.157218 |
| Final C | 0.198028 | 0.162060 |
| Final O, only two atoms | 0.332249 | 0.258820 |
| Final Fe | 0.037950 | 0.091038 |
| Final H | 0.028731 | 0.089728 |
| Final all movable atoms | 0.072864 | 0.101098 |

MatRIS improves the sampled C/O errors but is worse for final Fe/H and final
all-movable force RMSE. Do not call it uniformly better or infer faster
relaxation. Initial/final pairs are correlated, oxygen coverage is tiny, and
this is not independent held-out validation or a global calibration update.
No cross-model absolute energies were compared.

Full grouped MAE/RMSE/P95/maximum metrics and immutable source bindings:
`calculations/fe110_five_c2_adsorption_20261006/gpu_matris_force_diagnostic_submission_v1/model_comparison.json`.

## Verification and next step

Local syntax/import checks, Ruff and 14 directly related tests passed.
Remote no-model preflight verified input/checkpoint hashes, order, cell and
fixed masks; shell syntax passed. Returned producer/model/input/output hashes,
sample coverage and finite N-by-3 forces passed validation.

Next: complete intact CH–C–O VASP coverage and freeze disjoint adsorption
validation before deciding model selection or a targeted fine-tuning proposal.
No new calculation or training is authorized by this report.
