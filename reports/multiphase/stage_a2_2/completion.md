# Stage A.2.2 · 原生模型装配依赖边界

本次按 Stage A.1 计划中的 P2 工作，以独立发布提交 `4a61aef5f5f04b37177d190a600359b05073f1d4` 为基线。开发树保留其独立开发历史。开始时，两树参与本次修改的八个已有文件逐字节相同。新增文件均在各树独立创建。

## 实现和兼容性

原先装配器选择 CATKINAS、Zacros 渲染器，渲染器和晶格工具又从装配器导入输入校验函数，构成四模块循环。现在装配器仍选择渲染器，三个消费者直接从 `scripts/native_inputs.py` 读取所需校验。原装配器模块继续导出 `conditions`、`integer` 和 `token`，旧调用者可使用同一函数对象。

装配器此前从参数 CLI 导入 `read`。现在两个 CLI 入口共享 `scripts.multiphase_contracts.read_unique_json`，沿用相同的字节读取和重复键处理。原模块的 `read` 名称继续可用。对照基线源 AST，三项校验的参数、函数体和字符串常量一致，读取函数除公开定义名之外也一致。标准压力、允许偏差、模型渲染、原生执行授权与检查点语义没有变化。

## 变更文件

| 范围 | 文件与改动 |
|---|---|
| 校验与装配 | 新增 `scripts/native_inputs.py`，从 `scripts/native_model.py` 移出已有三项校验并保留旧导入。 |
| 原生适配器 | `scripts/baseline_mkm/native.py`、`scripts/surface_kmc/native.py`、`scripts/surface_kmc/lattice.py` 各调整一行导入。 |
| 共用读取 | `scripts/multiphase_contracts.py` 在已有重复键校验旁提供读取函数；`scripts/kinetic_parameters/__main__.py` 复用该函数。 |
| 回归 | `tests/test_b5_architecture_boundaries.py` 增加原生适配器边界用例；`tests/test_native_model.py` 增加旧导入身份、UTF-16 JSON 和嵌套重复键用例。 |
| 交付与交接 | `reports/multiphase/stage_a2_2/completion.md` 及 `modules/state_handoff/events/history-stage-a2-2-native-boundary-20261121.json`。 |

## 核验结果

| 检查 | 开发目录 | 独立发布树 |
|---|---|---|
| 静态导入图（节点 / 边） | 328 / 1150 → 329 / 1151 | 287 / 1046 → 288 / 1047 |
| 循环强连通分量 | 4 → 3 | 4 → 3 |
| 离线专项 pytest | 124 通过，9 项原生运行用例显式排除 | 124 通过，同样排除 9 项 |
| py_compile 和 Ruff | 9 个变更的 Python 文件通过 | 同左 |
| 历史输入、清单与重启工件 | 10 个模型、53 个文件，全部匹配 | 同左 |

静态图采用 B5 的 maintained_trees 和 imported_modules。在两个适配器、晶格工具和新校验模块中均找不到到装配器的传递路径；装配器也无到参数 CLI 的传递路径。每个消费者及新模块分别在独立解释器中导入，均未加载装配器或参数 CLI。剩余三组环的成员与改动前相同，分别涉及 DRC 扰动对、DRC 批次和灵敏度报告。

逐字节核验在两树各执行两次，分别位于修改前和修改后。使用现有 assemble/publish 在临时目录重建 Phase 2.5 的 CATKINAS、Zacros 两种模型和 Phase 2.5.1 的八个 Zacros 案例（含 split、resume）。校验每个归档的 SHA-256；恢复案例使用 with_checkpoint 绑定原始检查点。生成的原生输入、检查点及 10 份 manifest.json 均与归档字节相同，修改前后各文件摘要也相同。

专项覆盖 test_native_model、test_native_advanced、test_kinetic_parameters、test_mkm_single_point，以及 B5 中 P1、P2 的三个边界/兼容用例。既有非法分压、多齿 CATKINAS 输入拒绝、Zacros 多齿支持和错误重启回执用例均通过。另以子进程核对两个 CLI 的帮助退出码 0 与嵌套之外的重复键输入退出码 1，错误文本仍为 `ValueError: duplicate JSON property 'x'`。

未运行全仓测试或新的科学计算，未修改生产 SQLite 或科学证据。下一项独立工作为 P3 中的扰动对与报告循环，需另行启动。
