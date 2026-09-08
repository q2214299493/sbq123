# Final Code Quality Audit

Date: 2026-07-27

## Scope and method

The audit covered 108 production Python files under `scripts/` and `modules/`
(excluding the separately governed `modules/memory_migration`), 15,874 lines,
and 132 internal import edges. It used Ruff plus a repository-local AST scan;
no new lint dependency or rule set was introduced.

## Results

| Check | Result | Evidence / qualification |
|---|---|---|
| Unused imports and variables | PASS | Ruff `F` rules pass |
| Syntax/import validity | PASS | 108/108 files parsed; full tests import exercised modules |
| Duplicate top-level definitions | PASS | 0 found |
| Unreachable/syntax-error code | PASS | Ruff `E7/E9` and AST parse pass |
| Circular imports | PASS | 0 cycles in the 132-edge internal graph |
| Bare `except` | PASS | 0 |
| Broad exception silently continued | PASS | 0; three broad handlers all rollback/clean up and re-raise |
| Unlimited `while True` | PASS | 0 |
| `subprocess.run` without timeout | PASS | 0 of 5 production calls |
| `Popen`, `os.system`, or `shell=True` boundary bypass | PASS | 0 found |
| Fixed shared `.tmp` name | PASS | 0; two `.tmp` suffixes use unique same-directory `mkstemp` |
| `cwd`/`os.getcwd` dependency | PASS | 0 direct uses |
| production `sys.path` mutation | PASS | 0 |
| import-time execution/printing | PASS | no I/O/submission/database call and no top-level print found |
| production debug `print` | PASS | 65 calls in 36 executable/CLI/reporting modules are user output; no import-time/debug-only print identified |
| direct SQLite access outside adapters | PASS WITH SCOPE | registry-owned modules and explicitly isolated endpoint adapter only; no endpoint science module opens SQLite |
| obvious synonymous final authorities | PASS | duplicate-looking state strings are domain-local; no second gate/evaluator/validator |
| commented-out large code block | PASS | none identified in production scan |
| TODO/FIXME/XXX in production Python | PASS | 0 |
| skipped/xfail tests | PASS | 0 markers; pytest reported none |
| Ruff configured checks | PASS | `E4,E7,E9,F,C90`; “All checks passed” |

## External command boundaries

All production Python process launches are bounded:

| Caller | Command family | Timeout source |
|---|---|---|
| `scripts/scheduler_evidence.py` | LSF query | `LSF_QUERY_TIMEOUT_SECONDS = 60` |
| `scripts/neb_agent/remote_monitor.py` | SSH monitor | `SSH_TIMEOUT_SECONDS = 60` |
| `scripts/neb_agent/submission.py` | submit/stop command | shared `EXTERNAL_COMMAND_TIMEOUT_SECONDS = 300` |
| `scripts/convergence/setup_alpha_fe_bulk_smearing.py` | `bsub` | shared `EXTERNAL_COMMAND_TIMEOUT_SECONDS = 300` |
| `scripts/adsmind_lite/audit_remote_fe110_batch.py` | read-only SSH audit | local 60 s command timeout and 15 s SSH connect timeout |

Timeout, nonzero exit, and unknown scheduler state remain distinct error
paths. No retry loop is unbounded. The read-only adsorption audit retains local
literal timeouts; this is a P2 consistency issue, not an observed correctness
failure.

## Write boundaries

State/report JSON writers in the refactored paths use `scripts.artifact_io`.
It creates a unique temporary file in the target directory, flushes and
`fsync`s it, atomically replaces the target, deletes a failed temporary file,
and preserves the prior target on serialization failure. Concurrency tests
support atomic complete-file replacement, not merge semantics: simultaneous
writers are intentionally last-writer-wins.

Direct `Path.write_text` remains in input/campaign builders that populate a new
destination (INCAR, KPOINTS, POSCAR, job scripts, manifests) and in
`aqcat25_ts_training_data.py`. These are not shared mutable state files and no
Phase 4 regression evidence justifies rewriting them. A caller that reuses an
existing destination still owns overwrite protection.

## Complexity

- Largest module: `modules/ts_endpoint_validator.py`, 505 lines.
- Largest function: `scripts/ts_validation/analyze_vfa.py::analyze_vfa`,
  208 lines.
- Other long scientific functions include
  `path_quality_control.evaluate_quality` (180 lines) and
  `active_learning_domain.assess_independent_ts_domain` (162 lines).
- Ruff's configured maximum McCabe complexity of 15 passes.

The long functions are maintenance risks, but splitting them during release
closeout would be higher risk than leaving their tested scientific order
intact. They are deferred rather than silently classified as clean.

The authorized endpoint correction mechanically extracted only the validator
status-priority block. `validate` is 140 lines and remains within Ruff's
complexity limit; broader scientific decomposition was intentionally avoided.

## Final production-change qualification

Phase 4 itself changed no production code. The later authorized endpoint
correction added bounded contact/desorption/identity checks and transactional
migration guards. Ruff and the 274-test full suite pass after those changes.
