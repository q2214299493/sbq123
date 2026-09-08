# Phase 2B Changeset Manifest

Date: 2026-07-27
Scope: NEB path-quality responsibility and entrypoint consolidation only

## Parent review baseline

The historical Review Baseline v2 was not edited. Its current
`baseline_v2_sha256.txt` SHA-256 is
`c4755b9291093e42cb8e26c9a5839a5d9d4d89484717b308afbb63af3876719b`.

## Source and test changes

`before_sha256 = NEW` means the file was created in Phase 2B. Git status
reflects the current dirty worktree; several formal Phase 2A files were already
untracked before this phase.

| Path | Git status | Bytes | Before SHA-256 | Current SHA-256 |
| --- | --- | ---: | --- | --- |
| `scripts/neb_agent/path_quality_service.py` | `??` | 4837 | `NEW` | `0f306f106615ff0524aee590c9dc9b467700ac6e1d19d83ba7db663840feaf20` |
| `scripts/neb_agent/path_quality_cli.py` | `??` | 2386 | `0063f77d759b97d116df2c379376080d767231b9fad1517874cfc35223b09de8` | `9177d24b018549028c075a641f3ab4c5176b9bfab2cea43f780665b56b2c15e9` |
| `scripts/neb_agent/pilot_validation.py` | `??` | 9101 | `db0d00bc286138bb8a772fb292011845b1b3219f617524b25ca15f963de2e90d` | `8c280cb54e405bf215d10705213a25f25193bdf3e79730a9921838c53aef969d` |
| `scripts/ts_strategy_engine/workflow.py` | `M` | 11777 | `bff5a7e412f0f58b5d2638f8a53ff397c93e3b9dee553093812f2bea7a9bdade` | `014397403cf9a05c7b44d3aad6d9e11da99bd789c19bc674da60d7872fef1a51` |
| `tests/test_neb_path_quality_entrypoints.py` | `??` | 16815 | `NEW` | `60eb9aef25b592bb21888c13f3c5d6aaf4c24ad003077cdd9b5ebddc7147add1` |

## Phase reports

| Path | Git status | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `PHASE_2B_BEHAVIOR_BASELINE.md` | `??` | 5118 | `cdad44d6f8d26ce19c2029e0b38ba317459aa061b2755a53ba372978891bb879` |
| `NEB_PATH_QUALITY_ARCHITECTURE.md` | `??` | 4175 | `e058aa6271e2b84ab413bca479a17a11a019f829541cb97971dbea1b567e50fe` |
| `PHASE_2B_BEHAVIOR_COMPATIBILITY.md` | `??` | 4688 | `9b13db71e5a4de19eb5f9c1142c4a541db02ed72816790c28c8007080e2daf64` |
| `PHASE_2B_IMPLEMENTATION_REPORT.md` | `??` | 5545 | `29386785cd612ef7d69ded5c0012b7a3aeece725424928d9cbe806bd3e3d0837` |

This manifest intentionally does not hash itself.

## Protected invariants

| Path | Current SHA-256 | Phase 2B result |
| --- | --- | --- |
| `scripts/neb_agent/path_quality_control.py` | `12b277f51a1a9add4c82422ff7024c031dde1ceeca2b6330d80cb06d99d4b523` | Byte-identical to pre-refactor evaluator |
| `configs/neb_path_quality_control_v2.yaml` | `db2c5d32e3b5f732f7b733df8fbcb62360177a0164de0cb7e1a51848475f0b92` | Unchanged |
| `configs/neb_agent/default_thresholds.yaml` | `8074f789fb65cab93df3b267bc007603707e974c83ad7cd376deb374d784a21b` | Unchanged |
| `scripts/ts_strategy_engine/execution_gate.py` | `0e2ddca8e3888e6a0e29dcac7b8daecc29c2ece52252cbddfe059545d83c24d1` | Unchanged |
| `scripts/neb_agent/submission.py` | `ac2eaf13e97ed5320df1a2acc65ba4863148938b86abaaec2f8cc5d102ae531b` | Unchanged |
| `data/project_registry.sqlite3` | `4a179ecfc1778c603c2139e0144afc54fb1296818c4884231536f711e3ac02eb` | Unchanged |

Existing `tests/test_neb_path_quality_control.py` and
`tests/test_neb_pilot_validation.py` also remained byte-identical to their
Phase 2A hashes.

The historical source-baseline artifact files were not edited. Rechecking
their 25 recorded content hashes against the post-Phase-2B tree gives 24
matches and one expected mismatch:

`scripts/neb_agent/pilot_validation.py`

That path is an explicitly authorized Phase 2B change and its before/current
hashes are recorded above. Review Baseline v2's own 15 bound files still match.

## Validation binding

- Ruff: exit 0.
- Full pytest: exit 0, 242/242 passed.
- skip/xfail: 0.
- standalone and unified CLI help: exit 0.
- diff check: exit 0.
- relevant dependency cycles: 0.
- no real external, scheduler, calculation, migration, or database operation.
