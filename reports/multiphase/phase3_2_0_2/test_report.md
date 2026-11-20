# Validation record

| Check | Location | Result |
|---|---|---|
| Phase regressions, previous 609 and 24 new cases | Development | 633 passed, 1 live baseline deselected in 51.62 s |
| Same test list | Independent release worktree | 633 passed, 1 live baseline deselected in 50.81 s |
| Complete repository suite with the same live baseline excluded | Fresh checkout of the release baseline with this checkpoint applied | 5 failed, 2194 passed, 1 deselected, 15 warnings in 930.65s (0:15:30) |
| Historical failure reproduction | Current development tree | 5 known failures reproduced in 7.33 s |

[Development test log](regression/dev.txt.gz) · [Release test log](regression/release.txt.gz) · [Full test log](regression/full.txt.gz) · [Development debt reproduction](regression/dev-debt.txt.gz)

The opt-in `test_live_closed_cycle` would run the unperturbed CATKINAS baseline again. The four newly authorized native runs are accounted separately in the [completion report](completion.md). Routine tests used deterministic fixtures, recorded native output and a mocked executor.

## Numerical, evidence and code checks

- Both working trees passed scoped Python compilation, import and Ruff checks. Both paired results validate against the paired DRC schema and the comparison validates against the cross-reaction schema.
- Reconstructed all four datasets, configurations and native input hashes from the accepted parent and the signed displacement. Replayed each native MAT and log excerpt independently and reproduced each accepted normalized result SHA-256 byte for byte.
- Verified the 47 archived Phase 3.0, Phase 3.2.0 and Phase 3.2.0.1 reference files against the release baseline. Verified all four execution decisions and source replies, plan digests and original output files against the raw native receipts.
- During test development the four new MAT replay assertions initially looked up the pressure as `NO`. The recorded native symbol is `P_NO`. Correcting the test to use the archived native pressure and coverage symbols made all four pass on the same MAT files. A scoped Ruff complexity finding was resolved by separating the four-plan preflight from execution.

All five failing test IDs match the Phase 3.2.0.1 full-suite log and the current development reproduction. No additional failure appeared. The owner, failure reason and follow-up for each inherited test are in the [existing historical regression debt record](../phase3_2_0_1/historical_regression_debt.md). The uncompressed full log has SHA-256 `64f89d1c1e2e7131d36caff15b6e024e99de164ccb03225ce70ab3ae49bfd2c1`.
