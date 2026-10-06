# Authorized adsorption GPU batch

- User authority: 2026-10-06, `先提交gpu加速`; adsorption pre-relaxation only.
- Active job at capture: MZ73 Slurm **2139**, RUNNING.
- Model: AQCat25 demo_single; checkpoint SHA256 `e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50`.
- Inputs: 12 candidates, counts **3 / 2 / 1 / 3 / 3** for the five exact species in REVIEW.md.
- Budget: one GPU, four CPU cores, 32GiB host memory, two-hour limit; each candidate at most80 LBFGS steps, fmax0.10eV/A.
- Only bottom18 Fe fixed. No artificial internal-bond/height forces. Monitored pairs do not establish final chemical identity; the generic runner's empty-rule connectivity pass is not chemical acceptance.
- Preserve CCH2 cfg0 for height review and CHCO cfg1/2 as height-only raw variants; no claim of twelve distinct stable minima.

## Engineering failure evidence

2136,2137 and2138 failed before any candidate optimization. Inputs were unchanged.
MZ73 `/home/sbq/sbq` resolves to `/home/ubuntu/hdd/sbq/sbq`; two legacy bootstrap guards compared resolved paths against the lexical root. The task-local runtime corrects both checks, keeps lexical and canonical containment, pins cache/temp paths within the task root, and stops the batch after the first producer execution error. Global helpers and scientific configurations were not changed. Earlier remote packages and receipts remain intact.

Validated: Python syntax; twelve schema/hash/order/Selective Dynamics handoffs; remote ASE loading without running a model; shell syntax; canonical containment positive and escape negative tests; frozen package file hashes and checkpoint hash. These are engineering/input checks, not final adsorption convergence or VASP validation.

Exact package: `calculations/fe110_five_c2_adsorption_20261006/gpu_batch_v4/`.
Batch manifest SHA256: `efa84ef9a0a77ab4e4ec1aaa94b6fe83be4980a434eb25c410241e080a27ac03`.
Remote: `/home/sbq/sbq/aqcat25_ts_pilot/fe110_five_c2_adsorption_20261006_gpu_v4`.
Scheduler receipts: `calculations/fe110_five_c2_adsorption_20261006/gpu_submission_evidence/`.

Next: collect producer exit records, returned manifests and structures; validate and assess chemistry, sites, convergence and duplicates in work. No VASP submission or adsorption-energy database acceptance is authorized by this GPU batch.
