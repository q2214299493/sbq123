# 重构报告

## 范围

本轮只处理审计中已有直接证据、可由测试验证且不改变科学语义的低风险问题。

## 删除

未删除任何代码、配置、数据或历史结果。

## 合并

未发现有充分证据可合并的重复业务实现。

## 拆分

- 新增 `scripts/ts_strategy_engine/execution_decision.py`，负责 Schema v2
  决策文档的纯构造和派生字段。
- `execution_gate.py` 保留全部证据优先级、动作选择、哈希复算和授权校验，
  从 370 行降至 310 行，恢复包内 320 行结构契约。

## 可靠性修改

- `scripts/neb_agent/remote_monitor.py`：SSH 监视增加 60 秒超时和可读错误。
- `scripts/scheduler_evidence.py`：LSF 实时查询增加 60 秒超时。
- `scripts/neb_agent/submission.py`：上传、查询、提交和停止的外部命令增加
  300 秒上限，保留 `TimeoutExpired` 原始异常链。
- `scripts/artifact_io.py`：原子 JSON 写入改为同目录唯一临时文件、flush、
  `fsync` 和原子替换；失败时保留旧目标并清理临时文件。

## 保留

- 科学公式、阈值、候选筛选、状态优先级和默认参数；
- 执行门名称、Schema、字段、动作顺序和公开导入；
- CLI、配置字段、数据库 Schema、文件格式和输出含义；
- AQCat25/VASP 权限、人工复核和真实计算授权要求；
- 所有历史结果和用户已有工作树修改。

## 文档

新增根 `README.md`、`PROJECT_AUDIT.md`、`REFACTOR_PLAN.md`、
`ARCHITECTURE.md`、`DEPRECATED_CODE.md` 和本报告；同步更新脚本和
TS 模块的代码结构说明以及旧测试快照。

## 新增测试

- 原子 JSON 成功替换和序列化失败回滚；
- 远程 NEB 监视超时；
- LSF 查询有限超时；
- 提交命令超时异常链。

## 接口和配置

- 公开 Python 接口：未改变。
- CLI 参数：未改变。
- 配置字段和默认值：未改变。
- 数据库和输出 Schema：未改变。

## 验证结果

- 初始：197 项测试，196 通过、1 个结构契约失败；Ruff 通过。
- 修改后：202 项测试全部通过。
- 针对性语法、执行门、远程监视、提交、AQCat25 handoff/active-learning
  和原子写入测试均通过。

- 最终 Ruff：通过。
- 配置解析：25 个 YAML 和 4 个 JSON 全部通过。
- CLI smoke：统一 TS CLI 和 AdsMind 规划 CLI 的 `--help` 均正常退出。
- 修改范围 `git diff --check`：通过。

## 尚未验证

- 未连接 MZ73 或 `sunboquan-codex` 做真实远程命令测试。
- 未提交、停止或重启任何真实计算。
- 未运行 VASP、NEB、DIMER、频率、MKM、KMC 或反应器计算。
- 未验证外部用户脚本是否仍调用待退役兼容入口。

## 剩余风险

- 当前工作树含大量本次之前的未提交 TS 和计算证据改动，不能把完整工作树
  视为本轮重构产物。
- 数个科学分析函数仍较长；在缺少更细粒度行为测试前继续拆分风险高。
- AQCat25/FairChem GPU 环境仍缺少独立、版本锁定的依赖清单。
