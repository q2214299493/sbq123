# SCF9754110: reviewed two-parameter mixing control submitted

2026-09-13: user approved the reviewed control and submission, then separately
authorized stopping current SCF9753825. Canonical STOP_JOB returned a termination
receipt; a subsequent live scheduler query confirmed EXIT. Outputs were preserved.

Exactly one new diagnostic-static job **9754110** was submitted through the current
hash-bound SUBMIT_DIAGNOSTIC_VASP gate. Initial live checkpoint: **PEND** in
Gkn_normal, 80 MPI ranks, excluding gknew0440 with span[ptile=32]. No actual MPI
startup, electronic convergence, saved state or TS acceptance is claimed.

Only AMIX=0.2 and AMIX_MAG=0.8 differ from SCF9753825's input. The reviewed candidate
SHA-256 remains `61b24fd7c4699e466b3ea3559460a4199934ba10ad4d10b109d6bfe4d9bea7cf`.
All other INCAR entries and exact POSCAR/KPOINTS/POTCAR.spec/script.lsf are retained.
The executor verified the remote approved POTCAR hash before bsub. This is a fresh
directory, not a restart from the failed electronic state. No pilot, Dimer or
additional static was submitted.

Local package:
`calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_mid_scf_mixing_control_20260913/`

Remote package:
`sunboquan-codex:~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_scf_mixing_control_20260913`

Review rationale and limitations: `docs/reviews/scf_mixing_control_20260913/README.md`.
Stop authorization/gate/receipt: `archive/scf_mixing_control_20260913/stop9753825/`.
The package retains both terminal-old and pending-new scheduler evidence, the
submission reservation, successful submission receipt, preflight and current gate.

Validation performed: Python syntax check of the bounded orchestration script;
exact candidate/source identity and two-key semantic comparison; canonical
diagnostic_static preflight PASS; custodian read-only static input check without
blockers/warnings; remote bash -n exit 0; gate revalidation and remote full input
hash verification in the canonical executor. No scientific calculation was run
as a software test.

Old-stop and new-submission provenance were registered together: 14 rows across
calculation/job/status/file tables, with zero accepted energies or TS records.
Database integrity returned ok and foreign-key errors were zero. Both job IDs
were queried back. The bounded orchestration scripts passed compilation and Ruff.
The review-free current-task proposal was applied. Global safe sync still reports
an unrelated classified PKG-INFO drift; no such file was modified here.

Next: check actual MPI/SCF startup and output integrity. Require EDIFF=1e-7 normal
completion, unchanged geometry and completed valid WAVECAR/CHGCAR, then compare
energy/forces/magnetic state with successful SCF9752745 before separately approved
restart reproducibility verification. This test does not by itself establish a TS
or prove a unique cause of the earlier SCF instability. No further retry is authorized.
