# Phase 3.2.2 software verification

| Environment | Result | Log |
|---|---|---|
| Development directory, phase regression suites | 702 passed, 1 live baseline excluded, 59.13 s | [Development](regression/development.txt.gz) |
| Independent release worktree, same suites | 702 passed, 1 live baseline excluded, 57.80 s | [Release](regression/release.txt.gz) |
| Clean checkout with phase implementation, full suite | 2263 passed, 5 known historical failures, 1 excluded, 15 warnings, 951.11 s | [Full suite](regression/full.txt.gz) |

The 43 new deterministic cases cover connected reaction energies at fixed absolute TS, species identity, missing data, feed constraints, registered gases, validity ranges, nonpositive TOF, coarse and fine estimates, campaign approval, first failure and budget. Previous TS studies reproduced all 12 signed datasets, and 140 reference files from earlier phases matched the published baseline. The five full-suite failing node IDs exactly match the previous checkpoint. [Historical failures](../phase3_2_0_1/historical_regression_debt.md)

Both trees passed scoped compilation, imports, Ruff and schema checks. Additional focused checks verified that all four fixed-total preview configurations preserve the canonical reaction records byte for byte, an out-of-range pressure increase fails qualification and a standalone pair cannot launch a sensitivity run without the study deadline. No native solver was invoked for these tests.

The uncompressed full-suite log SHA-256 is `dcdce3296ef5b762a9b2a6d901848a048248fd098a073ac72e241d22db083d13`.
