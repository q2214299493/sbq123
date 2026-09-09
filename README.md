---
document_class: CURRENT_REFERENCE
as_of: '2026-09-10T00:00:00+08:00'
as_of_scope: B7 distribution review, not a live scientific observation
source_scope: publication document at B6 baseline; observations retain original dates
source_version: 93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a
source_version_role: B7 base commit
source_branch: codex/b7-release-environment
evidence_kind: CURRENT_CODE_STATE
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# sbq123 — source publication and recorded evidence boundaries

Development source: `C:/Users/86177/Desktop/work`. Publication target:
[q2214299493/sbq123](https://github.com/q2214299493/sbq123). B6 uses an isolated
Git worktree based on B5; it is not a copy of every current development/runtime file.
The older `C:/Users/86177/Desktop/sbq123` directory and initial source snapshot are
historical publication references, not the required location of this checkout.

See [document authority](docs/DOCUMENT_GOVERNANCE.md),
[current-state scope](docs/02_CURRENT_STATE.md), [module status](docs/06_MODULE_MAP.md),
[derived readiness](reports/capability_readiness.md), and
[publication boundaries](docs/PUBLIC_RELEASE.md).
SUPPORTED_CODE_SCHEMA: 9. production_schema_version: NOT_VERIFIED_IN_B6.
Production SQLite, credentials, POTCAR, full weights and all runtime outputs are
not included in the public source snapshot. Passing software tests establishes
software behavior only. Scheduler/accepted scientific statements in referenced
history are LAST_RECORDED_OBSERVATION, never newly observed by this README.

# Fe(110) 催化计算工作流

本仓库用于组织 Fe(110) 催化计算的证据检索、吸附构型、VASP/VTST、
过渡态验证、结果登记以及后续动力学流程。它是带科学审查门的工作流，
不是自动提交全部计算的一键程序。

## 目录

| 路径 | 用途 |
|---|---|
| `tasks/` | 当前唯一可执行步骤和待办事项 |
| `docs/` | 项目状态、方法协议、决策和科学验证规则 |
| `configs/` | 机器可读的路由、后端、阈值和计算参数 |
| `modules/` | 科学阶段的职责、输入、输出和完成条件 |
| `scripts/` | 可执行入口、解析器、生成器和工作流实现 |
| `tests/` | 行为、结构、配置和科学边界回归测试 |
| `calculations/` | 经审查的计算输入、证据和运行记录 |
| `data/` | 项目注册表等持久化数据 |
| `outputs/`、`reports/` | 派生输出和交付报告 |
| `archive/` | 已归档或仅用于追溯的材料 |

当前流程和使用边界见 [工作流架构](docs/12_WORKFLOW_ARCHITECTURE.md)；
[ARCHITECTURE.md](ARCHITECTURE.md) 保留历史架构快照。当前模块状态只以
`docs/06_MODULE_MAP.md` 为准，记录的任务入口见 `tasks/current_task.md` 和
`docs/02_CURRENT_STATE.md`；两者都不代表实时调度器证据。

## 安装

普通 wheel 安装与 editable 开发安装均有独立验证。Python 3.11 是
Windows/Linux CI 基准；开发源码仍位于 `C:/Users/86177/Desktop/work`。
配置、SQL、检索 schema 和模板由明确的资源清单打包；仓库状态和科学数据不随 wheel 分发。

```text
python -m pip install /path/to/sbq_catalyst_agent_workflow-0.1.0-py3-none-any.whl
registry-init --help
ts-strategy --help
catalysis-search --help
python -m scripts.release_smoke
```

开发安装使用 `python -m pip install -e ".[dev,neb,release]"`。
完整的 extras、平台支持、仓库上下文要求及外部 HPC/GPU 边界见
[安装与发布合同](docs/INSTALLATION.md)。已安装的软件入口可从仓库外运行；
状态管理和文档投影需要显式 `--root`，缺少上下文时返回 `REPOSITORY_CONTEXT_REQUIRED`。
安装不会提供 VASP、POTCAR、生产数据库、凭据或模型权重。

## 配置

- `configs/skill_routing.yaml`：路由、模块所有权和规则来源。
- `configs/execution_backends.yaml`：本地、AQCat25 GPU 和 VASP 后端权限。
- `configs/true_fe110_production.yaml`：当前 Fe(110) 兼容分支和阶段参数。
- `configs/neb_agent/default_thresholds.yaml`：共享 NEB 几何阈值。
- `configs/neb_path_quality_control_v2.yaml`：NEB 路径质量阈值。

配置加载后必须由所属模块验证。说明文档不能覆盖机器可读配置。

## 核心工作流

```text
白名单证据
  -> 方法与收敛分支
  -> 吸附构型规划与生成
  -> MatRIS/AQCat25 候选加速、可选 Sella 分支
  -> 本地证据/几何复核
  -> VASP/VTST
  -> 按来源方法执行频率与连接性验证
  -> 兼容分支规定的最终能量
  -> 注册表
  -> 热力学、MKM/KMC、反应器和不确定性
```

调度器完成、电子收敛、离子/力收敛、几何有效和科学接受是不同状态。

现有流程的基线捕获、失败记录与受限策略改良见
[策略学习接口](modules/transition_state_search/LEARNING.md)；MatRIS 峰值的
标准 Sella 候选、VASP 标注和模型重跑衔接见
[Sella 分支](modules/transition_state_search/SELLA_BRANCH.md)。这些功能复用现有
模型和科学审查门。原报告记录过 GPU 组件小样本（LAST_RECORDED_OBSERVATION）；B6 未复核生产状态或完整闭环收益。

## 测试和静态检查

```powershell
python -m pytest -q
python -m ruff check scripts modules tests
```

小改动先运行相关测试；只有跨模块行为变化才需要完整回归。测试通过不能
替代真实 VASP、频率、连接性或科学有效性审核。
GitHub Actions 保留 Linux 完整 pytest（包括 Sella CPU 解析势测试），并在
Ubuntu/Windows Python 3.11 上执行工程回归和真实 wheel 安装验证。

## Dry-run 与预检

- 使用各命令公开的 `--dry-run`，不要假定所有入口都支持同一参数。
- VASP 提交前先运行对应 preflight；preflight 不等于提交授权。
- NEB 提交、停止、重建、CI-NEB、DIMER 和结果推广都必须具有当前、
  哈希绑定且明确列出动作的执行门决策。
- 真实集群验证不可用时，只验证命令、输入、路径、Schema 和解析行为。

## 常见错误

- 把 `DONE` 当作收敛或科学接受；
- 混用不同 slab、XC、POTCAR、ENCUT、磁性、占据或能量参考分支；
- 跳过白名单证据门直接生成吸附或反应路径；
- 从 GPU 直接向 VASP 传输候选；
- 复用过期执行门或修改其 `ALLOWED_ACTIONS`；
- 用外部论文或 AQCat25 能量填充本地 DFT 结果。

## 安全要求

默认不提交、停止、删除、覆盖或重启真实计算。AQCat25 只生成预测候选；
VASP 结果仍需所属模块验证。不得提交 `POTCAR`、私钥、凭据或未审查的大型
运行产物。任何删除、覆盖、发布或高成本计算必须有明确授权。

## 软件测试覆盖的安全边界（CURRENT_CODE_STATE）

- 运行时后端值只通过 `scripts.execution_backends` 从
  `configs/execution_backends.yaml` 读取；提交、调度证据和结果门控拒绝
  与该配置不一致的主机、调度器和 GPU 写入路径。
- 新的基础 provenance 登记使用 `registry-write plan/apply`。`apply` 只做
  追加写入，要求当前 Schema、精确计划哈希和完整外键事务；历史裸 SQLite
  writer 仅保留在显式 compatibility allowlist 中，禁止新增。
- NEB 路径质量的唯一科学 evaluator 是
  `scripts.neb_agent.path_quality_control.evaluate_quality`。standalone CLI、
  unified workflow 和 pilot validation 通过
  `scripts.neb_agent.path_quality_service` 共享同一应用层调用路径；它们都
  不能授权提交、停止、重建、CI-NEB、DIMER 或 TS 结论。
- NEB 动作的唯一授权入口是
  `scripts.ts_strategy_engine.execution_gate`。所有执行器必须校验当前、
  哈希绑定且在 `ALLOWED_ACTIONS` 中明确列出的动作。
- TS endpoint 的原始几何证据由 `scripts.ts_endpoint.evidence` 只读采集，
  科学状态和 reason code 只由 `scripts.ts_endpoint.validator` 汇总。
  `scripts.ts_endpoint.purpose` 负责编排，`scripts.ts_endpoint.database`
  只负责持久化边界。历史 `modules.ts_endpoint_*` 和
  `modules.structure_purpose_manager` 路径仅为兼容别名。
- endpoint SQL migration 已修订，但仍禁止直接执行；真实数据库应用
  需要对具体路径单独授权，非空 rollback 永久拒绝。adapter 不会隐式
  创建、替换或迁移 Schema；不得对 `data/project_registry.sqlite3`
  未经授权执行 migration。
- 提交恢复以 `submission_attempt.json` 和调度器证据为准。未知或超时状态
  不得解释为成功，也不得自动重复提交。详见
  [SUBMISSION_RECOVERY.md](SUBMISSION_RECOVERY.md)。
- `calculations/`、`outputs/`、运行状态、调度器输出和真实数据库均不是代码
  重构 changeset 或发布源码基线的一部分，不得为整理代码而移动、覆盖或
  删除。

最终代码架构和发布边界见
[FINAL_ARCHITECTURE.md](FINAL_ARCHITECTURE.md)；历史架构文件和 Review
Baseline v1/v2/v3 保持为追加式审查链，不被覆盖。
