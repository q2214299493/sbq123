# Phase 0 · development baseline

Snapshot taken on 2026-11-19 before implementation. The development checkout is `C:/Users/86177/Desktop/work`. The independent release repository is `q2214299493/sbq123`.

| Baseline | Evidence |
|---|---|
| Development | `refactor/v2-architecture-repair` at `233d5a6c589560094a0e942b6d48708b1fd5a847`, 62 commits ahead of its origin tracking branch. Working tree at intake had 238 modified entries and 948 untracked entries in porcelain normal mode (directories may count as one). |
| Release | Fetched `sbq123/main` at `b1649fcffb0930c1008acb6791de9b9ce300b35c`. No merge base. Left/right commit counts 128/61. Committed tree diff spans 1,227 paths. |
| Relevant working files | Byte comparison after newline normalization found identical release resource lists, resource resolver, registry schema Python, postprocessing config and kinetic-data module README. The method protocol and current task differ. Local packaging files include untracked work. |
| Release procedure | Develop and test against the working files. Transfer only new contract artifacts and the two resource-list insertions to a separate worktree based on the verified release commit. Publish the task branch there. |
| State audit | `repo-state audit --phase start` returned 0 errors, 71 warnings, 71 review findings. These include existing worktrees and an oversized state document. This is administrative evidence. |
| Active task | `repo-state task status` points to `task-fe110-adsorption-control-paired-vasp3-submitted-20261020`. Its one step is an on-demand six-job checkpoint. The November kinetic-intake section of `docs/02_CURRENT_STATE.md` separately records electronic evidence awaiting thermochemical review. Neither checkpoint was executed here. |
| Baseline regression | `C:/Anaconda/python.exe -m pytest -q tests/test_registry_schema.py tests/test_artifact_io.py` passed 23 tests on Python 3.13.9 with pytest 8.4.2. The tests use temporary artifacts. |
| Production metadata | Read `data/project_registry.sqlite3` with SQLite URI `mode=ro` and `PRAGMA query_only=ON`. Schema metadata is **9**. SQLite catalog counts are 20 tables (including sqlite_sequence), 34 indexes, 49 triggers and one view. File SHA-256 at inspection was `23d4accaf16f2d992d3df7a6545320b8fe0c550b7f4e98ae26f61bdab84e724e`. |

## Ownership and migration risk

`scripts/registry_schema.py` declares version 9 and explicit migrations. `modules/calculation_registry/schema.sql` and `scripts/registry_write.py` govern persistence. Existing records include calculations, files, results, TS validations, barriers, compatibility revisions, reviews and immutable application receipts. The production schema and code take precedence over the historical v8 wording in the module map. In particular, adding a phase column with a Fe default would assign unverified context to historical rows. A future migration would need reviewed identity mappings, foreign keys, trigger preservation, a disposable-copy migration/rollback test and explicit authority. Phase 1 uses separate versioned files.

The kinetic-data module owns the exchange contract. Thermochemistry owns corrections, reaction network owns pathways, baseline/coverage MKM own mean-field simulations, surface KMC owns spatial simulations and reactor simulation owns reactor balances. Registry and State Handoff retain separate authority. The Fe(110) protocol binds method, energy convention, cell, occupancy and convergence. The contract carries external reference IDs without redefining those parameters.

## Deliverables and limits

This phase created this baseline, [the twelve-component reuse matrix](legacy_reuse_matrix.md), [the installed-engine assessment](external_engine_compatibility.md) and [the SPC boundary assessment](spc_integration_assessment.md). The scientific outcome is the ability to identify which evidence an adapter would require. No new scientific result or runtime benchmark was produced. The scoped baseline used the two suites above. The archived fake-process timeout test also passed. A second SHA-256 check after development tests matched the production database digest above. Runtime capability and remaining evidence gaps are tabulated in the engine assessment.

Next executable development step at this baseline: validate Phase 1 contracts against deterministic, physically balanced synthetic fixtures.
