# Fe(110) 11–15: FT512 GPU and DFT submission, 2026-10-29

Current override:the user subsequently requested NSW300 for all15 tasks. See [NSW300 update](nsw300_update.md). The initial80-step submission record below is retained provenance.

15/15 reviewed v5 seeds completed native AQCat25 CUDA pre-relaxation on MZ73 GPU1.
Producer span: 81.131697 seconds. Model SHA256:
`cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0`. This is the newest development-selected
partial FT512 snapshot, not a promoted or per-species calibrated production model.

Every target molecular graph and fixed Fe layer is retained. All15 reached
ML fmax≤0.10 eV/Å;all15 pass work-side endpoint review. Symmetry/permutation-aware
comparison found no duplicates at adsorbate RMSD0.20Å and movable Fe RMSD0.05Å.
All trajectories/raw ML forces, seeds and failures remain preserved. No predicted
energy is admitted as a DFT result, adsorption energy or motif-ranking authority.

All15 exact inputs pass the canonical adsorption preflight, read-only INCAR
custodian and independent POSCAR/INCAR/order/mask/graph readback. DFT: PBE/PAW-PBE,
Fe45 five layers/bottom18 fixed, ENCUT400eV, Gamma5×5×1, ISPIN2, Fe2.2μB initial,
ISMEAR1/SIGMA0.20, EDIFF1e-5, EDIFFG−0.02eV/Å, LORBIT11, 32ranks/job, NSW80.
80steps is an agent-selected screening bound;it does not guarantee convergence.

Fe/O/C/H POTCAR is the exact [Fe,O,C,H] permutation of the reviewed [Fe,C,O,H]
datasets;licensed contents stay on the VASP server. Its hash is
`cfdeb95d5ce5ab92e2ff0c0cdd1cd3870fbbe3a929822c631e09fd828c511a4f`.
13_A first encountered a pre-reservation rejection because its POTCAR source
used an expanded absolute path. Readback confirmed six SUBMITTED and nine
NOT_RESERVED. A new immutable nine-job bundle/gates binds the same verified
POTCAR bytes through ~/sbq. The six submitted jobs were not repeated;no
existing calculation or gate was overwritten. Both submission stages are retained.

Queue observation: `2026-10-29T04:10:59.632504+00:00`. Queue status alone establishes
neither electronic/ionic convergence nor scientific validity.

| Seed | Real LSF job ID | Queue status |
|---|---:|---|
| 11_A | 9927512 | PEND |
| 11_B | 9927513 | PEND |
| 11_C | 9927514 | PEND |
| 12_A | 9927515 | PEND |
| 12_B | 9927516 | PEND |
| 12_C | 9927517 | PEND |
| 13_A | 9927519 | PEND |
| 13_B | 9927521 | PEND |
| 13_C | 9927522 | PEND |
| 14_A | 9927523 | PEND |
| 14_B | 9927524 | PEND |
| 14_C | 9927525 | PEND |
| 15_A | 9927526 | PEND |
| 15_B | 9927527 | PEND |
| 15_C | 9927528 | PEND |

Registry: 375 metadata rows read back;zero scientific result rows.
Primary validation: 35 existing GPU-controller regression tests, then47 scoped
GPU/DFT/input/submission tests passed;Python syntax and scoped Ruff passed.
The isolated source-release checkout passed194 scoped tests. Chemistry/symmetry
helpers and their tests are carried from published seed-preparation commit3111b274.
repo-state sync --safe-only failed on the existing PKG-INFO classification mismatch;
managed state synchronization did not complete;the classification was not repaired.
DFT completion/SCF/local magnetism/final force/final chemistry and site minima
remain unverified. No speedup ratio or global-minimum claim is made.

Next: check these15 jobs on demand, then validate their converged structures
and compare compatible DFT results. No automatic continuation or retry is active.

Canonical live evidence: calculations/fe110_c2_adsorption_11_15_20261020/ft512_gpu_20261029_v1/.
The source-release evidence.zip preserves frozen runtime, exact input bytes,
all ML trajectories, canonical gates, actual submission receipts, queue proof
and metadata-only registry transaction. It contains no checkpoint weights or POTCAR.
The GPU stage used an exact backend-policy direct-execution exception and
native request/producer receipts. No scheduler ID or schema-v2 scheduler-based
handoff was fabricated for this direct run. Producer exit0 proves process exit only.
