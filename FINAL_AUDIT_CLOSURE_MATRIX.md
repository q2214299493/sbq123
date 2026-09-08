# Final Audit Closure Matrix

Date: 2026-07-27

## Conclusion

`OPEN_P0 = 0`.

The matrix below reconciles the initial audit, condition closure, Phases 2A,
2B, 3A, and 3B against the current files and the Phase 4 regression results.
`ACCEPTED_RISK` means the behavior is explicitly contained and is not an
unrestricted production authority.

| # | Original problem | Current evidence | Status | Phase 4 action |
|---|---|---|---|---|
| 1 | Duplicate code | confirmed execution-decision, path-quality orchestration, endpoint evidence, and AdsMind overlaps were consolidated; compatibility facades remain intentional | CLOSED | None |
| 2 | Unused/dead code | Ruff and AST scan found no unused import/variable, duplicate top-level definition, unreachable block, stale TODO, or provably removable public path | NOT_APPLICABLE | Nothing safely removable |
| 3 | Mixed module responsibilities | gate/decision, evaluator/service/CLI, endpoint evidence/validator/manager/DB boundaries are explicit and tested | CLOSED | None |
| 4 | Circular dependencies | 0 cycles across 132 internal edges | CLOSED | None |
| 5 | Multiple configuration sources | scientific thresholds remain in their owning YAML/config sources; no Phase 4 duplicate default was found | CLOSED | None |
| 6 | Inconsistent state representation | scheduler, convergence, geometry, science, module, and action states intentionally remain separate; local string enums still exist | ACCEPTED_RISK | Do not collapse distinct domains |
| 7 | Fixed temporary files | atomic writers use unique same-directory `mkstemp` names | CLOSED | None |
| 8 | Unsafe concurrent writes | atomic complete-file replacement is tested; multiwriter merge is not provided | PARTIALLY_CLOSED | Last-writer-wins remains documented |
| 9 | Subprocess without timeout | all five production Python process calls have finite timeout | CLOSED | None |
| 10 | Duplicate external submission | attempt records, scheduler reconciliation, current-gate validation, and alpha-Fe markers are tested | CLOSED | None |
| 11 | Unknown status treated as success | timeout, command failure, connection failure, and unknown scheduler state are non-success | CLOSED | None |
| 12 | CLI mixed with business/scientific logic | major CLIs are adapters; path-quality CLI is thin; unified CLI delegates | CLOSED | None |
| 13 | Multiple scientific evaluators | one path-quality evaluator and one endpoint validator were confirmed | CLOSED | None |
| 14 | Database adapter mixed with science | endpoint DB checks record shape/status vocabulary only and does not recompute science | CLOSED | None |
| 15 | Silent exceptions | no bare or silently continued broad exception; cleanup/transaction handlers re-raise | CLOSED | None |
| 16 | Insufficient error/log context | timeout/command/submission paths preserve command, stderr/state evidence; some one-shot builders still use direct exceptions | PARTIALLY_CLOSED | Improve only when a concrete failure lacks context |
| 17 | Stale documentation | README, scripts README, TS README, and additive final architecture now describe verified boundaries | CLOSED | None |
| 18 | Missing regression tests | suite grew from 197 to 274; focused gate, path-quality, endpoint, migration-safety, and artifact-layout contracts pass | CLOSED | None |
| 19 | Calculation/source changes mixed | additive manifests exclude calculations/runtime/output/database; pre/post status hash matches | CLOSED | None |
| 20 | Migration safety | exact existing-schema validation, explicit DDL transactions, post-failure rollback, repeat validation, and empty-only rollback were exercised on temporary SQLite | CLOSED | Real execution still requires separate authorization |

Additional historical structural findings are also closed: the original
`execution_gate.py` 370-line contract failure is now 310 lines; legacy gate
imports/signatures remain tested; the Phase 3B evidence extraction reduced a
successful initial ASE structure read from two to one without changing the
validator result.

## P0 disposition

No open item can currently bypass the execution gate, silently run an endpoint
migration, overwrite the real registry, or turn unknown scheduler state into a
successful submission. Extreme contact, real surface-normal desorption, and
empty reaction identity now have explicit endpoint behavior and regression
tests.

## Unclosed-item conditions

| Item | Files | Risk and current impact | Why not changed | Start condition |
|---|---|---|---|---|
| Domain-specific state strings | gate, scheduler, validator, manager, DB modules | confusing strings could be compared across layers; current code/tests keep layers separate | one universal enum would erase distinct semantics and break APIs | only after a cross-domain state protocol is approved |
| Last-writer-wins JSON | `scripts/artifact_io.py` | concurrent complete writes do not corrupt JSON, but one writer can supersede another; current controllers assume one owner | merge/locking semantics require a domain decision | when parallel writers to one target are introduced |
| Residual error-context variation | one-shot VASP/campaign builders | a failed fresh-directory write may have less structured context; no silent success observed | broad error-framework work is outside low-risk closeout | reproduce a concrete diagnostic failure first |
