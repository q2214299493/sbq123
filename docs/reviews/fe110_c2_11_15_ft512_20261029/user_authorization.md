# Current user instruction, 2026-10-29

> 利用新微调的AQCat25 gpu加速 然后提交dft

This authorizes the fifteen existing reviewed Fe45 seeds 11_A through 15_C
for newest fine-tuned AQCat25 pre-relaxation, work-side geometry review, and
subsequent DFT submission. The selected checkpoint SHA256 is
`cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0`.

Implementation bounds chosen by the agent: one GPU batch, at most 600 seconds,
80 ML steps per seed, then fifteen 32-rank VASP screening relaxations with
NSW=80 and EDIFFG=-0.02 eV/A. These are conservative implementation bounds,
not numerical budgets quoted by the user. Existing scientific settings remain
unchanged. No automatic continuation, resubmission, model promotion, or
scientific acceptance is authorized by the execution receipts themselves.
All VASP submissions require the canonical current hash-bound execution gate.
