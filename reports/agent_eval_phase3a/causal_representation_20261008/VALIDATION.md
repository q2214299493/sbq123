# Phase 3A compact validation record

Date: 2026-10-08 (Asia/Shanghai). These are the actual local checks from the completed implementation. This publication does not invent or rerun model results.

| Command | Actual result | Exit code |
|---|---|---|
| `python -B -m py_compile scripts/ts_strategy_engine/learning_cases.py scripts/ts_strategy_engine/learning_evaluation.py tests/test_ts_learning_cases.py` | passed | 0 |
| `python -B -c 'from scripts.ts_strategy_engine import learning_cases, learning_evaluation; assert learning_cases.SCHEMA_VERSION == 2'` (the recorded command also printed a PASS marker) | imports passed | 0 |
| `python -B -m pytest tests/test_ts_learning_cases.py -q -o addopts=` | 82 passed | 0 |
| `python -B -m pytest tests/test_ts_strategy_learning.py tests/test_code_structure.py tests/test_b5_architecture_boundaries.py -q` | 68 passed | 0 |
| `python -B -m ruff check scripts/ts_strategy_engine/learning_cases.py scripts/ts_strategy_engine/learning_evaluation.py tests/test_ts_learning_cases.py` | All checks passed | 0 |
| `git diff --check` | no whitespace errors; Git noted CRLF-to-LF normalization for the test file | 0 |
| `python -B -m scripts.state_manager.cli --root <publication-worktree> audit --phase start --format json` | 1 error / 17 warnings / 18 review-required findings; existing managed module-map projection drift | 1 |

A total of 150 local tests passed. Original local stdout/stderr, command receipts and snapshots remain in the implementation delivery directory; they are not copied into this source release.

## Tested bytes and scope

The two Python source files, the test file and module documentation were compared byte-for-byte with the tested delivery snapshot before publication. Only the Phase 3A audit document was shortened for public release, and this validation summary was added. No test result was changed.

| File | SHA-256 of tested local bytes |
|---|---|
| `scripts/ts_strategy_engine/learning_cases.py` | `aae910006f64c26d04185b34327b43064ecd0598b5a48f606c8070d81e381f40` |
| `scripts/ts_strategy_engine/learning_evaluation.py` | `c18c33efb90ddb31fe231f1ff7148bd6e0183fe600ede00f5bcd83c5d05c811e` |
| `tests/test_ts_learning_cases.py` | `a05c1ab1b017cef44ce48252e6d8ac86bcd503c9dbfedcb1e602e0c7997184ba` |
| `modules/transition_state_search/LEARNING.md` | `ec0c0c6f1c83d6d1c11f4e18e7ff9b4e3d35a1e39af4de1c086ba8dd8eb4a235` |

Hashes above identify tested local bytes. Git may normalize CRLF to LF in repository blobs according to the existing attributes; staged content is checked against that existing normalization.

The final implementation audit verified 290 protected historical/software files unchanged. Production outcome/event logic, learning policy, execution gate and scientific acceptance standards were not edited. No historical benchmark, reference, model answer or score report is included in this commit.

## Unverified and limitations

- Full repository suite, model diagnostic ability, production deployment and reference-access isolation were not tested.
- Claim text is compared exactly; paraphrase equivalence and scientific causal truth are not validated by code.
- Historical bundles require newly reviewed explicit claims and new output paths. Production outcome/event schema remains unchanged.
- Existing startup projection drift remains unresolved; no state sync or projection repair was performed.
- No model run, A/B rerun, HPC/VASP/Sella computation, training, production database operation, merge or deployment was performed.

Commit/push authorization is limited to the independent source-review branch. CI success is not merge or production approval.
