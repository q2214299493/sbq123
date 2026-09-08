# Phase 2B 独立差异审查

## 1. 审查边界与方法

- 审查日期：2026-07-27
- 分支：`codex/ts-workflow-cleanup-20260722`
- 审查对象：Phase 2B “NEB 路径质量模块职责整理”
- 审查依据：当前文件内容、Git 工作区状态、Phase 2B 修改前行为快照、Phase 2A 源码哈希基线和当前哈希；未把实施报告当作代码事实来源。
- 重要限制：`path_quality_control.py`、`path_quality_cli.py`、`pilot_validation.py` 及对应旧测试在当前 Git 仓库中仍是未跟踪文件，因此普通 `git diff` 无法恢复这些文件修改前的逐行内容。对这些文件的审查采用修改前 SHA-256、字节数、行数、行为快照与当前源码交叉验证。旧快照只保存哈希而未保存完整旧文件，所以无法独立重算其精确 gross additions/deletions；净行数和所有当前内容可以独立核对。

## 2. 实际文件状态

| 文件 | Git 状态 | 修改前/当前行数 | 修改前/当前 SHA-256 | 审查结论 |
|---|---:|---:|---|---|
| `scripts/neb_agent/path_quality_control.py` | 未跟踪、Phase 2B 未改 | 330 / 330 | 当前 `12b277…b523`，与 Phase 2A 基线一致 | 科学 evaluator 未改 |
| `scripts/neb_agent/path_quality_service.py` | 新增未跟踪 | 0 / 147 | 当前 `0f306f…af20` | 授权范围内的新共享应用服务 |
| `scripts/neb_agent/path_quality_cli.py` | 未跟踪、已改 | 96 / 70 | `0063f77…b09de8` / `9177d24…c15e9` | 薄化 26 行 |
| `scripts/neb_agent/pilot_validation.py` | 未跟踪、已改 | 192 / 202 | `db0d00…2e90d` / `8c280c…969d` | 仅增加共享适配入口及导入 |
| `scripts/ts_strategy_engine/workflow.py` | 已跟踪、已改 | 316 / 294 | `bff5a7…9bdade` / `014397…f1a51` | 删除重复配置合并和评价编排 |
| `tests/test_neb_path_quality_entrypoints.py` | 新增未跟踪，验收补测 | 0 / 600 | 当前 `8ea4ed…f44a` | 五入口、异常边界及碰撞职责边界回归 |
| `tests/test_neb_path_quality_control.py` | 未跟踪、Phase 2B 未改 | 不变 | 与旧基线一致 | 原 evaluator 测试未放宽 |
| `tests/test_neb_pilot_validation.py` | 未跟踪、Phase 2B 未改 | 不变 | 与旧基线一致 | 原 pilot 测试未放宽 |

Phase 2B 生产源码由 934 行变为 1043 行，净增加 109 行；原有四个生产文件合计减少 38 行，新 service 为 147 行。实施完成时入口回归测试为 552 行，本次独立验收按允许范围补充 48 行碰撞职责边界测试，当前为 600 行；五份 Phase 2B 实施/基线材料合计 433 行。因此当前可独立确认的净增加为 1142 行。`PHASE_2B_CHANGESET_MANIFEST.md` 没有声明精确 additions/deletions，只保存实施完成时的文件、哈希、字节数和行数；其生产源码记录仍与当前一致，入口测试的单一差异由本次验收补测解释并在 `PHASE_2B_VERIFIED_CHANGESET.md` 追加绑定。用户所述“约 1186 行”不能在未保存旧文件全文的情况下还原为精确 gross diff，但不存在未解释差异。

## 3. 逐文件审查

### 3.1 `path_quality_control.py`

1. 修改内容：Phase 2B 未修改。
2. 修改原因：不适用；保持唯一科学 evaluator。
3. 授权范围：未触碰，符合冻结要求。
4. 公共 API：`quality_source_paths`、`collect_evidence`、`evaluate_quality` 保持可导入。
5. 导入路径：`scripts.neb_agent.path_quality_control` 保持不变。
6. 副作用：collector 读取计算文件；evaluator 只构造结果，不写文件、不提交任务。
7. 异常类型：未改变。
8. 返回结构：未改变。
9. 字段或排序：状态、reason code、阈值、字段和 reason 顺序未改变。
10. 未记录变化：无。

### 3.2 `path_quality_service.py`

1. 修改内容：新增 `PathQualityRequest`、`load_path_quality_thresholds`、`build_path_quality_report`、`read_configured_nelm` 及三个私有配置辅助函数。
2. 修改原因：集中原 CLI/workflow 重复的配置加载、证据采集、evaluator 调用和兼容报告构造。
3. 授权范围：属于 Phase 2B 明确授权的共享调用层。
4. 公共 API：新增 API，不删除旧 API。公开签名为：
   - `load_path_quality_thresholds(quality_path: Path, geometry_path: Path) -> dict[str, Any]`
   - `build_path_quality_report(request: PathQualityRequest) -> dict[str, Any]`
   - `read_configured_nelm(path: Path) -> int`
5. 导入路径：新增 `scripts.neb_agent.path_quality_service`；旧路径不变。
6. 副作用：读取 YAML、INCAR、monitor JSON 和路径输入；不写 JSON、不调用 scheduler/submission、不退出进程。
7. 异常类型：文件和 evaluator 异常继续上抛；非法配置在采集前明确转为 `ValueError`。这是非科学错误边界的有意收紧，不是成功降级。
8. 返回结构：以 evaluator 完整结果为基础，仅补入原有 `schema_version`、`evaluator_version`、`producer`、`kind`、`source_manifest`。
9. 字段或排序：完整入口比较未发现科学字段或列表顺序变化。
10. 未记录变化：新增 pilot 顶层 import 会把 service 及其 collector 依赖带入 pilot 的模块导入链；项目环境可正常导入，但这是实施材料没有单独强调的低风险依赖边。

### 3.3 `path_quality_cli.py`

1. 修改内容：删除本地配置合并、证据采集、评价和报告组装；改为构造 request、调用 service、通过 `artifact_io.write_json` 写入。
2. 修改原因：消除第二套评价编排。
3. 授权范围：属于 standalone CLI 适配。
4. 公共 API：`main() -> int` 和 `_incar_nelm(path: Path) -> int` 兼容入口保留。
5. 导入路径：`python -m scripts.neb_agent.path_quality_cli` 仍有效。
6. 副作用：仍只读取输入、写一个 JSON、打印一行状态或错误；无计算/提交副作用。
7. 异常类型：模块函数最外层仅将 `KeyError`、`OSError`、`ValueError` 转为退出码 1；argparse 语法错误仍为 2。
8. 返回结构：成功 JSON 与基线相同。
9. 字段或排序：完整字典及顶层键顺序测试一致。
10. 未记录变化：非法配置的 stderr 更明确，但没有转成成功 JSON，也未弱化退出码。

### 3.4 `pilot_validation.py`

1. 修改内容：新增 service 导入和 `build_pilot_path_quality_result(request)` 显式适配函数；原 pilot 构造、验证和 CLI 主体未改。
2. 修改原因：让 pilot 可显式使用共享 path-quality 路径，同时保留 pilot 独有验收。
3. 授权范围：是 Phase 2A 24/25 差异中唯一授权文件。
4. 公共 API：仅新增函数；`build_pilot_result`、`validate_pilot_result`、`main` 保持可调用且签名不变。
5. 导入路径：原模块路径不变。
6. 副作用：新适配入口继承 service 的只读采集；未增加真实计算、SSH、LSF 或提交。
7. 异常类型：适配函数不捕获、不吞没 service 异常。
8. 返回结构：原 pilot 结果结构未改变；新函数返回完整 path-quality 报告。
9. 字段或排序：pilot 原有字段、`passed` 和磁性规则未改；path-quality reason 不过滤、不重排。
10. 未记录变化：存在前述顶层依赖边；没有发现行为回归。

### 3.5 `workflow.py`

1. 修改内容：`_path_quality` 改为调用共享 service；删除本地 YAML 合并、collector/evaluator 调用和报告构造。
2. 修改原因：移除 unified workflow 中重复的评价编排。
3. 授权范围：属于 Phase 2B workflow 适配。
4. 公共 API：`AnalyzeRequest`、`analyze_search`、`_path_quality` 的签名和 workflow CLI 入口未变。
5. 导入路径：原 `scripts.ts_strategy_engine.workflow` 不变。
6. 副作用：仍在同一流程位置写入一个 `neb_path_quality.json`；继续使用 `artifact_io.write_json`。
7. 异常类型：service/写入异常继续传播，workflow 未吞没。
8. 返回结构：无输出时 `{}`、缺 primary 时的三字段 `INVALID_ENDPOINTS`、正常报告均保持。
9. 字段或排序：execution gate 消费的 `schema_version`、`evaluator_version`、`producer`、`kind`、`source_manifest` 和科学字段不变。
10. 未记录变化：无。

### 3.6 相关测试

1. 修改内容：实施阶段新增 552 行入口回归；验收阶段补充 48 行原子过近/碰撞职责边界回归，当前 600 行。原 evaluator/pilot 测试未删除、未改写。
2. 修改原因：覆盖五入口、旧签名、配置错误、缺失输入、evaluator 异常、写入失败和 workflow 特例。
3. 授权范围：属于必要回归测试。
4. 公共 API/导入：测试直接导入真实旧入口及新 service。
5. 副作用：只使用 `tmp_path` 和 monkeypatch，不连接远端、不提交任务。
6. 异常与返回：断言失败退出、无成功 artifact、完整结构和 reason 顺序。
7. 断言强度：没有删除或放宽原断言；新增测试使用全字段深比较。
8. monkeypatch：patch 的是 service 实际使用的 `collect_evidence` 和 CLI 实际使用的 `write_json`，不是旁路副本。

## 4. 变更范围结论

- 生产代码净增加 109 行的主要原因是新增 147 行共享 service，同时原 CLI/workflow 合计净减少 48 行、pilot 增加 10 行。
- 新增体量主要来自测试和审查材料，不是以更大的生产实现替代少量重复代码。
- 未发现 Phase 2B 对科学阈值、reason code、状态优先级、JSON Schema、execution gate、scheduler、submission、SSH、LSF、SQL 或 migration 的修改。
- 未发现实施报告之外的科学或公共行为变化。事实性补充只有：非法配置更早以 `ValueError` 失败，以及 pilot 新增一条顶层依赖边。
