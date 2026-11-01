# Current user authorization

Client date: 2026-11-02, Asia/Shanghai.

Original instruction:

> 对证据齐全的构型进行正式登记审核， 然后录入吸附表中 然后提交16-19

Separate GPU resource answer:

> 允许GPU0受限共享运行

Scope: the twelve reviewed16–19 A/B/C candidates. Follow the previously
requested GPU-before-DFT adsorption workflow. GPU execution is one bounded
600-second shared-GPU0 batch with16GiB allocator limit and no resident-process
termination. Work-side review must precede any VASP handoff.

VASP preparation inherits the active routine-production profile:32ranks,
32/node, at most300ionic steps, EDIFFG-0.02, ALGO Fast, SIGMA0.20 and the same
Fe45/PBE/400eV/5x5x1 basis. No pilot, automatic retry, continuation, training,
reference calculation, protocol change or unrelated job cancellation is added.

Work-side review found10intact ML endpoints.16_B/18_A underwent predicted H
detachment; use their unchanged reviewed original seeds for the requested
intact-target DFT test. This fallback is the workflow reviewer decision, not
a claim that the user approved a newly generated structure or that ML was
successful for those two seeds. Preserve the predicted dehydrogenated outputs.
