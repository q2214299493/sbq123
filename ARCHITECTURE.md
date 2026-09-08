# 项目架构

> 本文件保留 Phase 1 后的架构快照。Phase 2B、Phase 3B 和最终发布边界的
> 追加式统一说明见 [FINAL_ARCHITECTURE.md](FINAL_ARCHITECTURE.md)；本文件
> 不被改写为新的历史基线。

本文件说明当前代码和数据流。科学方法以所属模块 README 和
`docs/01_METHOD_PROTOCOL.md` 为准；路由与权限以机器可读配置为准。

## 权威层级

```text
机器可读配置
  -> 所属模块 README
  -> 路由 skill
  -> 解释性文档
```

`configs/skill_routing.yaml` 决定模块所有权和规则来源，
`configs/execution_backends.yaml` 决定本地、AQCat25 GPU 和 VASP 后端权限。

## 目录结构

```text
work/
├── tasks/          当前步骤和 backlog
├── docs/           状态、协议、决策、验证和交接
├── configs/        路由、后端、参数、阈值和 Schema
├── modules/        科学模块职责和少量模块自有实现
├── scripts/        主要 Python/Shell 实现和 CLI
├── tests/          回归与结构契约
├── calculations/   计算输入、证据和运行记录
├── data/           SQLite 注册表等持久数据
├── outputs/        派生输出
├── reports/        用户交付报告
└── archive/        已归档材料
```

## 主要代码层

| 层 | 位置 | 责任 |
|---|---|---|
| CLI | `scripts/**` 中入口模块 | 参数解析、调用、用户可读退出 |
| 工作流 | `scripts/ts_strategy_engine/workflow.py` 等 | 编排已验证步骤，不自行提交 |
| 领域规则 | AdsMind、NEB、TS validation 模块 | 纯计算、几何和科学证据分类 |
| 副作用 | `artifact_io.py`、scheduler、submission、registry | 文件、数据库、SSH/LSF 和提交 |
| 协议 | `configs/`、模块 README、validation docs | 阈值、Schema、允许动作和接受标准 |

## 核心数据流

```text
外部证据
  -> retrieval_top5.json
  -> adsorption/TS plan
  -> reviewed POSCAR/path + hashes
  -> AQCat25 candidate (预测证据)
  -> work geometry/provenance review
  -> VASP preflight + explicit authority
  -> scheduler/calculation files
  -> parser evidence
  -> geometry/connectivity/frequency gates
  -> matched static energies
  -> project_registry.sqlite3
  -> thermochemistry / reaction network / kinetics
```

任何阶段的“完成”只表示该阶段产生了证据，不自动接受下一阶段。

## 关键调用关系

### 吸附

```text
plan_adsorption_candidates
  -> evidence_gate
  -> prescreen / fts_prescreen
  -> site_detection
  -> candidate_generation
  -> relaxed_analysis
  -> state_deduplication
  -> result promotion gate
```

Fe(110) 位点几何的唯一核心实现在
`scripts/adsorption/build_fe110_adsorption.py`。

### 过渡态

```text
ts_strategy_engine.cli
  -> workflow / contract / fingerprint / strategy
  -> neb_agent geometry and output evidence
  -> execution_gate authorization
  -> neb_agent.submission enforcement
  -> dimer / VFA / connectivity evidence
  -> evidence registration
```

`execution_gate.py` 是唯一动作授权入口。它将决策文档的纯构造委托给
`execution_decision.py`；后者无 I/O、无调度器调用，也不选择允许动作。
`submission.py` 只执行当前哈希绑定决策中明确允许的动作。

### 持久化

```text
domain evidence
  -> artifact_io atomic JSON
  -> calculation_registry transaction
  -> schema/provenance validation
```

SQLite 事务边界负责 commit/rollback；科学模块负责生成和审核记录内容。

## 外部系统边界

| 系统 | 允许 | 禁止 |
|---|---|---|
| 本地 `work` | 证据、契约、哈希、审查、注册 | 把预测值伪装成 DFT |
| AQCat25/MZ73 | 候选松弛、路径/BA-Sella、力模型 | VASP、TS 接受、最终能量 |
| `sunboquan-codex` | VASP/VTST、频率和位移 | 未审查候选、AQCat 训练 |

GPU 结果必须返回 `work`；禁止 GPU 到 VASP 直传和自动远程提交。SSH/LSF
边界有返回码检查和有限超时，提交/停止还需要实时同任务复核。

## 状态模型

不同领域状态不应强行合并：

- 调度器：`PEND/RUN/DONE/EXIT`；
- 电子、离子/力、几何、路径、频率和连接性分别记录；
- 模块：`Planned/Active/Blocked/Completed`；
- 执行动作只由 `ALLOWED_ACTIONS` 表达。

同一概念只在所属层有一个权威来源，但不同层的状态不能用一个布尔值代替。

## 扩展规则

1. 新科学阶段先建立模块 README、输入、输出和完成条件。
2. 新阈值进入权威配置，并记录单位和来源。
3. 新外部副作用集中到边界模块，检查返回码、超时和幂等性。
4. 新 CLI 只做薄适配，业务逻辑进入可测试函数。
5. 新兼容入口必须标明调用方、退役条件和迁移路径。
