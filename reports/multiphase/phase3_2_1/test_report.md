# Phase 3.2.1 validation record

| Environment and scope | Measured result | Full log |
|---|---|---|
| Development, phase regressions | 659 passed, 1 deselected, 56.10 s | [Development](regression/development.txt.gz) |
| Independent release worktree, same scope | 659 passed, 1 deselected, 54.89 s | [Release](regression/release.txt.gz) |
| Clean release checkout, full suite | 2220 passed, 5 historical failures, 1 deselected, 15 warnings, 964.88 s | [Full](regression/full.txt.gz) |

The phase suite includes the 633 earlier regressions and 26 new batch cases. The opt-in live baseline rerun was deselected to preserve the accepted unperturbed baseline. After exposing the read-only scan command, the three DRC test modules passed all 94 cases in both trees, the CLI reproduced the Fe(110) exclusion file and Ruff passed. The five failed full-suite node IDs exactly match the preceding checkpoint. The uncompressed full log SHA-256 is `66855df91d0e4a3bbd5cdf3b1a106e4cdb2e0ea2e1cf4acb0ed1ad76117bf970`. [Historical regression debt, causes and ownership](../phase3_2_0_1/historical_regression_debt.md)

The new tests cover network scanning, TS/parameter evidence, unknown reversibility, different pressure units, hash and condition mismatches, exact plan membership, per-run and global capacity, individual approvals, expiry and partial recovery, reuse, fail-fast, duplicate prevention, stable-only ranking, Fe exclusion and offline reproduction of plan members. During development a test passed a string to a Path-based JSON reader; correcting the test fixture resolved that failure.

Both working trees passed compilation, scoped Ruff, the result schema and four portable native output replays. Each replay rebuilt the signed dataset and native input and reproduced the original normalized result SHA-256. A read-only check against the four raw native receipts verified source approvals and output hashes, non-overlapping execution intervals and zero duplicate launches on completed-batch resume. The four authorized native executions and their scientific evidence are recorded separately. [Completion and numerical results](completion.md)
