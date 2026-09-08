# 待退役代码

本次没有删除或移动以下内容。它们仍可能被 CLI、历史脚本或外部环境调用。

| 内容 | 当前用途 | 退役条件 | 建议 |
|---|---|---|---|
| `scripts/adsmind_lite/core.py` | 旧导入路径的兼容门面 | 仓库和外部调用均不再从 `core` 导入 | 新代码直接导入职责模块；保留一轮明确弃用期 |
| `scripts/aqcat25_ts_active_learning.py` | 旧 active-learning 模块入口 | MZ73 作业、文档和用户脚本全部迁到统一 CLI | 继续转发到 `scripts.ts_strategy_engine.cli active-learning`，记录调用后再删除 |
| `modules/memory_migration/` | 已完成迁移的历史和交接材料 | 确认没有恢复/审计流程依赖 | 保留为 handoff-only 或迁入 `archive/`，不参与当前状态推断 |
| `AGENTS.md.bak.*` | 本地规则备份 | 用户确认当前 `AGENTS.md` 已覆盖所需内容 | 移入 `archive/` 或删除；本次未操作 |
| `modules.ts_endpoint_*`、`modules.structure_purpose_manager` | 第三批迁移后的旧导入路径 | 仓库外调用方完成 `scripts.ts_endpoint` 迁移并经过一个明确弃用周期 | 保持薄兼容别名；新代码只使用 canonical package |
| `scripts.neb_agent.path_quality_cli._incar_nelm` | 历史私有名称兼容入口 | 外部调用证据和兼容基线均确认不再需要 | 当前静态引用虽为空，但兼容报告明确要求保留，不按死代码删除 |

## 调用证据要求

删除前必须同时确认：

1. `rg` 静态引用为空；
2. 配置、插件、Shell、LSF/Slurm 和远程作业脚本未调用；
3. CLI 帮助和文档不再公开旧入口；
4. 至少一个发布或实际工作周期未观测到调用；
5. 回归测试和最小运行 smoke 通过。

无法满足以上条件时，保持兼容层并标记为待确认，不用“代码看起来旧”作为
删除依据。

## 2026-08-19 第五批复核

- 仓库静态扫描没有发现满足全部删除条件的生产代码。
- `scripts/aqcat25_ts_active_learning.py` 仍由执行后端配置显式引用。
- AdsMind `core.py` 仍被回归测试和公开文档引用。
- `_incar_nelm` 没有仓库内调用，但属于已有兼容基线，不能仅凭静态零引用删除。
- `modules/memory_migration/` 和本地 `AGENTS.md.bak.*` 缺少删除所需的人工确认。
- 本批只移除 `neb` extra 对未使用 `matplotlib` 的依赖，并把该依赖归入
  实际渲染脚本使用的 `visualization` extra；没有删除历史或计算文件。
