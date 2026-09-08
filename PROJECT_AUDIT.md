# 项目审计

审计日期：2026-07-27

## 范围与基线

本次审计覆盖当前工作树中的 `scripts/`、`modules/`、`configs/`、`tests/`
以及架构和状态文档；只对 `calculations/`、`outputs/`、`archive/` 做目录和
版本控制层面的检查，没有读取大型运行产物或把历史结果重新解释为当前状态。

已核实的基线：

- `HEAD` 中有 568 个跟踪文件；当前工作树在审计前已有大量未提交修改和
  新计算证据，本次未清理或覆盖这些内容。
- 静态分析覆盖 105 个当前 Python 实现文件、572 个函数；没有语法错误。
- 初始完整测试收集 197 项，196 项通过、1 项失败。失败原因是
  `scripts/ts_strategy_engine/execution_gate.py` 370 行，违反该包不超过
  320 行的结构契约。
- 初始 `python -m ruff check scripts modules tests` 通过。
- 当前 `scripts` 内部导入图未发现循环依赖。
- 结构测试未发现完全相同的 Python 文件或非平凡函数体复制。

## 1. 主要功能

1. 白名单优先的催化结构、吸附构型和反应路径证据检索。
2. Fe/Fe(110) 数值参数和表面模型收敛工作流。
3. AdsMind Lite 吸附候选规划、位点检测、结构生成、弛豫分析和去重。
4. AQCat25 吸附和 TS 候选加速及哈希绑定的跨后端交接。
5. VASP/VTST 输入、调度证据、NEB/CI-NEB/DIMER 和频率证据处理。
6. TS 反应契约、路径质量、执行授权、连接性和 Grade-A 验证。
7. SQLite 计算注册表和结果来源管理。
8. 热力学、反应网络、MKM、KMC、反应器和不确定性模块接口。

## 2. 核心执行流程

```text
current_task
  -> skill_routing / owning module
  -> whitelist evidence
  -> reviewed structure or path candidate
  -> backend handoff contract
  -> preflight
  -> hash-bound execution gate
  -> explicitly authorized external action
  -> scheduler + calculation-file evidence
  -> geometry/scientific validation
  -> registry promotion
```

调度状态、电子收敛、离子或力收敛、几何有效和科学有效分别判断。GPU
候选必须返回本地审核；VASP 是第一性原理结果来源，但 VASP 完成仍不等于
科学接受。

## 3. 主要模块及职责

| 模块 | 责任 |
|---|---|
| `catalysis_data_retrieval` | 外部结构和路径的唯一检索入口 |
| `convergence_workflow` | 当前 Fe(110) 方法和收敛分支 |
| `adsmind_lite` | 证据约束的吸附候选规划 |
| `adsorption_workflow` | VASP 吸附弛豫、结果审核和端点 |
| `transition_state_search` | 契约、路径、NEB/CI-NEB/DIMER 和执行门 |
| `ts_vibrational_validation` | 频率、虚频模式和双向连接性 |
| `calculation_registry` | 任务、文件、数值、来源和审核记录 |
| `kinetic_data` 及下游模块 | 经验证数据到热力学、MKM/KMC 和反应器 |
| `incar_custodian` | 所属模块门控之后的参数建议，不替代科学判断 |

所有模块都有 README；模块状态集中在 `docs/06_MODULE_MAP.md`。

## 4. 重复与冗余

- 没有发现可直接删除的完全重复实现。
- `scripts/adsmind_lite/core.py` 和
  `scripts/aqcat25_ts_active_learning.py` 是明确的兼容层，不是重复业务
  实现；新代码不应继续依赖它们。
- YAML 映射加载存在多处调用，但它们读取不同领域配置。未经统一 Schema
  和错误契约前，不应机械合并为“万能配置器”。
- JSON 写入已经集中到 `scripts/artifact_io.py`；本次修复了固定临时文件名
  带来的并发冲突风险。

## 5. 疑似无用或待退役内容

没有证据支持直接删除任何生产文件。以下内容需要迁移确认：

- AdsMind `core.py` 兼容导出；
- 旧 AQCat25 TS active-learning 模块入口；
- 已完成的 `modules/memory_migration/` 历史迁移材料；
- 仓库根目录的本地 `AGENTS.md.bak.*` 备份文件。

状态和建议见 `DEPRECATED_CODE.md`。

## 6. 高耦合模块

静态长度和函数职责显示以下区域需要后续小步处理：

| 区域 | 证据 | 处理建议 |
|---|---|---|
| `modules/ts_endpoint_validator.py` | 479 行；`validate` 137 行 | 当前为未跟踪开发文件，先稳定测试和所有权，再迁入明确包 |
| `scripts/adsmind_lite/relaxed_analysis.py` | 447 行 | 按连通性、位点和 slab 位移证据拆分纯函数 |
| `scripts/adsorption/build_fe110_adsorption.py` | 433 行 | 保留 Fe(110) 几何唯一权威，避免为行数强拆 |
| `scripts/ts_validation/analyze_vfa.py` | 主函数 208 行 | 按解析、判级和报告组织器拆分 |
| `scripts/neb_agent/path_quality_control.py` | `evaluate_quality` 180 行 | 将证据提取与决策分类分离 |
| `scripts/neb_agent/analyze_neb_outputs.py` | `analyze` 164 行 | 将逐图解析与汇总分离 |

这些函数目前 Ruff 复杂度检查通过；长度只是审查信号，不是自动修改依据。

## 7. 不合理依赖

- `fairchem` 由 MZ73/AQCat25 专用脚本导入，但未在 `pyproject.toml` 中声明；
  这反映远程专用环境，不能加入基础依赖。应在后续为 GPU 环境提供独立、
  可复现的依赖清单。
- `ase` 同时出现在 `adsmind` 和 `neb` extras，语义合理但安装说明此前不完整；
  根 README 已明确推荐组合安装。
- 未发现 `scripts` 内部循环导入、`global` 语句或 `Path.cwd()/os.getcwd()`
  隐式依赖。

## 8. 边界处理缺失

审计时确认并已修复：

- NEB 远程监视 SSH 没有超时；
- LSF 实时查询没有超时；
- NEB 上传、提交、停止等外部命令没有超时；
- 原子 JSON 写入使用固定 `.tmp`，并发进程可能互相干扰。

仍待处理：

- 11 个实现文件仍有直接 `write_text()`；其中多数是明确的 VASP 输入生成，
  不能统一改为原子覆盖，需逐个确认覆盖策略。
- 配置加载后的对象类型验证分散；当前 25 个 YAML 和 4 个 JSON 配置均可
  解析，但不是全部都有显式 Schema。
- 一个 `except Exception` 位于 SQLite 事务边界，执行 rollback 后立即
  re-raise，属于合理的资源边界，不是静默吞错。
- 63 个 `print` 调用主要位于 CLI 入口；没有证据表明它们是遗留调试输出。

## 9. 兼容性风险

高风险且本次未改变：

- 科学公式、阈值、候选筛选和锁定 Fe(110) 计算参数；
- 数据库 Schema、历史结果和能量参考；
- CLI 参数、配置字段、输出 Schema 和执行门 Schema；
- AQCat25、VASP 和本地工作区的权限边界；
- 真实任务提交、停止、重建和结果推广。

当前工作树已有大量未提交计算和 TS 改动。任何跨目录移动或大规模命名修改
都可能覆盖用户工作，因此本次只实施可隔离、测试覆盖明确的修改。

## 10. 保留、合并、拆分、移动或删除建议

- 保留：科学模块边界、权威配置层、Fe(110) 几何核心、哈希绑定执行门、
  注册表证据模型。
- 合并：没有发现可安全合并的重复业务实现。
- 拆分：执行门的纯文档构造已拆出；其余长函数按上表逐项、先补测试再拆。
- 移动：稳定后将直接位于 `modules/` 根的 TS endpoint 实现移至明确的
  `scripts` 包，`modules/` 保留职责和协议；当前不移动未跟踪开发文件。
- 删除：本次不删除文件。兼容入口先收集调用证据，再按
  `DEPRECATED_CODE.md` 退役。

## 11. 风险分级重构计划

| 风险 | 内容 | 当前状态 |
|---|---|---|
| 低 | 执行门序列化职责拆分、外部命令超时、原子 JSON 临时文件、根 README | 已完成 |
| 中 | VFA/NEB 长函数拆分、配置对象统一验证、GPU 专用依赖清单 | 计划中；需逐模块测试 |
| 高 | TS endpoint 文件迁移、公共状态模型统一、数据库/配置/CLI 迁移 | 暂缓；需单独授权和兼容方案 |

## 结论

项目的科学阶段和权限边界总体清楚，主要风险不是缺少抽象，而是活跃 TS
开发造成局部文件膨胀、文档测试快照过期，以及少数外部/文件系统边界缺少
有限失败机制。本次没有证据支持大规模重写或删除。
