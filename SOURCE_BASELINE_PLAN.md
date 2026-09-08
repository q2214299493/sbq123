# Source Baseline Plan

## 结论

23 个 E 类文件均已获得唯一归属。建议形成 10 个正式源码、6 个正式测试、
3 个正式配置和 2 个正式 migration 候选的版本基线；另有 1 个重复候选和
1 个需要人工确认的规则文档。

## A. 建议纳入正式版本控制

### 正式源码

- `modules/structure_purpose_manager.py`
- `modules/ts_endpoint_database.py`
- `modules/ts_endpoint_generator.py`
- `modules/ts_endpoint_validator.py`
- `scripts/neb_agent/magnetic_continuity.py`
- `scripts/neb_agent/path_quality_control.py`
- `scripts/neb_agent/pilot_validation.py`
- `scripts/ts_strategy_engine/active_learning_calibration.py`
- `scripts/ts_strategy_engine/execution_evidence.py`
- `scripts/ts_strategy_engine/execution_gate_cli.py`

### 正式测试

- `tests/test_neb_execution_gate.py`
- `tests/test_neb_path_quality_control.py`
- `tests/test_neb_pilot_validation.py`
- `tests/test_structure_purpose_manager.py`
- `tests/test_vasp_inputs.py`
- `tests/test_vasp_result_gate.py`

### 正式配置

- `configs/neb_path_quality_control_v2.yaml`
- `configs/structure_purpose_routing.yaml`
- `configs/ts_connectivity_gate.yaml`

### 正式 migration 候选

- `modules/calculation_registry/migrations/001_ts_endpoint_records.sql`
- `modules/calculation_registry/migrations/001_ts_endpoint_records_rollback.sql`

Migration 纳入版本审查不等于允许执行。`MIGRATION_REVIEW.md` 的
`NEEDS_REVISION` 条件必须先关闭。

## B. 建议作为实验模块保留

无。没有文件仅凭“未 import”被降级为实验状态。

## C. 疑似重复，等待下一阶段处理

- `scripts/neb_agent/path_quality_cli.py`

它与 unified workflow 重复配置加载、evidence orchestration 和 artifact
写入，但 CLI 完整可启动。本轮保留，不删除、不重命名。

## D. 疑似 legacy，暂时保留

无。`StructurePurposeManager` 内的 legacy routing 是兼容分支，不代表该
模块本身是 legacy。

## E. 需要人工确认

- `AGENT_RULE_TS_ENDPOINT.md`

它被正式 transition-state README 指定为规则 authority，内容与 endpoint
实现一致，但 Git 中无历史记录，且本轮状态分类没有 `FORMAL_DOCUMENT`。
需要项目所有者确认它是否作为正式治理文档进入版本控制。

还需人工确认 migration 的执行和 rollback 政策，但两个 SQL 文件的源码
归属仍为 `FORMAL_MIGRATION`。

## F. 不属于源码但不得删除

E 类中无 generated/runtime 文件。冻结 F 类 474 项继续按原清单保留，不
进入源码基线。

## 机器可读清单

已生成：

```text
artifacts/source_baseline/formal_source_paths.txt
artifacts/source_baseline/formal_test_paths.txt
artifacts/source_baseline/formal_config_paths.txt
artifacts/source_baseline/formal_migration_paths.txt
artifacts/source_baseline/baseline_sha256.txt
```

`baseline_sha256.txt` 绑定 21 个正式候选和 4 个路径清单，共 25 项。它不
哈希自身。没有执行 `git add`、commit 或 push。
