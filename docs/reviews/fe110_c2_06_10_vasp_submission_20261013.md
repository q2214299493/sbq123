# Fe(110) C2 species 06–10: fifteen authorized VASP relaxations

## Scope and status

User authorized “15个都提交吧”, then “继续”, after receiving the CUDA
chemistry review. All fifteen original-byte GPU direct-v3 final structures
were returned through work, reviewed and submitted using the canonical
adsorption executor to sunboquan-codex (10.68.0.103, nsgkn_chengdj3).
No GPU-to-VASP direct handoff, new GPU launch, extra pilot or result acceptance.

Each job uses 32 MPI ranks, NP_PER_NODE=32 and unchanged routine_production:
Fe45/five layers, bottom18 fixed, Gamma5x5x1, PBE/PAW-PBE, ENCUT400,
ISPIN2/Fe2.2 initial MAGMOM, ALGO Fast, SIGMA0.20, EDIFF1e-5,
EDIFFG-0.02, IBRION2, POTIM0.20, NSW300. These are maximum300 steps,
not an assertion that300 steps will be needed. No artificial bond restraint.

The first post-submission scheduler snapshot records:

| Candidate | LSF job | Queue state |
|---|---:|---|
| 06_A | 9848799 | RUN |
| 06_B | 9848800 | PEND |
| 06_C | 9848801 | PEND |
| 07_A | 9848802 | PEND |
| 07_B | 9848803 | PEND |
| 07_C | 9848804 | PEND |
| 08_A | 9848805 | PEND |
| 08_B | 9848806 | PEND |
| 08_C | 9848807 | PEND |
| 09_A | 9848808 | PEND |
| 09_B | 9848809 | PEND |
| 09_C | 9848810 | PEND |
| 10_A | 9848811 | PEND |
| 10_B | 9848812 | PEND |
| 10_C | 9848813 | PEND |

This is queue evidence only; electronic startup/convergence, ionic progress,
VASP final chemistry and accepted energy are not established by RUN/PEND.

## Chemistry review and explicit reclassification

All75 returned GPU files match their immutable size/SHA inventory. All15
preserve atom order, cell, fixed coordinates and Selective Dynamics. The
twelve intact candidates have no pairwise surface-symmetry duplicate under
the existing RMSD0.20 criterion; original carbon roles and absolute heights
are preserved, with36 face-preserving clean-slab operations and H permutations.

Three inputs are intentionally retained as reviewed predicted coadsorbates:

| Candidate | Original target | Submitted predicted state | Geometry evidence (Å; zero-based atoms) |
|---|---|---|---|
| 06_A | C–O–CH | CO* + C* + H* | C45–O47 1.1804; C46–O47 4.5409; C45–H48 4.0799; nearest H–Fe 1.7591 |
| 06_B | C–O–CH | CO* + C* + H* | C45–O47 1.1990; C46–O47 3.6548; C45–H48 2.9842; nearest H–Fe 1.7410 |
| 09_B | C–O–CH2 | CH2* + CO* | C45–O47 3.2978; C46–O47 1.2022; C45–H48/H49 1.1104/1.1305 |

These labels classify predicted input geometry, not demonstrated VASP
dissociation, stability or a reaction barrier. Preserve the original target
identity separately; never register these as intact original species unless
final VASP geometry actually re-establishes that identity.

## Validation and evidence

-15/15 adsorption preflights and current hash-bound SUBMIT_VASP gates pass.
-Actual remote POTCAR species order and SHA verified for Fe_C_O_H, Fe_O_C_H,
  Fe_C_H; licensed contents remain remote.
-Each submitted bundle/POTCAR hash verified by the canonical executor;
  immutable attempts and real LSF receipts exist for all15.
-Main workspace: Python compile and scoped Ruff pass;12 adsorption
  composition checks plus57 input/execution/submission regressions pass.
-Independent sbq123 release worktree:62 scoped tests pass on that source base.
-Preflight change supports exactly Fe45/O1/C2/H2 and Fe45/C2/H3 in addition
  to existing reviewed compositions; unsupported neighboring counts still fail.
  No scientific numerical profile or chemistry gate was relaxed.

Authoritative local package:
`calculations/fe110_c2_adsorption_06_10_20261012/vasp_batch_v1/`.
It contains batch_manifest, structure_review, each original POSCAR and VASP
inputs, explicit authorization, preflight/decision, submission attempt/receipt,
scheduler_snapshot, submission_summary and canonical registry plan/receipt.
Only job/input provenance is registered; no numeric ML/DFT energy is accepted.

Remote root:
`~/sbq/Fe110/adsorption/fe110_c2_06_10_20261013_v1/`.

Next action: bounded queue and electronic/ionic progress check; upon completion
review final chemistry and duplicates, then automatically register only
scientifically eligible compatible VASP results.
