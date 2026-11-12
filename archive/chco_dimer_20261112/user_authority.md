# User-selected CH + CO Dimer refinement

2026-11-12 Asia/Shanghai, current Codex conversation:

> 0.6并不算大吧 直接选取最高峰 进行dimer吧

Scope: prepare and submit one Fe(110) CH* + CO* -> CHCO* VASP Dimer
from the reviewed completed ordinary NEB 9994246 image 05, with 04 and 06
as its local mode neighbors. Use the unchanged compatible production DFT
branch and 32 MPI ranks, 32 per node. This does not authorize another NEB,
GPU run, training, stopping other jobs, or frequency calculation.

The persistent 0.62833 A C-C scalar-coordinate interval remains a parent
sampling warning. It is not a 0.62833 A single-atom jump. The local triad
passed its hard gate; final MODECAR and submission preflight remain required.
Use the existing explicit Dimer-preparation branch and a new bound decision;
preserve the earlier default REBUILD_PATH decision. No policy changes.
