# Authorized banner-safe submission recovery

User replied `继续` to the prior recovery/renewed-submission question. Fresh
read-only checks found the old target absent and its reservation preserved;
visible scheduler records remained the September 15 jobs. The old local and
remote markers were not deleted, renamed or reused.

One new exact-input attempt uses `h_is_a_int06_gpu1802_neb_temp_r2_20260928` on
the separately configured `sunboquan-cdj1-temp` account. Manifest-only upload
now uses a locally generated tar archive on SSH stdin, not SCP/SFTP framing.
Remote extraction refuses existing target files. Canonical submission still
checks the current gate, full file hashes, POTCAR identity and reservation.
No remote shell startup file, restart file or physical parameter was changed.

All eleven structures, INCAR, KPOINTS, script and POTCAR.spec are byte-identical
to the accepted parent. Regenerating geometry evidence for the new absolute
paths legitimately changes the preflight bundle hash; it is explicitly rebound
by fresh user authorization and gate evidence, not disguised as an identical
full evidence bundle. Existing accepted VTST/movie/path-review bytes are reused.

Actual LSF receipt: `9802439`, queue `Gkn_normal`. Initial scheduler checkpoint
is `PEND`; compact NEB monitor shows zero steps and no energies or forces for
images01-09. Queue acceptance is not VASP startup, convergence or TS acceptance.

Main workspace validation: compilation and targeted Ruff passed,54 relevant
backend/submission/gate tests and88 scheduler-boundary tests passed. Source
publication validation is run independently in the existing isolated worktree.
Next requested checkpoint checks the same job, never submits another job.
