# Magnetic-seed SCF9754808 submitted

2026-09-13: user explicitly authorized one baseline-moment recovery diagnostic.
Submitted through the current hash-bound SUBMIT_DIAGNOSTIC_VASP gate; initial
live scheduler status PEND, Gkn_normal,80ranks, excludinggknew0440.

Remote directory:
~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_scf_magnetic_seed_20260913

Only MAGMOM differs from9754301:50 projected moments from9752745, in original
atom order. Comparison/source hashes verified, source9754301 DONE verified,
geometry evidence hash unchanged. Fresh directory; no WAVECAR/CHGCAR copied.
Diagnostic preflight PASS; candidate had already passed custodian validation,
and unchanged candidate hash was verified this turn. Python compile and
targeted Ruff passed for the one-off submission orchestrator.

Bundle SHA256: d022db561df455666c062d75a0bb7be4e16f98cb1a0fd67addc529af07ed58cf
Gate SHA256: eb8acb9ba4ef26bca981cffc42131e649bd63bc44b2c33f008943300ae1eb9c8
Receipt: calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_mid_scf_magnetic_seed_20260913/submission_record.json

This is fixed-geometry SCF, not Dimer or an accepted TS. Recovery of the lower
energy magnetic state, output integrity and saved-state validity are untested.
Next: inspect SCF progress; if converged, compare energy/local moments/forces
with9752745 before separately proposing restart verification. No retry or next
scientific job is authorized.

Current task updated through review-free proposal-82194ee92412edba73d2a933.
Global safe sync remains blocked by pre-existing PKG-INFO classification drift.
