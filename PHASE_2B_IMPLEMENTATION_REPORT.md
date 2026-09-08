# Phase 2B Implementation Report

Date: 2026-07-27
Verdict: **PASS**

## Implemented scope

| File | Change | Purpose |
| --- | --- | --- |
| `scripts/neb_agent/path_quality_service.py` | Added | One bounded application layer for config validation/merge, monitor loading, collection, evaluation, document construction, and source binding |
| `scripts/neb_agent/path_quality_cli.py` | Reduced to thin adapter | Preserve argparse, paths, exit meaning, atomic write, and status output while delegating all orchestration |
| `scripts/ts_strategy_engine/workflow.py` | Replaced duplicate `_path_quality` orchestration | Use the same request/service and preserve return/write/order behavior |
| `scripts/neb_agent/pilot_validation.py` | Added explicit path-quality adapter | Let pilot callers reuse the same result without changing pilot acceptance or its JSON Schema |
| `tests/test_neb_path_quality_entrypoints.py` | Added | Golden behavior, real-file collection, five-entry equivalence, compatibility, invalid/missing input, evaluator error, and write-failure coverage |
| `PHASE_2B_BEHAVIOR_BASELINE.md` | Added | Pre-change source hashes, behavior samples, errors, boundaries, and complexity |
| `NEB_PATH_QUALITY_ARCHITECTURE.md` | Added | Final ownership, dependency, persistence, authority, and API boundaries |
| `PHASE_2B_BEHAVIOR_COMPATIBILITY.md` | Added | Before/after sample-level semantic comparison |
| `PHASE_2B_CHANGESET_MANIFEST.md` | Added | Phase-owned file and hash inventory |

`path_quality_control.py`, both existing path-quality and pilot test files, the
quality configuration, shared threshold configuration, execution gate,
submission module, migrations, and database were not modified.

Historical baseline artifact files were not edited. Replaying the Phase 2A
source-content baseline against current source yields 24/25 matches; the sole
expected mismatch is `scripts/neb_agent/pilot_validation.py`, whose Phase 2B
before/after hashes are explicitly recorded in the new changeset manifest.
Review Baseline v2's own 15 hash bindings remain valid.

## Removed duplication

| Measure | Before | After |
| --- | ---: | ---: |
| Path-quality config merge implementations | 2 | 1 |
| Collector/evaluator orchestration sites | 2 | 1 |
| Result-document formatting implementations | 2 | 1 |
| Scientific evaluator implementations | 1 | 1 |
| Scientific decisions in standalone CLI | 0 | 0 |
| Scientific decisions in workflow adapter | 0 | 0 |
| Duplicate path-quality calculations in pilot | 0 | 0 |
| Relevant production files | 4 | 5 |
| Relevant production lines | 934 | 1043 |
| Existing four-file lines | 934 | 896 |
| Largest function | evaluator, 180 lines | evaluator, 180 lines |
| Standalone `main()` | 53 lines | 31 lines |

Total lines increased by 109 because the new 147-line service makes validation
and boundaries explicit; the four existing modules decreased by 38 lines.
The service's largest function is 51 lines and it has one purpose, so it is not
a general NEB manager.

## Compatibility

- Authoritative evaluator:
  `scripts.neb_agent.path_quality_control.evaluate_quality`.
- Standalone module path, argument names/defaults, help meaning, output path,
  status printing, producer, document kind, and Schema remain compatible.
- `AnalyzeRequest`, workflow outward return, `neb_path_quality.json` filename,
  execution-gate input, and execution order remain compatible.
- Existing pilot build/validate signatures, `passed` semantics, magnetic
  warning behavior, and exact Schema-v2 field set remain compatible.
- Public API changes: none removed or changed; one service request type and one
  pilot adapter were added.
- Scientific logic changes: none. Evaluator and threshold-file hashes are
  unchanged.

## Validation

| Command | Exit | Result |
| --- | ---: | --- |
| `python -m py_compile` on five relevant modules | 0 | Passed |
| Targeted Ruff on changed source/tests | 0 | Passed |
| Path-quality + entrypoint + pilot tests | 0 | 20/20 passed |
| Related path-quality, pilot, TS workflow, and execution-gate tests | 0 | 49/49 passed before final test additions |
| `python -m ruff check scripts modules tests` | 0 | Passed |
| `python -m pytest -q -ra` | 0 | 242/242 passed |
| `python -m pytest --collect-only -q` | 0 | 242 collected |
| Standalone path-quality `--help` | 0 | Passed |
| Unified TS CLI `--help` | 0 | Passed |
| `git diff --check` | 0 | Passed; only pre-existing LF/CRLF warnings |
| skip/xfail scan | — | 0 |
| Relevant import-cycle check | — | 0 cycles |

Tests used in-memory evidence and pytest temporary directories only. No SSH,
LSF, `bsub`, `bkill`, VASP, NEB, scheduler, submission, database, or migration
operation was executed.

## Risks and exclusions

- No real calculation directory was used for entry equivalence; the integration
  fixture exercises the real POSCAR/INCAR collector in a temporary directory.
- Pilot path quality is deliberately an explicit adapter rather than a hidden
  new condition in `build_pilot_result`; changing pilot acceptance would
  violate the frozen Schema and scientific meaning.
- Phase 2B did not alter execution gate behavior, endpoint logic, scheduler,
  submission, migrations, database, scientific configuration, or historical
  review baselines.
- The Phase 2A source baseline is now historical rather than a current-source
  assertion: its one expected pilot-adapter difference must be evaluated
  through `PHASE_2B_CHANGESET_MANIFEST.md`.

No independent Phase 2B acceptance or other optimization theme was started.
