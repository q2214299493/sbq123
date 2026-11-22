# Stage R.2.2 completion — strict read-only State Handoff sync

R1-003 is repaired on the R.2.2 integration branch. `repo-state sync --safe-only` builds and reports hash-bound plans in memory. It exits the per-proposal loop iteration before the first cache write, receipt lookup, review append or application. Applying the plan is a separate operation.

## Baseline reconciliation

| Reference | Verified commit | Role |
| --- | --- | --- |
| Original production baseline | `335008915ebcb227cc5012054df105a2e0ac4404` | Merge base of current production and R.2.1 |
| `codex/multiphase-phase0-integration` | `dd3a5cbbd180c97fe09a0554a6ef2a845ef95f73` | Production advanced once, adding the failed native-initialization archive, its test and historical event |
| `codex/stage-r2-1-network-binding` | `5fb520a6eb5d4161949edef78bd3b86ce0585c05` | Independent, one repair commit after the common base |
| `codex/stage-r1-architecture-audit` | `efe4cf4e2a0e0f6f1c94af66f8729c078906db25` | Audit evidence, direct child of current production |
| Normal merge | `b8f2640a42fb3fd59ef118f4a7e0d057450b8753` | Production first parent, R.2.1 second parent; automatic content merge without conflicts |
| Tested implementation | `977968c75a310eb4b3881184b007ef1c48b580b4` | R.2.2 implementation, tests and command documentation |

The development worktree was created at the production head. A separate publication worktree checked out the tested implementation. The pre-existing desktop worktree at `233d5a6c` had 242 tracked modifications, three tracked deletions and 1,100 untracked porcelain entries. No task edits or staging occurred there. The original production, R.2.1 and audit branch histories are preserved.

The 31 network-binding tests passed immediately after merging, before editing State Manager. The four R.2.1 production files and its regression file have no diff from `5fb520a6`. Rebuilding the R.2.1 history proposal reproduced `proposal-dd74dd87c1c2598d56ff3d94` with review still required.

## Mutation boundary and compatibility

The old loop saved each nonempty proposal before checking review status. Already reviewed events could reach apply directly. A pending scientific registration could enter the combined Registry/Excel predicate, record a review and apply. An ordinary review-free proposal also reached apply. The apply path reserves a lock and persists an attempt before it revalidates the source, so a failed apply could leave ledger changes even if the target stayed intact.

The repaired loop preserves candidate selection, application-lock detection, current-task ownership, one-time cleanup deferral, and authoritative proposal construction. A flagged invocation verifies file evidence for plans with actions and reports an optional `preview` array. `pending_review` uses the exact current proposal ID; a prior decision for another plan does not approve a rebuilt plan. The command returns 1 for a pending review and 0 when the preview completes without pending review. Existing guard failures still interrupt preview. It never saves a previewed plan. To use an uncached plan, explicitly propose its source event, then confirm the returned ID before review or apply.

Unflagged `sync` retains its existing cache, approval-reuse and apply paths. The reuse predicate requires both an accepted, eligible Registry result and a matching trusted Excel promotion with matching workbook and receipt hashes. Its SQLite connection is read-only. Neither piece of evidence alone authorizes reuse. Explicit `review` and `apply`, the narrower flag on **explicit apply**, proposal IDs, receipt policy and application-ledger format retain their existing implementations.

## Before/after mutation matrix

The tests use real CLI dispatch against temporary roots. An independent inventory hashes every regular file with SHA-256 and records directory membership before and after each of two invocations. This covers source evidence, immutable events and approvals, cached plans, application attempts and receipts, manifest, managed targets and the temporary Registry/Excel inputs. An additional guard fails if flagged sync enters the receipt predicate. Explicit positive controls use the real review and apply machinery in the same temporary roots.

| Initial state | Old flagged path | Repaired flagged result |
| --- | --- | --- |
| Managed, review-free change; no cache | Saved proposal and applied target/manifest | Preview only, exit 0; cache remains absent |
| Unmanaged target requiring review; no cache | Saved pending proposal | Same pending ID on repeat, exit 1; cache remains absent |
| Exact plan already approved | Entered apply | Preview shows same ID; review and target hashes stay fixed |
| Rejected proposal | Excluded from selection | Excluded, exit 0 |
| Registry evidence only | Cached pending plan and consulted reuse | Pending, exit 1; skips receipt lookup |
| Excel promotion only | Cached pending plan and consulted reuse | Pending, exit 1; skips receipt lookup |
| Eligible Registry and Excel evidence together | Recorded automatic approval and applied | Pending, exit 1; approval, application and SQLite contents stay fixed |
| Stale bound source | Entered apply, leaving cache/attempt artifacts on failure | Evidence error, exit 2; no writes |
| Previously applied projection edited externally | Rebuilt and applied drifted target | Preview only; preserves edited bytes and prior manifest |
| Later historical compaction blocked after an earlier eligible task | Earlier task could apply before planning failed | Error, exit 2; both source and targets remain unchanged |
| One-time cleanup, existing application lock or repeated invocation | Cleanup deferred; lock blocked; repeat could see a changed first-run state | Cleanup remains deferred; lock remains in place; repeated previews have equal output and file hashes |

On the merged code before the repair, eight of nine initial independent mutation cases failed the tree comparison. Only rejection was already mutation-free. All nine passed after the repair, plus the mixed-candidate failure test. A simulated human decision exercised explicit CLI `review --decision approve`, then preview, then explicit `apply`; the latter updated the target and produced an `APPLIED` receipt. Deliberately invoking unflagged sync in the joined-receipt fixture produced the expected review and applied the eligible target. Both single-sided controls remained pending under unflagged sync.

## Regression and remaining repository findings

The pre-change focused run passed 206 tests. The repaired development and publication worktrees each passed **694 focused offline tests** (62.40 s and 57.72 s respectively), including all 509 tests in the R.2.1 contract/adapter selection. The other 185 cover State Manager, State Handoff and Registry. Both worktrees passed `py_compile` and Ruff on the five changed Python files. The full repository suite and Linux execution were outside this verification.

To reproduce, run `python -m pytest -o addopts= -q` with these test modules under `tests/` (each name below takes the `test_` prefix and `.py` suffix).

- State/Registry: `state_manager`, `b4_state_governance`, `state_log_projection`, `state_sync_repository_items`, `state_sync_task_ownership`, `state_sync_safe_only`, `registry_schema`, `registry_write`, `registry_excel_promotion`, `b4_registry_governance`.
- R.2.1: `rate_network_binding`, `rate_output_v2`, `rate_dimensions`, `native_rate_adapters`, `b1_contract_acceptance`, `b1_native_acceptance`, `kinetic_parameters`, `reaction_network`, `stoichiometric_sources`, `multiphase_contracts`, `interphase_transfer`, `cross_phase_elementary`.

A read-only sync against the actual development worktree reached the pre-existing `state-history-compacted-7ca5604cfc573d419007f891` source guard and exited 2. The event expects source SHA-256 `f6eee7315643818ddd25c238bc18db07598db7ef48227fda1fdb2f603f8b71ed`; the current file hashes to `17e5c1dd75605115aece7583cd3bce05425e04145f328f65442d092c117f2b7a`. Across that invocation, all 346 checked event, cache and projection files matched their original hashes. End audit also reported the existing `managed_projection_drift` for the `transition_state_search` module row. The repair preserves both findings. No scientific engine or production SQLite writer ran.

## Exact R.2.2 file list relative to the integration merge

| File | Change |
| --- | --- |
| `scripts/state_manager/cli.py` | Read-only preview guard and CLI help |
| `tests/test_state_sync_safe_only.py` | Independent mutation matrix and positive controls |
| `tests/test_state_manager.py` | Shared temporary receipt fixture and explicit mutating sync coverage |
| `tests/test_state_sync_repository_items.py` | Both plain and preview behavior with mixed cleanup/projection candidates |
| `tests/test_state_sync_task_ownership.py` | Exercise task ownership during mutating sync |
| `modules/state_handoff/README.md` | Command, caching, receipt and checkpoint semantics |
| `AGENTS.md` | Correct the end-of-task sync instruction |
| `reports/architecture_repair/stage_r2_2/completion.md` | Reconciliation, mutation matrix, regression and limitations |
| `modules/state_handoff/events/history-stage-r2-2-safe-only-20261122.json` | New pending history proposal source bound to this report |

State Handoff review of this completion record is a separate decision. Creating it uses explicit `propose`; the reviewed history projection and projection manifest await that decision.
