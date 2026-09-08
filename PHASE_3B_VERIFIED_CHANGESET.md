# Phase 3B Independently Verified Changeset

Date: 2026-07-27
Parent implementation manifest:
`PHASE_3B_CHANGESET_MANIFEST.md`
Parent manifest SHA-256:
`9d14905c3a6265a4b5ae8e50e35ba18ee39613b0927fd01574f557a1d13843fc`

This is an additive verification record. It does not replace or modify Phase
3A, Phase 3B implementation, source-baseline, Review v1, Review v2, or Review
v3 manifests.

## Implementation changeset verification

At independent-acceptance start, every production and test hash listed by
`PHASE_3B_CHANGESET_MANIFEST.md` matched current bytes.

Verified implementation production state:

| SHA-256 | Bytes | Path | Finding |
|---|---:|---|---|
| `51822d18e5a61793f40c5f49253d572471327bc4ecc2437d43823af430bdabf2` | 2985 | `modules/ts_endpoint_evidence.py` | authorized new raw collector |
| `04e0a33d98d3317e9c3bec094f854651b1aab5ddc8dd831e173baa3f52c50fa5` | 17710 | `modules/ts_endpoint_validator.py` | authorized delegation |
| `db07eea4541cfdb414cc8957a50dd14b5881264c5310d20df7f6900c28ddc1da` | 6015 | `modules/ts_endpoint_generator.py` | exact Phase 3A hash |
| `f68fbb78a7e5f4926cb0531a5b4b0e38211fc839bd8304f1ad96d846651749b5` | 9668 | `modules/structure_purpose_manager.py` | exact Phase 3A hash |
| `8145e739bf80b0eee5e017a28b3caf4e0dac9310b85090f60d6bcef77208a702` | 7763 | `modules/ts_endpoint_database.py` | exact Phase 3A hash |

No production source was changed during independent verification.

## Verification-only test change

| Before SHA-256 | After SHA-256 | Before/after bytes | Path |
|---|---|---:|---|
| `998e85ce61844fa7cb4a7c38d693a13bb380bfb80d2110f06b5a53d39fcf9997` | `4af139c9fd4802d6b6670239e6f13e0675d7b05bf412ce2d1aa79e301cad4bf4` | `30302 -> 37394` | `tests/test_ts_endpoint_contracts.py` |

Verification delta:

- tests: `20 -> 25`;
- lines: `869 -> 1075` (`+206`);
- bytes: `+7092`;
- production changes: `0`.

Added coverage:

1. one ASE/POSCAR load per structure per validation;
2. new object identity across calls and no stale cache;
3. cell/PBC/constraint/tag/magnetic-moment preservation;
4. collector metric exception propagation and no persistence;
5. database failure propagation through manager;
6. JSON serialization rollback;
7. incompatible-table preservation and no migration call.

`tests/test_structure_purpose_manager.py` was not changed during verification
and remains:

```text
14fe6e6ea5a1178659156616089fb9c41c0a4f1d6a5537230c8fba88af68156e
```

## Independent reports

| SHA-256 | Bytes | Path |
|---|---:|---|
| `ea67dd291842577de34231a140ea05eb83dd9a2a819b05316c05bfb2cae2c5e7` | 8350 | `PHASE_3B_DIFF_REVIEW.md` |
| `4202c2912685c6ddaee33429536c701cb53c76f0453eaef8c97822f6fd46d328` | 7199 | `PHASE_3B_BEHAVIOR_VERIFICATION.md` |
| `756c3d4867b3f27aa8cef3348882d9652eb65d5cd33db72ed73edf46af76e9a8` | 2733 | `TS_ENDPOINT_FROZEN_ISSUES.md` |
| `a8be1cf66ae11543ca2f886de792277ac8577a5b7601352fd07bad446f4d0e75` | 11447 | `PHASE_3B_VERIFICATION_REPORT.md` |

This file intentionally does not hash itself.

## Protected-state verification

| SHA-256 | Path | Result |
|---|---|---|
| `4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb` | `data/project_registry.sqlite3` | before/after match |
| `a4bc47e51e21a612e067b8a4fd123703db3da207219c3ebc7a28f16164ad5315` | `configs/structure_purpose_routing.yaml` | unchanged |
| `43427e5bd1a7950d7ee6defc0ce43c14c80b37b04175ee790fba1f61c629fe88` | `configs/ts_connectivity_gate.yaml` | unchanged |
| `cbbedb50005d1bc57a821d5e983e2578c2d8e43c8f0cfe774f710af91ce1093f` | forward endpoint migration | unchanged/unexecuted |
| `6fdd989767a58aea76987cdbff4b0fa77182f1d4fd8cb2477ae10dacaa4808d5` | rollback endpoint migration | unchanged/unexecuted |
| `3e395bac41f647ddd9b8f7b2887c7554f9f8647aa513581c642c0219b0099307` | Review Baseline v3 binding | unchanged |

The five Phase 2B production hashes bound by Review Baseline v3 also matched.
Execution gate, scheduler-evidence, and submission files matched their
acceptance-start hashes.

## Validation binding

```text
endpoint tests: 41/41 passed
complete tests: 270/270 passed
test files collected: 37
skip/xfail: 0
Ruff: passed
git diff --check: exit 0
cycles: 0
duplicate top-level endpoint definitions: 0
broad/bare endpoint exception handlers: 0
```

No migration, real database write, SSH, LSF, `bsub`, `bkill`, VASP, NEB,
staging, commit, or push occurred.

## Verified conclusion

**PASS**

The Phase 3B production changeset is accepted. The only independent-review
mutation is additional regression coverage recorded above.
