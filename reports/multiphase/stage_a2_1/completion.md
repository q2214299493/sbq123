# Stage A.2.1 · Registry CLI 依赖边界

审计基线为 `dbd34f0132a60f5229047d9dccd133750ed1cfae`。本次修复 P1。分析与登记直接引用已有的领域校验函数。运行时代码共改两行。

## 完整变更清单

| 文件 | 变更 |
|---|---|
| `scripts/baseline_mkm/analysis.py` | 替换 registry_files 使用的校验函数导入。 |
| `scripts/baseline_mkm/registration.py` | 替换 registry_batch 使用的校验函数导入。 |
| `tests/test_b5_architecture_boundaries.py` | 新增一个函数身份回归用例，约束两个 MKM 调用方及公开 CLI 导出继续共享同一函数。既有测试仅检查导入边界及其他 Registry 操作的身份。 |
| `reports/multiphase/stage_a2_1/completion.md` | 本报告，含回归、CLI、导入图和验收范围。 |
| `modules/state_handoff/events/history-stage-a2-1-registry-boundary-20261121.json` | 以报告哈希登记本次修复的历史事件，投影进入人工审核。 |

## 接口和异常

修改前，`analysis` 和 `registration` 都从 `scripts.registry_write` 引用 `validate_registry_batch`，CLI 再从 `scripts.registry_mutations` 导出它。修改后，两个 MKM 模块和 CLI 均直接从 `scripts.registry_mutations` 导入。历史导入 `from scripts.registry_write import validate_registry_batch` 仍可用。

`registry_files(analysis, out, reviewer, timestamp)` 构造包含派生分析文件的批次；`registry_batch(run, reviewer)` 校验已接受单点及其工件后构造批次。两者都将一个字典作为唯一位置参数传给 `validate_registry_batch(batch: dict[str, Any]) -> dict[str, Any]`，并返回其结果。该函数校验结构、字段及来源，返回带规范化 rows 的字典。调用方继续传播原有异常。主键与库内现有记录的冲突由后续 `plan_registry_batch` 检出。此前置关系及数据写入授权均保持原语义。

## 两套工作树的专项回归

开发目录在 `refactor/v2-architecture-repair` 上保有本地开发成果（HEAD `233d5a6c`）；发布树独立以审计基线为父版本。修改前两处目标源码在两树逐字节一致。Registry CLI 和其测试在两树已有版本差异，分别以本树修改前的行为为参照。

| pytest 范围 | 开发目录 | 独立发布树 |
|---|---:|---:|
| test_domain_cannot_import_cli_or_skill_implementations 与新增函数身份测试 | 2 通过 | 2 通过 |
| tests/test_registry_write.py | 17 通过 | 17 通过 |
| tests/test_registry_write_cli.py | 4 通过 | 发布基线无此文件 |
| tests/test_mkm_analysis.py（含派生批次、工单及端到端 CLI） | 29 通过 | 29 通过 |
| tests/test_multidentate_coverage.py | 30 通过 | 30 通过 |
| tests/test_mkm_single_point.py（含模拟单点登记、哈希及冲突路径） | 31 通过 | 31 通过 |
| **合计** | **113 通过，0 失败** | **109 通过，0 失败** |

两树均显式排除 `tests/test_mkm_single_point.py::test_live_closed_cycle`（各 1 项），以遵守本轮禁止科学计算的约束。常规登记路径通过模拟运行或已封存数据验证。三个改动的 Python 文件均在两树完成 py_compile 和 Ruff。未运行全仓测试。

修改前在两树单独运行 P1 边界测试，均在 `analysis.py` 对 Registry CLI 的导入处失败。修复后该测试在两树均通过。在每树的三个全新 Python 进程中分别导入领域函数、MKM 分析、MKM 登记，校验函数身份一致，`scripts.registry_write` 均未被加载。

## 可执行 CLI 兼容性

`pyproject.toml` 中保留 `registry-write = scripts.registry_write:main`。使用已安装的 `registry-write` 可执行入口，显式绑定被测源码根目录，在每树修改前后分别启动以下 8 个子进程。涉及数据库的探针均显式指定临时 SQLite。退出码及表中结果在四组观察中一致。

| 操作 | 退出码 | 核对内容 |
|---|---:|---|
| --help | 0 | 既有 plan/apply 参数和输出选项可用 |
| 缺必选参数 | 2 | argparse 报告缺少必需参数 |
| 有效批次 plan | 0 | 返回计划，7 行待插入 |
| 已批准的测试批次 apply | 0 | 在临时库插入 7 行 |
| 再次 plan | 0 | 7 行均为 unchanged |
| 非法 rows 执行 plan | 1 | ValueError，`registry batch rows must be a mapping` |
| 缺审批资料执行 apply | 1 | ValueError，`apply requires --plan, --approval and --confirm-sha256 from a reviewed plan` |
| 已有主键的内容冲突 | 1 | ValueError，消息含 `conflicts with existing` |

开发目录特有的 CLI 测试另核验了 ASCII 控制台、保存输出、浮点类型及确认哈希。开发目录和发布树继续各自使用原有输出格式。第一次修改前探针的 CLI 断言均完成，但 Windows 在回收临时库时遇到文件占用。改用独立子进程初始化临时库后，完整的修改前后探针均正常退出。

## 静态依赖与验收边界

沿用 Stage A.1 和 B5 测试的 maintained_trees、imported_modules，计算全部维护范围内 Python 导入（含函数内导入）。两个消费模块均直接依赖 registry_mutations，且均不存在到 registry_write 的传递路径。将新图的这两条边换回旧目标后，有序边列表的 SHA-256 与本轮现场修改前完全匹配。

| 工作树 | 节点 / 边（前后） | 强连通分量 | 有序边列表 SHA-256（前 → 后） |
|---|---|---|---|
| 开发 | 328 / 1150 | 相同的 4 组循环 | `909dbae4083b656e2d09d49f93dfe9ebcbc14e459a7fae5b989e13ba08ebf3cc` → `8dea41a96a58ad711730348f7adbc4d1d361914cef2e27aad1af5d3794d131bf` |
| 发布 | 287 / 1046 | 相同的 4 组循环 | `eba8ae30b339d0e6ce2c3b7fc7586fa6311ce492e1d3f19d5ef1dfbf532b57b1` → `b4f834b750afaba4691ce6686ae8c766d24d3ffa99040a0223dfdc12f99a5841` |

没有新增循环。Stage A.1 已记录的原生适配器及 DRC/灵敏度循环留在原有范围。本轮验证只涉及 P1、相关 MKM 和 Registry 调用；未执行科学计算，未修改生产数据库及原始科学证据，未进入后续重构。
