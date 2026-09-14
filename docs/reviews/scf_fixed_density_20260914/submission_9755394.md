# Fixed-density orbital diagnostic9755394 submitted

2026-09-14. User explicitly authorized this one diagnostic. Initial live LSF
status PEND, queueGkn_normal,80ranks, excludesgknew0440.

Remote:
~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_fixed_density_20260914

Reviewed candidate/source hashes verified. Exact differences from9754808:
ICHARG12, ISTART0, LMAXMIX4. Original geometry and other inputs unchanged.
No failed WAVECAR/CHGCAR copied. Canonical diagnostic_static preflight PASS;
current hash-bound gate allowed SUBMIT_DIAGNOSTIC_VASP. No duplicate attempt.
Orchestrator Python compile and targeted Ruff passed. Custodian validation of
the unchanged candidate was completed during review; runtime behavior untested.

Submission bundle SHA256:
7de31afb503a37158e7709b82dbfcd24c54c5f188981a2105b09db816656c6df
Gate SHA256:
0c74db9e5609f41b8d30bf1f1d18387fa5dfe5ebf9a6674004b51f31010dc33d
Receipt:
calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_mid_fixed_density_20260914/submission_record.json

This is non-selfconsistent diagnosis, not SCF recovery or a TS. Output is
ineligible for adsorption/barrier energies, training labels or automatic Dimer
restart. Check actual ICHARG/ISTART/LMAXMIX and finite orbital convergence;
DONE/EDIFF text alone is insufficient. No further job/retry/stop authorized.

Current-task projection updated by review-free proposal-584434a510de8520dd95939b.
Global safe sync remains blocked by existing PKG-INFO classification drift.
