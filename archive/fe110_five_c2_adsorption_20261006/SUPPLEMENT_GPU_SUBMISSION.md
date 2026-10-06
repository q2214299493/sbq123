# Supplemental adsorption GPU submission

User authorization: 2026-10-06, `提交gpu加速`.

- MZ73 Slurm **2142**, **RUNNING** at 2026-10-06 23:34:59 Asia/Shanghai.
- Five sequential candidates: `01_extra1`, `02_extra1`, `02_extra2`, `03_extra1`, `03_extra2`.
- AQCat25 demo_single checkpoint SHA256 `e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50`.
- Budget: one GPU, four CPU cores, 32GiB host RAM, 120 minutes; maximum80 LBFGS steps/candidate, fmax0.10eV/A.
- Only bottom18 Fe fixed. No internal-bond, height or site forces. All adsorbate pairs monitored; an empty generic connectivity-rule list is not chemical acceptance.
- Exact package manifest SHA256 `eba3524bc6a64800dd93a849824ea40adeb1fa887a37eda059fe64ccb47beda6`.
- Remote `/home/sbq/sbq/aqcat25_ts_pilot/fe110_five_c2_adsorption_20261006_gpu_supplement_v1`.
- Local package `calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_v1/`.
- Raw submission/scheduler/preflight receipts `calculations/fe110_five_c2_adsorption_20261006/gpu_supplement_submission_v1/`.

Validated: Python syntax, focused Ruff, four structural regression tests, five local schema/hash handoffs, remote package/checkpoint hashes, ASE atom-order/fixed-layer loading and three shell syntax checks. Remote preflight ran no model. Existing verified task-local runtime reused without modification; prior packages remain intact. Exclusive local and remote submission reservations prevent silent duplicate submission.

Not validated yet: relaxation convergence, final exact molecular graphs, final sites, post-relaxation duplicates or any DFT adsorption energy. Initial nominal counts3/3/3/3/3 are not a claim of three stable minima per species. Calibration remains near-relaxed adsorption only; no calibrated uncertainty or TS claim.

Existing10VASP jobs9839748–9839757 were not changed or queried. No additional VASP submission, model fine-tuning or automatic resubmission authorized. Next: collect2142 outputs into work for hash, chemistry, site, convergence and duplicate review.
