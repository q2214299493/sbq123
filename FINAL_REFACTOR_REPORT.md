# Final Refactor Report

Date: 2026-07-27

## Outcome

The multi-phase refactor and the subsequently authorized endpoint correction
are complete. Phase 4 itself was documentation-only. The later correction is
limited to TS endpoint contact/desorption/identity handling, guarded optional
migration code, focused tests, and refreshed release evidence.

## Delivered architecture changes

1. External command boundaries use finite timeouts and preserve command,
   connection, and timeout distinctions.
2. Submission paths record recoverable attempts, reconcile scheduler evidence,
   and reject ambiguous success or duplicate submission.
3. JSON state/report writes use unique same-directory atomic replacement.
4. `execution_gate.py` remains the sole action authority while
   `execution_decision.py` holds pure decision construction with old imports.
5. NEB path quality has one evaluator and one shared application service.
6. TS endpoint validation has one read-only evidence collector and one
   scientific validator; generator, manager, and database responsibilities
   remain separate.
7. Endpoint extreme contacts now reject, actual vertical desorption requires
   review, and empty reaction IDs are rejected at two boundaries.
8. Endpoint migration application validates exact structure, is transactional,
   and cannot destructively roll back non-empty data.
9. Provenance remains additive through source, review, and release baselines.

## Phase history

| Stage | Original problem | Delivered result |
|---|---|---|
| Initial audit / Phase 1 | oversized gate, indefinite commands, fixed temp JSON, ambiguous submission state | pure decision split, bounded commands, atomic writer, idempotent recovery |
| Condition closure | duplicate retry and alpha-Fe submission remained possible | scheduler reconciliation and per-job protection |
| Phase 2A / 2A.1 | source provenance and endpoint-migration status were ambiguous | formal source inventory and additive Review Baseline v2 |
| Phase 2B | path-quality orchestration was duplicated | shared service; evaluator stayed unique; independent acceptance PASS |
| Phase 3A | endpoint API/science/DB boundaries lacked frozen evidence | contract, behavior baseline, duplication audit, minimum plan |
| Phase 3B | endpoint evidence was read/recomputed twice | read-only evidence collector and single initial read; independent acceptance PASS |
| Phase 4 | documentation drift and no release boundary | final audits, 270-test acceptance, additive release manifests |
| Endpoint issue closure | frozen contact/desorption/ID gaps and unsafe migration | bounded scientific correction, exact-shape transactional migration guards, 274-test acceptance |

## Final correction scope

Modified production/configuration:

- `modules/ts_endpoint_evidence.py`
- `modules/ts_endpoint_generator.py`
- `modules/ts_endpoint_validator.py`
- `modules/ts_endpoint_database.py`
- `configs/structure_purpose_routing.yaml`
- the two endpoint review-only SQL files

Tests:

- `tests/test_ts_endpoint_contracts.py`
- `tests/test_repository_contracts.py`

Reports and final release manifests were refreshed. No real database,
calculation, output, scheduler, execution-gate, NEB path-quality, SSH, or LSF
state was modified.

## Compatibility

- Public Python import paths and method signatures: preserved.
- Public validation-result and database-record field sets: preserved.
- Existing status names and priority: preserved.
- Endpoint threshold version: intentionally changed from v1 to v2.
- New reasons: `UNPHYSICAL_ATOM_CONTACT` and
  `ADSORBATE_DESORPTION_WARNING`.
- Core registry schema version: remains 5.
- Endpoint extension version: remains independently versioned at 1.

## Validation

- Ruff: passed.
- Focused endpoint: 45 passed.
- Full repository: 274 passed.
- Skip/xfail: 0.
- `git diff --check`: passed.
- Real registry SHA-256: unchanged.

The suite increased from the original 197 collected tests (196 passed, one
structural-contract failure) to 274/274 passing tests.

## Remaining limitations

- Direct migration SQL and real-registry execution without explicit
  path-specific authorization remain prohibited.
- Non-empty endpoint rollback is intentionally unsupported.
- Some scientific functions remain long; only the validator status-priority
  block was mechanically extracted because broader splitting had insufficient
  benefit for its regression risk.
- Atomic file concurrency is complete-file last-writer-wins, not record merge.
