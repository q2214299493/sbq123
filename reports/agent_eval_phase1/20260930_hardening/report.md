# Phase 1.1 diagnostic evaluation hardening

## Object and scope

- Base: `sbq123/codex/phase1-diagnostic-cases-20260929` at `d3a0d7802a42987d517743063bf6c9295d2e13b4`.
- Worktree: `C:\Users\86177\.codex\worktrees\phase1-diagnostic-cases\work`, initially clean. The separate live workspace `C:\Users\86177\Desktop\work` remained on `refactor/v2-architecture-repair` with pre-existing changes; none were copied into this repair.
- The attached review and probe results were treated as claims to check, not as execution instructions or fresh local test results. Existing related tests passed on the base before edits (49 tests, exit 0; Python 3.13.9 on Windows).

## Findings, fixes, and checks

| Finding | Confirmed cause and fix | Verification |
|---|---|---|
| F1: resealed private reference could disagree with its reviewed source | Loading checked source bytes but did not compare `reference.expected` to `source.value`. The loader now reuses the builder's source and reference checks, including route, provenance, unique IDs, separate sources, and the persisted allowed root. Private bundle format 2 is required; older bundles fail with a rebuild instruction. | A new red test reproduced the mismatched reference on the base. Post-fix tests reseal invalid references and markers, including approval, provenance, duplicate ID, same source, and an existing out-of-root JSON file. All are rejected. |
| F2: answer structure did not control integrity or CLI exit | Scoring checked the reference before the answer and the CLI always exited 0 after writing a report. The answer is now checked first, structural errors remain visible in each row and in the fixed denominator, `integrity_ok` becomes false, and the CLI exits 2 after saving its failure report. A valid wrong diagnosis remains a scored mismatch with exit 0. `comparison_ready` is false for empty, incomplete, or unscorable sets. | A new red test reproduced stale input identity with `integrity_ok=true` and exit 0 on the base. Post-fix direct and parent-CLI tests cover stale identity, extra/duplicate/missing IDs, invalid/repeated citations, illegal fields, unscorable references, and a wrong top-level answer-set version. |
| F3: report could not distinguish references or evaluator versions | The report now includes private package, policy, builder, evaluator, composite evaluation-code, and answer-file hashes. | Two valid bundles with identical public cases and answer bytes but different reviewed references produce different private identities and different scores. Tests recompute policy and code hashes from the actual files and check repeat stability. The baseline behavior was identified from the attached isolated probe and source inspection; it was not independently rerun before editing. |
| F4: global `--output` could overwrite a just-built case file | Both new commands reject global `--output` before dispatch; old learning commands retain their existing behavior. | Direct and parent-CLI tests confirm exit 2 and no new bundle or report for conflicting and ordinary output targets. The baseline behavior was identified from the attached isolated probe and source inspection; it was not independently rerun before editing. |

## Final validation

| Command | Result |
|---|---|
| `python -m py_compile` on the three changed runtime files and new test file | exit 0 |
| `ruff check` on those files | exit 0 |
| `python -m pytest tests/test_ts_learning_cases.py tests/test_ts_strategy_learning.py tests/test_b5_architecture_boundaries.py -q` | exit 0; 97 tests (40 + 35 + 22) |
| `git diff --check` | exit 0 |

Changed files are `learning_cases.py`, `learning_evaluation.py`, `learning_cli.py`, `test_ts_learning_cases.py`, and `LEARNING.md`. No database schema, execution gate, scientific state, or calculation file was edited.

## Final file identities (SHA-256)

| File | SHA-256 |
|---|---|
| `scripts/ts_strategy_engine/learning_cases.py` | `4a5d6688ce12cddf42d2ee5ccfa5963a5fb5081c786dfe2296cf51b81f1a781d` |
| `scripts/ts_strategy_engine/learning_evaluation.py` | `20aae42d5e15bb74e01581f3b37842d2bf16f3f6444079adf094dbbfc3d291c3` |
| `scripts/ts_strategy_engine/learning_cli.py` | `3bab9b4ba1f5b551c6b0caf4b983310fa36465d1f4c7b2be3276eba24ca8339f` |
| `tests/test_ts_learning_cases.py` | `e67768322ed829e77ab9374f0c7574155452c55d1e35d28b567b093ed67afe91` |
| `modules/transition_state_search/LEARNING.md` | `55d96272412252be4bbef157cc01399a044c2cd9e04429d7996c1591f10fbc1d` |

## Limits

- Real reviewed cases: 0. The tests use synthetic snapshots. No real diagnostic accuracy, hallucination reduction, TS success, or compute-time benefit was measured.
- Bundle hashes detect inconsistent files but are not signatures. A party able to replace the private bundle, sources, and marker can create a different review version. Fair comparisons require the report identities and an independently governed reference source.
- The persisted allowed root and current source paths are checked on load. Cross-machine source portability, Windows link-escape behavior, and full repository tests were not verified here.
- `repo-state sync --safe-only` was attempted because the local project instructions require it; it exited 1 with `repository item changed after classification: sbq_catalyst_agent_workflow.egg-info/PKG-INFO`. No sync success is claimed. The release worktree's tracked state files showed no resulting change.
