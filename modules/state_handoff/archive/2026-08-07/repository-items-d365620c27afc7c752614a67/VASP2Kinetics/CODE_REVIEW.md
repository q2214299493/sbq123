# Code Review

Review scope: `main.py`, `src/`, configuration, tests, examples, and release
documentation. Scientific algorithms were not extended or altered.

## Open issues

| Severity | Problem | Location | Recommended change |
| --- | --- | --- | --- |
| Release blocker | Phase 3 leaves `Ea_forward` null, while both adapters require it. The standalone reviewed handoff contract exists, but no non-overwriting promotion/import step consumes it. | `src/kinetics/handoff.py`, `src/kinetics/builder.py`, both adapter generators, `src/workflow/executor.py` | Review a future hash-rechecking dataset-version promotion step. Do not estimate values or connect the contract directly to adapters. |
| Release blocker | Phase 5/6 outputs are bounded static representations, not guaranteed executable native CATKINAS/Zacros projects. | `src/catkinas/`, `src/zacros/` | Add versioned native schemas only after authoritative software formats and representative files are supplied. |
| High | A scientifically complete redistributable example cannot be provided with the current repository inputs and external-software constraints. | `examples/Fe110_CO_dissociation/` | Add a real example only when redistribution and scientific review are documented. The current example is explicitly fail-fast. |
| Medium | Validation-status loading is duplicated across adapter generators. | `src/catkinas/generator.py`, `src/zacros/generator.py` | Consolidate only after both adapter error contracts are frozen. |
| Low | Numeric formatting and small JSON writers are repeated in several output modules. | adapter writers, `src/analysis/result_writer.py`, `src/runner/execution_log.py` | Introduce shared utilities in a future non-scientific refactor with byte-for-byte regression tests. |
| Administrative | No owner-approved public distribution license is available. | `LICENSE` | Replace the restrictive notice only after the owner selects a license. |

## Resolved during Phase 11

- Removed fixed runner output/log roots; shared output roots and parser,
  simulation, and workflow logs now come from `config.yaml`.
- Added one shared phase-log context with timestamp, module, level, and message.
- Split the 370-line validator into bounded structural and energy/orchestration
  modules without changing validation rules.
- Split configuration section helpers so production Python files remain below
  300 lines.
- Verified all source functions have argument/return type annotations and
  docstrings.
- Ruff found no unused imports or local variables.
- Static import-graph audit found 50 modules and zero circular dependencies.
- No absolute user or machine paths occur in `src/` or `main.py`.

## Resolved after the compliance audit

- Added a Draft 2020-12 reviewed kinetic-parameter handoff schema.
- Added strict JSON, finite-number, dataset/reaction hash, source-file hash,
  energy-identity, method, validation, and manual-review checks.
- Added a non-eligible DRAFT template and an explicit standalone contract
  review. Workflow/adapter integration remains blocked by design.

## Review conclusion

The codebase is suitable as an auditable engineering preview. It is not ready
to claim a scientifically complete VASP-to-simulation loop until the two
release blockers above are resolved with real, reviewed data contracts.
