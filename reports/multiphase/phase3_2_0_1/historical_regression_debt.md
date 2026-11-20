# Historical Regression Debt

复现基线为 `8f7c77f5b96a7035d5ca839423c48bb58f575255`。下列五个 pytest node ID 在开发目录、独立发布工作树和无本轮改动的基线检出中均失败。三个环境使用的三个测试源文件逐字节相同。开发目录有独立历史和本地修改，因此个别断言展示的第一条循环路径或模块状态不同。

| pytest node ID | 实际失败原因 | 单独修复时的核对 |
| --- | --- | --- |
| `tests/test_b5_architecture_boundaries.py::test_domain_cannot_import_cli_or_skill_implementations` | `scripts/baseline_mkm/analysis.py` 从被架构规则归为 CLI 的 `scripts.registry_write` 导入校验函数。 | 确认校验函数的领域归属，使领域模块与 CLI 共用同一实现，再重跑依赖边界检查。 |
| `tests/test_b5_architecture_boundaries.py::test_maintained_runtime_import_graph_is_acyclic` | `scripts.native_model` 与后端适配器存在静态依赖环。遍历顺序决定首先报告 MKM 或 KMC 路径。 | 梳理适配器依赖的通用原语，让共享原语可独立导入，并验证两个后端既有入口。 |
| `tests/test_b6_governance.py::test_readiness_generation_is_deterministic_and_matches_checked_in_view` | 连续两次生成相同，但生成的就绪视图与签入的报告字节不同。 | 核对来源哈希及受管模块状态，经既有评审流程刷新衍生视图。 |
| `tests/test_b6_governance.py::test_tests_and_status_do_not_invent_maturity_or_science` | 测试预期热化学为 `Blocked`，实际视图为 `Active`。开发目录另有 `kinetic_data` 状态差异。 | 由模块负责人核对当期状态与历史测试夹具的时间范围，分别验证模块进度与科学资格。 |
| `tests/test_code_structure.py::test_scientific_parsing_and_contract_validation_have_single_owners` | 扫描还找到了 `scripts/thermochemistry/frequencies.py` 的 `parse_outcar`，与预期所有者清单不符。 | 先确认频率解析与其他 OUTCAR 解析的科学职责和兼容接口，再决定复用实现或明确专属名称。 |

## 复现证据

下列 gzip 文件解压后为完整控制台日志，含运行目录、HEAD、pytest 命令、五个完整测试名称、断言及退出汇总。三次均为退出码 1。哈希对应解压后的原始字节。

| 环境 | 完整日志 | SHA-256 |
| --- | --- | --- |
| 开发目录，HEAD `233d5a6c`，保留本地修改 | [development-debt.txt.gz](regression/development-debt.txt.gz) | `7c3c2a4ca580fd575c361dbb5c8a50fa453ec1b018a80609411d6fd34c08a663` |
| 独立发布工作树，含本轮变更 | [release-debt.txt.gz](regression/release-debt.txt.gz) | `0054d448c0f156ed585ef637fcf3cf4bddc111eace47e62bfd79fc8509316f65` |
| 未修改的 `8f7c77f5` | [baseline-debt.txt.gz](regression/baseline-debt.txt.gz) | `5285b8184d655bb7771e7f06c6abadde7330536e232c55f8263a0ec3da93e196` |

首次在长期使用的发布目录全测另触发 `tests/test_repository_contracts.py::test_root_contains_no_executable_or_download_clutter`。报错列出未跟踪的根目录 `build/`，其创建日期为 2026-11-19，早于本次变更。同一根目录用例在干净基线和包含本轮变更的干净检出均通过。原有 `build/` 保留在现场。[测试报告](test_report.md)
