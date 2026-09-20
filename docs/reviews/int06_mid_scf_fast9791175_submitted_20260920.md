# INT06–MID: authorized Fast static diagnostic

User authorization: “改为fast 再来一次”. Submitted job **9791175** to
`sunboquan-codex`, LSF `Gkn_normal`; first post-submission scheduler check: **PEND**.

This is a fixed-geometry electronic diagnostic, not NEB or Dimer. Relative to
the preceding All diagnostic, only `ALGO = All` changes to `ALGO = Fast`.
Preserved: original GPU1635 image05 geometry, 80 MPI ranks, cold start,
`NSW=0`, `IBRION=-1`, `NELM=200`, `EDIFF=1e-7`, `SIGMA=0.20 eV`,
PBE/ENCUT400, Gamma5×5×1, magnetic initialization and exclusion of gknew0440.

Input difference audit, INCAR review, submission preflight and hash-bound
`SUBMIT_DIAGNOSTIC_VASP` gate passed. Remote POSCAR/INCAR/KPOINTS/script hashes
match the prepared input. No electronic convergence or scientific result yet.
Earlier Fast Dimer 9781734 had electronic failures; this controlled static
retry is not evidence that Fast will resolve them.

Run package:
`calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_mid_dimer_gpu1635_parent_scf_fast_20260920`.
Canonical records: `submission_record.json`, `execution_gate_decision.json`,
`submission_preflight.json`, `diagnostic_input_review.json`,
`user_execution_authorization.json`.

Remote directory:
`~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_dimer_gpu1635_parent_scf_fast_20260920`.

POSCAR SHA256: `0bada36d9cb23959e3a956c97058eb09b35723a9750e099ea6f11f0941c58ece`.
INCAR SHA256: `dc6dd967ba651f92873834e5b4488a2b1638c317220c2f6cdf3ec49510d8010a`.
Bundle SHA256: `c664e71345e2fa7f95559b47957b73b1c1da577998ef2647e4301f90db989e86`.

Previous All job 9790254 was last observed RUN despite stalled output after an
EDWAV nonorthogonal-gradient error. It has not been cancelled: separate user
confirmation was requested. No authorization to submit NEB, Dimer, additional
retries or training is inferred from this one-job request.

Next: inspect 9791175 electronic progress, termination, forces and magnetic
branch before choosing a subsequent calculation.
