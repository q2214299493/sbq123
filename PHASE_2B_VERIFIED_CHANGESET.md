# Phase 2B Verified Changeset

## 1. Purpose

This file is the additive verification binding for the accepted Phase 2B NEB
path-quality responsibility cleanup. It does not replace or rewrite the Phase 2A
source baseline, Review Baseline v2, or the pre-implementation Phase 2B behavior
baseline.

Verification date: 2026-07-27
Verification conclusion: `PASS`

## 2. Parent bindings

| SHA-256 | Bytes | Path |
|---|---:|---|
| `4896acaa29a1b207e0280992c9db34e2de111db455777f34d5f06ff8dd3a01cd` | 3798 | `PHASE_2B_CHANGESET_MANIFEST.md` |
| `cdad44d6f8d26ce19c2029e0b38ba317459aa061b2755a53ba372978891bb879` | 5118 | `PHASE_2B_BEHAVIOR_BASELINE.md` |
| `4dd963fc31e65e8f7f5ebd1e56d9958100547918f9817d180e45632ebcf3b86a` | 2836 | `artifacts/source_baseline/baseline_sha256.txt` |
| `c4755b9291093e42cb8e26c9a5839a5d9d4d89484717b308afbb63af3876719b` | 1792 | `artifacts/review_baseline_v2/baseline_v2_sha256.txt` |
| `16e0d20105dc99c9d013d2490e26b62b0b90979fe9cdcaac352b50523d2a1ce3` | 220 | `artifacts/review_baseline_v2/parent_baseline_sha256.txt` |
| `9d7a2bab9d46fc971eb24a17b59918c7249d32b2c36512cce6c9056df50f14a5` | 8163 | `CHANGESET_MANIFEST.md` |
| `25e46fb205b460867bf377d785f3400495291b7f1b093ea77e2d592b9288adb0` | 4132 | `REVIEW_BASELINE_V2.md` |
| `788d57d86efcdf75cb1d13ff1b0064b3a54cd83370db4a686f7a371209e56e23` | 5001 | `PHASE_2A_REPORT.md` |
| `25dccee27bd8baed43ef54998b1e8c45574d6ab7959087eaa3418ffb0e93ed34` | 4458 | `PHASE_2A1_CLOSURE_REPORT.md` |

## 3. Verified production sources

| SHA-256 | Bytes | Path | Verification meaning |
|---|---:|---|---|
| `12b277f51a1a9add4c82422ff7024c031dde1ceeca2b6330d80cb06d99d4b523` | 14384 | `scripts/neb_agent/path_quality_control.py` | Unchanged sole scientific evaluator |
| `0f306f106615ff0524aee590c9dc9b467700ac6e1d19d83ba7db663840feaf20` | 4837 | `scripts/neb_agent/path_quality_service.py` | Shared application orchestration |
| `9177d24b018549028c075a641f3ab4c5176b9bfab2cea43f780665b56b2c15e9` | 2386 | `scripts/neb_agent/path_quality_cli.py` | Compatible thin standalone CLI |
| `8c280cb54e405bf215d10705213a25f25193bdf3e79730a9921838c53aef969d` | 9101 | `scripts/neb_agent/pilot_validation.py` | Authorized Phase 2B pilot adapter |
| `014397403cf9a05c7b44d3aad6d9e11da99bd789c19bc674da60d7872fef1a51` | 11777 | `scripts/ts_strategy_engine/workflow.py` | Compatible unified workflow adapter |

## 4. Verified tests

| SHA-256 | Bytes | Path |
|---|---:|---|
| `a3dedd7f92f040cef437307958829ca8400ec7c10744ae82b7271087e3573616` | 5922 | `tests/test_neb_path_quality_control.py` |
| `8ea4ed1597b2462235fb15d1bd71213afebf521043b31a285ccbfc937e57f44a` | 18478 | `tests/test_neb_path_quality_entrypoints.py` |
| `b85880609add6fd682a65073eabf7bfb53729cb92905ddfe84ba19a7cbded939` | 4067 | `tests/test_neb_pilot_validation.py` |

The complete repository collection contained 244 tests. All 244 passed; the
focused acceptance selection contained 59 tests and all 59 passed. No skip or
xfail was reported.

## 5. Bound implementation and verification records

| SHA-256 | Bytes | Path |
|---|---:|---|
| `e058aa6271e2b84ab413bca479a17a11a019f829541cb97971dbea1b567e50fe` | 4175 | `NEB_PATH_QUALITY_ARCHITECTURE.md` |
| `9b13db71e5a4de19eb5f9c1142c4a541db02ed72816790c28c8007080e2daf64` | 4688 | `PHASE_2B_BEHAVIOR_COMPATIBILITY.md` |
| `29386785cd612ef7d69ded5c0012b7a3aeece725424928d9cbe806bd3e3d0837` | 5545 | `PHASE_2B_IMPLEMENTATION_REPORT.md` |
| `89c6c501c26310f1f29bac819d743c7ba50011ba2a4cb4284fa1d6c8fec99aa5` | 9675 | `PHASE_2B_DIFF_REVIEW.md` |
| `42e50efb0260e85a12779aba5ae37c715411740de4adcf799517091c864cfa94` | 5114 | `PHASE_2B_ENTRY_EQUIVALENCE_REPORT.md` |
| `dfab5d146fecc983ca23dad6f1c42a2ea7f07c1625a2604666c355d9d5c4238f` | 10930 | `PHASE_2B_VERIFICATION_REPORT.md` |

This file intentionally does not contain its own hash.

## 6. Historical baseline interpretation

- Phase 2A remains a historical snapshot and is still `24/25` against the
  current source tree.
- The only mismatch is
  `scripts/neb_agent/pilot_validation.py`.
- Its Phase 2A hash was
  `db0d00…2e90d`; the Phase 2B verified hash is
  `8c280c…969d`.
- `PHASE_2B_CHANGESET_MANIFEST.md` explicitly owns that authorized transition.
- Its entrypoint-test hash remains the implementation-completion snapshot. The
  verified test hash in this file supersedes it only for the 48-line
  acceptance-only collision-boundary regression addition.
- No second unexplained source-baseline mismatch was found.
- No calculation, runtime, database, migration, scheduler, submission, SSH, LSF,
  execution-gate, or scientific-configuration file is admitted by this
  changeset.

## 7. Verification commands

```text
python -m pytest tests/test_neb_path_quality_control.py tests/test_neb_path_quality_entrypoints.py tests/test_neb_pilot_validation.py tests/test_artifact_io.py tests/test_ts_strategy_engine.py tests/test_neb_execution_gate.py -q -ra
# 59 passed; exit 0

python -m scripts.neb_agent.path_quality_cli --help
# exit 0

python -m scripts.ts_strategy_engine.cli --help
# exit 0

python -m ruff check scripts modules tests
# All checks passed; exit 0

python -m pytest -q -ra
# 244 passed; exit 0

python -m pytest --collect-only -q
# 244 collected; exit 0

git diff --check
# exit 0
```

All behavior tests used mocks, in-memory objects, or temporary directories. No
real VASP/NEB calculation, SSH/LSF command, `bsub`, `bkill`, database write, or
migration was executed.
