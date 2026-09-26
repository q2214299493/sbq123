# User authorization — 2026-09-26

User statement after reviewing the 11-image IS-A→INT06 candidate and its image count:

> 可以先拿去gpu加速吧

Scope: one MZ73 MatRIS epoch6 ordinary ML-NEB run of the exact reviewed 00–10
candidate, then AQCat25 evaluation of the identical final path without relaxation.
Maximum 400 optimizer steps, fmax 0.10 eV/Å, one GPU, four CPU threads, 40 GB
host memory and two-hour allocation. No ML-CI, Sella, added reaction-coordinate
restraints, automatic retry, fine-tuning or VASP submission.

Request SHA-256: `6011d0a9b1a0430e3b273b9180f2d6484683589a81def2d168418696e8bf4d32`.
MatRIS checkpoint SHA-256: `8e53cfb0e54aec7aa918cefae3ce7b4a9488d87231626f7ae4bc98fdebdbeb49`.
AQCat25 checkpoint SHA-256: `e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50`.

Large endpoint displacement remains reviewed evidence; neither a unique saddle
nor an independently validated low point is assumed. GPU results are predictions
only and must return to work for review before any VASP handoff.
