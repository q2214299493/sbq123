# Final Verification Report

Date: 2026-07-27

## Final conclusion

**PASS — ENDPOINT CONDITIONS CLOSED; READY FOR MANUAL COMMIT REVIEW**

The repository passes the full regression after the authorized endpoint
correction. No real database migration, scientific calculation, scheduler, or
remote operation was performed.

## Acceptance results

| Requirement | Result |
|---|---|
| Open P0 | 0 |
| Full tests | 274 passed |
| Endpoint focused tests | 45 passed |
| Skip/xfail | 0 |
| Ruff | passed |
| `git diff --check` | passed |
| Endpoint scientific validator | unique |
| Public endpoint signatures/result fields | compatible |
| Extreme contact | now rejected |
| Actual vertical desorption | now review-required |
| Empty reaction ID | rejected at request and record boundaries |
| Core registry schema version | unchanged at 5 |
| Endpoint extension | revised, temp-tested, real execution not authorized |
| Real registry | SHA-256 unchanged |
| Final release manifests | 329 bound asset rows verified |
| Manual staging allowlist | 182 paths; five disjoint groups; no prohibited path |
| Git index | unchanged/empty |

## Commands actually run

```text
python -m ruff check <changed endpoint/test files>
python -m pytest -q tests/test_ts_endpoint_contracts.py tests/test_structure_purpose_manager.py
python -m ruff check scripts modules tests
python -m pytest -q -ra
python -m pytest --collect-only -q
python -m pytest -q tests/test_repository_contracts.py::test_root_contains_no_executable_or_download_clutter
git diff --check
```

The endpoint suite finished with 45 passed. Collection reported 274 tests and
the full suite completed 274/274 with no skip/xfail.

## Endpoint correction evidence

- A 0.2 Å C–O endpoint is `REJECTED` with
  `UNPHYSICAL_ATOM_CONTACT`.
- Collision evaluation uses configured covalent-radius scaling plus an
  absolute cap; it is separate from connectivity detection.
- An adsorbate atom rising more than 2.0 Å relative to the surface top produces
  `REVIEW_REQUIRED` with `ADSORBATE_DESORPTION_WARNING`.
- Opposite in-plane motion is not falsely classified as desorption.
- Whitespace-only `reaction_id` raises `ValueError` in both
  `TSEndpointGenerationRequest` and `TSEndpointRecord`.
- The public `EndpointValidationResult` field list is unchanged.
- The threshold version is intentionally updated to
  `ts_endpoint_thresholds_v2`.

## Authority verification

- `scripts.ts_strategy_engine.execution_gate` remains the only NEB action
  authority.
- `scripts.neb_agent.path_quality_control.evaluate_quality` remains the only
  NEB path-quality evaluator.
- `modules.ts_endpoint_validator.TSEndpointValidator` remains the only endpoint
  scientific status/reason authority.
- `modules.ts_endpoint_evidence` provides raw metrics only.
- Manager and database modules do not scientifically revalidate endpoints.

## Migration verification

The revised optional endpoint extension was exercised only on pytest temporary
SQLite files:

- fresh forward application;
- exact-shape repeat;
- incompatible same-name table refusal;
- forced post-validation failure with complete DDL rollback;
- legacy rollback refusal;
- wrong-confirmation refusal;
- non-empty rollback refusal with data retained;
- explicitly confirmed empty rollback.

The core registry version remains 5. The optional extension uses its separate
`ts_endpoint_schema_version=1`. Direct SQL execution remains prohibited.

Current review-only SQL hashes:

- forward:
  `e84506a2b1106dc564bef9fb14f60832315c4829f5f56d4e59b509886961119e`
- rollback:
  `bb95bda8141294dbfba06987dea595b28c538def7b3690441e790fb3b3ae7db2`

## Side-effect protection

The real registry remained:

`4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb`.

No migration was run against it. No SSH, LSF, `bsub`, `bkill`, VASP, NEB,
database write, Git stage, commit, push, or tag occurred.

## Additional regression correction

The full suite exposed a stale exact-artifact-layout contract that omitted the
already established `artifacts/final_release_baseline/` directory. The test was
not weakened: all eight expected filenames were added explicitly. The targeted
contract test and full suite then passed.

## Remaining risks

- Real-registry migration still requires a recoverable copy and explicit
  path-specific authorization.
- Non-empty endpoint rollback is intentionally unavailable.
- The release baseline is local evidence until a reviewed manual commit and
  off-machine backup exist.
- Atomic artifact writes remain complete-file last-writer-wins.
