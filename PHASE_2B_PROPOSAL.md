# Phase 2B Proposal

## 候选比较

| 主题 | 收益 | 风险 | 主要源码数 | 科学逻辑 | 公共 API | 数据库 | 测试基础 | 小批次/回滚 |
|---|---|---|---:|---|---|---|---|---|
| 1. 状态定义与结果模型统一 | 高 | 高 | >10 | 可能影响状态解释 | 高 | 可能 | 分散 | 不适合首批 |
| 2. 外部命令、超时和错误上下文统一 | 中高 | 中 | 4–7 | 无预期影响 | 中 | 无 | 较好 | 可做，但通用框架易过度设计 |
| 3. 配置加载与边界验证统一 | 中高 | 中 | 6–10 | 阈值加载属于科学边界 | 中 | 无 | 中等 | 可做，需较大快照测试 |
| 4. CLI 与业务逻辑分离 | 中高 | 低中 | 4–7 | 无预期影响 | 中 | 无 | 不均衡 | 可小批次 |
| 5. NEB 路径质量模块职责整理 | 高 | 低中 | 5 | 锁定现有判定，不改阈值 | 低 | 无 | 5 个纯判定测试及 workflow 测试 | 可独立验证、易回滚 |
| 6. TS endpoint 生成/验证/持久化分离 | 高 | 高 | 4–7 | 有 | 高 | 有 | 很好 | migration 未关闭，不适合 |
| 7. 重复文件读写与 artifact 管理 | 中高 | 中 | >10 | 无预期影响 | 中 | 无 | 较好 | 范围过宽 |
| 8. 工作流编排与具体执行分离 | 高 | 高 | >10 | 间接影响授权顺序 | 高 | 可能 | 较好 | 不适合首批 |

## 选定主题

**5. NEB 路径质量模块职责整理**

## 证据

当前有两个 orchestration：

1. `scripts/neb_agent/path_quality_cli.py`
2. `scripts/ts_strategy_engine/workflow.py::_path_quality`

两者重复读取和合并配置、调用同一 collector/evaluator、写同名 artifact，
而正式统一 TS CLI 使用第二条路径。纯判定函数已有 5 个测试，但没有证明
两个入口输出等价。

## 建议 2B 范围

主要源码限制为：

- `scripts/neb_agent/path_quality_control.py`
- `scripts/neb_agent/path_quality_cli.py`
- `scripts/ts_strategy_engine/workflow.py`
- `scripts/ts_strategy_engine/cli.py`
- `scripts/ts_strategy_engine/execution_evidence.py`

测试范围：

- `tests/test_neb_path_quality_control.py`
- `tests/test_ts_strategy_engine.py`

## 实施约束

- 不改变 `evaluate_quality()` 的状态、reason code、优先级或阈值含义；
- 不改变 `neb_path_quality_control_v2.yaml`；
- 不改变现有 CLI 参数或模块路径；
- 不删除 standalone CLI，只将其变为兼容薄适配层；
- 建立一个共享 report builder，统一配置合并、source manifest 和写入前
  payload 构造；
- execution gate 仍是唯一授权层；
- 不接触 endpoint、migration、数据库、submission 或真实计算。

## 必需测试

1. standalone 与 unified workflow 对同一 fixture 产生等价核心 payload；
2. producer、document kind、Schema version 和 source manifest 不变；
3. 五个现有 path-quality 判定测试完全不变；
4. CLI `--help` 和旧模块 import 保持有效；
5. 缺失/非法配置错误保持清晰；
6. 不产生网络、scheduler 或任务副作用；
7. 完整 pytest、Ruff 和 diff check 通过。

## 回滚

变更限定在 5 个主要源码文件和 2 个测试文件，不涉及数据库或计算数据；
可用单一 patch 回滚。若入口等价性不能建立，保留现有两个 orchestration，
不修改科学 evaluator。
