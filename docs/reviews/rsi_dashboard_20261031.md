# 本地 RSI 看板展示接入验收 — 2026-10-31

本地静态页面、项目运行选择和四类自动刷新已完成离线接入验收；四次已有
真实运行均从本机绑定原件回填。科研收益仍未建立。浏览器工具拒绝 file://，
真实桌面/320px 视觉验收未完成，不能将 DOM 测试称为浏览器视觉通过。

## 代码与入口

基线为 `cdc75352228c5bb9deeb9cc9f2914d4f4bf32010`，本次独立分支为
`codex/rsi-usage-dashboard-20261030`。不合并 main，不覆盖旧科研助手入口、
日常 work 的用户修改或原始运行记录。附件日期为 10 月 30 日；本次收尾
发生于上海时间 10 月 31 日，保留实际记录时间。

- `dashboard_sources.py` / `dashboard_data.py`：有大小/数量边界的来源核验、
  逐来源错误、运行快照与当前策略状态、明确的未知值。
- `dashboard_comparison.py`：普通任务、接续、已登记真实配对；只并列实际
  回答及确定性文本差异。存在配对记录不自动认定收益。
- `dashboard_render.py` / `dashboard_assets/`：独立 HTML、内联 CSS/JS、
  三页签和运行选择器、文本转义、无外部 CDN、禁止页面网络请求。
- `dashboard_registry.py`：按回执 SHA 登记；派生目录独立于策略状态，
  写入原子化、重建串行化；重复名称和变化哈希不冒充同一运行。
- `usage_sources.py`：提取复用原严格使用记录与反馈校验。原 usage 命令
  遇坏来源仍拒绝；看板单独展示坏来源，保留其他可核验记录。
- CLI 在 run/resume 原件落盘、反馈保存及策略 review 成功后自动刷新。
  stdout JSON/科研返回值不变，展示路径/错误另发 stderr；可用
  `--no-dashboard` 禁用。展示失败不改科研状态，不重试模型。

现有旧 wrapper 不认识 dashboard。本次新增入口明确绑定新源码，默认仍
复用旧 `daily_profile.json` 的 accepted-only 设置；trial 不因看板晋升。
新的正常 run/resume 应从本次 `use_research.py` 或本分支模块入口进入，
才会使用新增自动钩子。没有修改旧 wrapper 的路由。

## 页面与具体命令

总入口：
`C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_runtime_policy_20261030\policy_store\dashboard\index.html`

相关试用单次页：
`C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_runtime_policy_20261030\runs\relevant_candidate\views\rsi_view.html`

推荐在 PowerShell 中运行以下 Python 打开入口；不需要改变 PowerShell 的
脚本执行策略。它只生成/打开 dashboard，不执行 run/resume 或加载认证：

```powershell
& 'C:\Anaconda\python.exe' 'C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_usage_dashboard_20261030\open_rsi_dashboard.py'
```

加 `--no-open` 只刷新。本次已实际执行此模式并返回成功。

PowerShell 入口保留在：
`C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_usage_dashboard_20261030\Open-RSIDashboard.ps1`。
它支持 `-NoOpen`、`-RunDirectory` 和 `-OutputDirectory`。本机 Codex
自带 PowerShell 7 的实际路径已通过 Get-Command 核实，`-NoOpen` 执行成功。
系统 Windows PowerShell 5.1 禁止执行脚本，实际尝试被拒绝；没有绕过或
修改执行策略。因此推荐上面的 Python 命令，不假定系统安装了标准路径下的 pwsh。

新科研助手入口：
`C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_usage_dashboard_20261030\use_research.py`。
支持 run/resume/feedback/policies/usage/dashboard 等原有及新增命令。
无 profile 时，run/resume 复用已核实的非秘密 daily_profile 路径；
dashboard/open 入口不读取该认证配置。

## 已有真实记录展示

实际读取旧任务 runs 下的四次运行和绑定的 paired_review.json，没有重跑
真实模型、A/B 或科学计算。四份回执/结果/应用/初始输入均按原哈希核验。
普通运行、resume 接续和配对三种展示状态分别保留，接续不冒充对照。

| 项目 | 本次实际结果 |
|---|---|
| 登记真实运行 | 4 次，相关/不相关 × 试用/基线 |
| 原件/策略状态检查 | 2,047 份原文件哈希未变，包含策略 state.json |
| 原初策略 | check_registered_material v1，external_proposal，仍为 trial |
| 新完整候选 | 0，不强行生成 |
| 观察 | 5，保留原提出记录 |
| 运行时 token/秒数 | 从原回执读取；不换算费用，不当成人工耗时 |
| 本任务新增真实模型调用/科学作业 | 0 |
| 用户确认帮助/对照收益 | 仍未知/未建立 |

页面明确分列“策略已提供、观察到对应行为、用户报告帮助、对照支持收益”。
相关试用的动作/输出有限对应可展示；不能因此声称避免了计算或因果增益。
五次原宿主工具错误仍在动作列表中，不因展示来源核验成功而掩盖。

## 反馈与异常

表单只导出反馈请求，明确显示“尚未写入”。用户选择实际 option IDs、
动作和输出引用，确认帮助原因；准备/评阅/纠正时间各自可空。下载后仍经
原 feedback 命令保存，未建立浏览器写策略库服务。

测试夹具验证了：后补反馈自动刷新，原输入/结果/应用/回执未变；已保存
但索引待恢复的反馈仍可见；策略 review 更新当前状态而保留旧 trial；
坏反馈/坏配对/坏登记隔离、来源哈希变化失效、旧版未知成本不变成零；
并发登记不丢运行；禁用显示生效；展示异常不重试模型且 stdout 兼容。
所有测试反馈均在独立临时夹具中，未伪装为真实用户反馈。

## 验证结果与限度

语法、导入、限定 Ruff 和 JavaScript 语法检查通过。六个相关测试文件
95 项中 93 通过、2 跳过；跳过项需要 RSI_TEST_SPC_ROOT 的可选 SPC owner
环境。随后数量边界收紧另做看板定向回归，结果见本地 JUnit。

DOM-only 检查通过页签、四项运行选择、实际配对成本、trial 状态、候选
计数、反馈导出而不保存、未知与零的区分、脚本/HTML 转义。临时 jsdom
只用于测试，不是运行页面的依赖；未启用外部资源加载。

首次较宽回归中 CSS 格式断言失败，修正后回归通过。另一个较宽打包检查
`test_workflow_scripts_are_packaged_without_runtime_path_injection` 因既有
spc_adapter.py 的 sys.path.insert 失败；该源文件与 cdc75352 完全一致，
本任务未修复，也未计为通过。新增三份静态资源已列入现有发布资源清单和
MANIFEST，未声称已构建/验收安装分发包。

浏览器工具实际拒绝 file://，理由为只允许 http/https。未尝试绕过或改用
其他浏览器表面间接打开。因此 Windows 浏览器真实视觉、实际打开动作、
桌面及 320px 布局仍未完成验收；CSS 响应规则与 DOM 单测不代替视觉检查。

本地证据根目录：
`C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_usage_dashboard_20261030`。
包含 originals_before.json、original_integrity.json、各阶段 JUnit、DOM
检查记录、入口和生成脚本；原运行目录及凭据不随源码推送。

## 判定与下一步

展示/自动接入：通过上述离线及钩子测试，真实浏览器视觉未验。
科研收益：未建立；没有因新增看板而采纳策略、增加自主改进数量或补填收益。

下一步在本机通过推荐命令打开页面，核对真实视觉和 320px 布局。
这一步不需要重跑科研任务或模型。

结束时实际执行 owning CLI 的 `sync --safe-only`，退出 **2**：
`ERROR: state history source changed before proposal generation`。
没有返回 proposal ID 或选项；没有代替用户选择，也没有修复无关状态历史。
该既有阻断单独保留，不作为展示或科研收益通过项。
