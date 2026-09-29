# Phase 1 offline diagnostic cases: implementation audit

## Scope and baseline

- Implementation base: `sbq123/main` at `9d272be8fa5e12cca7aee09b7d1b8e7c9ecddd27`; release branch: `codex/phase1-diagnostic-cases-20260929`.
- The live workspace was `C:\Users\86177\Desktop\work`, HEAD `376c597ad3e026da9539401748e5fbe5d145b87c`, branch `refactor/v2-architecture-repair`, with extensive pre-existing changes. In particular, its `learning_cli.py`, `LEARNING.md`, and existing learning tests were already modified. Those unrelated edits were not committed here.
- Existing `observe`, SHA-256 helpers, policy routes, atomic JSON writer, and parent learning CLI were reused. The existing learning test baseline passed before implementation (exit 0). No production database, calculation, or scheduler was used.

## Delivered

- `learning_cases.py`: validates explicit small JSON snapshots under a permitted root; binds paths, hashes, pointers, and selected values; separates public cases from reviewed references; creates a new bundle and writes its completion marker last.
- `learning_evaluation.py`: verifies bundle/source identity and scores saved structured answers. Missing, duplicate, unknown, malformed, or mismatched answers remain visible; the scorable denominator is explicit.
- `learning_cli.py`: adds `cases-build` and `cases-evaluate` to the existing CLI without using its database path.
- `learning_evidence.py`: rejects malformed pointer escapes and noncanonical or negative array indices.
- `test_ts_learning_cases.py` and `LEARNING.md`: synthetic behavior tests and the actual CLI contract.

Example workflow: prepare a reviewed manifest and JSON sources inside one allowed directory, run
`python -m scripts.ts_strategy_engine.cli learning cases-build --manifest CASES.json --allowed-root SNAPSHOT_DIR --bundle NEW_DIR`, then save answers with the public bundle hash and run
`python -m scripts.ts_strategy_engine.cli learning cases-evaluate --bundle NEW_DIR --answers ANSWERS.json --report NEW_REPORT.json`.
Only `public.json` is input for an answer generator. This project did not run one.

## Validation and review

On the release worktree after the final code change:

| Check | Result |
|---|---|
| `python -m py_compile` on four changed Python runtime files and the new test | exit 0 |
| `ruff check` on those files | exit 0 |
| `python -m pytest tests/test_ts_learning_cases.py tests/test_ts_strategy_learning.py -q` | exit 0; 49 tests |
| Parent `learning cases-evaluate --help` | exit 0 |
| `git diff --check` | exit 0 |

The live workspace also passed its existing learning and architecture boundary tests before the final isolated release check. The latter result is not presented as testing the final release bytes.

Self-review found that the existing observer accepted `/array/-1`; this was fixed and regression tested. Tests also check stale hashes, missing files, bad pointers/types/paths, reference separation, duplicate/missing/extra answers, unknown answers against confirmed references, embedded instructions as inert data, deterministic public bytes, exclusive output, and an interrupted bundle without a completion marker. They use synthetic JSON and temporary SQLite only.

## Limits and state

- Real reviewed cases: 0. Synthetic test cases do not establish scientific diagnostic accuracy, hallucination reduction, TS success, or saved compute time.
- An approved reference is an evaluation input, not independently proven scientific truth. The manifest author must confirm that each public value and question predates the answer; field filtering cannot prove semantic nonleakage. Public/private file separation is not an operating-system permission boundary.
- The new commands have no call to the registry, network, scheduler, model, or training path. Test sentinels cover selected registry entry points; this is a bounded side-effect check, not a general process sandbox.
- The requested end-of-task `repo-state sync --safe-only` in the live workspace returned exit 1: `repository item changed after classification: sbq_catalyst_agent_workflow.egg-info/PKG-INFO`. No state-sync success is claimed. No current scientific task or calculation was intentionally edited.

## Release file hashes (SHA-256)

| File | SHA-256 |
|---|---|
| `scripts/ts_strategy_engine/learning_cases.py` | `59ca89710d4da731d37b136fb7519fc3ecd218ebc041f5c0654f2e562ef959d8` |
| `scripts/ts_strategy_engine/learning_evaluation.py` | `c826de3e85dee37d904a1201ca707f56c74babbca82c9ae666bee28ba2793e96` |
| `scripts/ts_strategy_engine/learning_evidence.py` | `72f9149833bba64f3beaa46f88b82a38db1f1147b95d920b3371224e5d90ecdc` |
| `scripts/ts_strategy_engine/learning_cli.py` | `b47923d20cff4a09e8967edce82d6f96d8de362eb4fc027297dd77165ebc9d56` |
| `tests/test_ts_learning_cases.py` | `4128afbcae7958ed8b14f4c66039f301c47eb43e123876694575bfe23a732b63` |
| `modules/transition_state_search/LEARNING.md` | `e83ed542b57103f3719bbb69bedc4510b2e0264ee389b1e33b92e9a8b027fe1c` |
