# Phase 2A 真实诊断候选准备报告

状态：**AWAITING_REFERENCE_REVIEW**。已整理5个真实历史候选、1个保守反应组、47项公开标量证据；已批准参考和可评分案例均为0。没有生成模型回答或执行评分。

## 身份与最终产物

- code_root：C:\Users\86177\.codex\worktrees\phase1-diagnostic-cases\work
- evidence_root：C:\Users\86177\Desktop\work
- output_root：C:\Users\86177\.codex\visualizations\2026\09\29\01a0eb4e-842b-7f33-9d59-87ee752f88e9\sbq_agent_eval\phase2a_20260930_215046_6b0645bc
- 实际代码分支：codex/phase1-diagnostic-cases-20260929
- 实际 HEAD 与审查基线相同：b353ba4a00d0ee1d5b3f833dc71d0634f1a1e9cd
- 历史树 HEAD：376c597ad3e026da9539401748e5fbe5d145b87c，分支 refactor/v2-architecture-repair。
- 实际初始 cwd：C:\Users\86177\Desktop\work。
- Python 3.13.9，解释器 C:\Anaconda\python.exe；两项案例模块实际导入路径均在 code_root。
- 输出位于本会话明确列出的第二个可写 workspace_root。目录真实解析后，与两个只读来源根目录无包含关系。launch_context.json 使用实际观测值创建，未把历史候选当作事实。
- 实际创建时间及+08:00时区见 launch_context.json，最终核对时间见 final_checks.json。

最终交付以 **revision_02** 为准：
1. revision_02/intake.json：实际来源路径/字节哈希、快照身份/哈希、JSON Pointer或准确文本行、原生类型、分组、可见性限制及拟议参考。
2. revision_02/REVIEW_QUEUE.md：5行私有待审核项。
3. snapshots/manifest_v2.json、revision_02/draft_bundle：现有CLI构建的草稿，全部 provenance=incomplete、reference=null。
4. revision_02/answer_pack：实际仅含public.json、TASK.md、FORMAT.json，标明草稿，不进入正式答题。
5. 本报告、final_checks.json、revision_02/artifact_checks.json及命令日志。

初版包原样保留为superseded草稿。二轮检查发现c005只列两个数组元素不能证明总长度，因此新版本补入原始coverage_passed=false标量；未覆盖旧包、改来源或放宽评分规则。

## 候选与来源限制

| 案例 | 历史事件与原始观测 | 待审核事项 |
|---|---|---|
| c001 | GPU1347原始进程日志：GPU分配/选择后，包装脚本报“权限不够” | 日志无内嵌时间；runtime/confirmed仅针对执行权限故障，不凭此单独确认执行位；确认可见性和精确引用集合 |
| c002 | GPU1508普通ML-NEB保护记录：268步，单原子相邻位移1.2087282854302368 A，限值1.2 A | geometry/hypothesis的解释范围；保护触发不证明模型误差 |
| c003 | GPU1509真实受控Sella试用：预算3步，末力1.2851373562786916 eV/A，目标0.05 eV/A | 优化阶段预算诊断是否适配optimizer题型；不能把整体运行冒烟成功强行标成失败；不适配则排除 |
| c004 | Dimer9746548原有2026-09-08T11:03:28+08:00检查点：四项完成力评估达到NELM=200，仍RUN，无正常结束/精度标记 | 原始残差未在本轮重解析；scf/hypothesis或unknown及证据强度需审核 |
| c005 | GPU1324半强度释放第1步：O-H区间覆盖图像10/11、要求至少3个、coverage_passed=false | 当时阶段可见性、geometry标签、引用集合；不能由此直接判定模型误差 |

只审阅这5个候选事件，没有凑数或制造未知案例。统一保守归入g001：Fe(110)上C2HO*+H* -> C2H2O*的相关子路径、重试及试用；它们不构成5个独立反应。

六份入题原始来源均做了读前、读取字节、读后及结束时哈希核对。原始JSON按字节复制；日志派生JSON仅保存逐字UTF-8行，准确行号在intake中。公开scalar由Python原生值选取，未经JavaScript/PowerShell重序列化。新快照创建与历史观察时间分开记录，不使用mtime伪装科学时间。

历史可见性均为部分核实。后续文字审查不足以批准这些新的结构化标签和精确evidence_ids，5项proposed_reference全部pending，没有自行写approved，没有review.json或reviewed_bundle。后续诊断、接受结论和建议不进入公开题面，未改名绕过过滤。

## 执行命令与退出码

启动Git argv及完整输出见startup_observations.json；案例构建/审计完整argv、stdout、stderr、退出码见execution_log.json及revision_02/execution_log.json；最终Git argv见final_checks.json。只读检查和内联程序调用见inspection_commands.json；必要整理脚本为prepare_cases.py。

| 实际命令/操作 | 退出码 | 结果 |
|---|---:|---|
| python -B -m scripts.ts_strategy_engine.cli learning cases-build --help | 0 | 参数确认 |
| python -B -m scripts.ts_strategy_engine.cli learning cases-evaluate --help | 0 | 仅help，未评分 |
| python -B -c 导入并打印两项案例模块__file__ | 0 | 来自实际code_root |
| repo-state --help / repo-state audit --help | 0 | 仅已有安装入口帮助查询 |
| python -B -m scripts.state_manager --root <code_root> audit --phase start --format json | **1** | 1 error、16 warning、17 review_required |
| python -B <output_root>\prepare_cases.py | 0 | 初版提取、构建及现有加载端核对 |
| python -B -m scripts.ts_strategy_engine.cli learning cases-build --manifest <output_root>\snapshots\manifest.json --allowed-root <output_root>\snapshots --bundle <output_root>\draft_bundle | 0 | 初版5案例 |
| python -B - 内联修订程序 | 0 | 独占创建revision_02 |
| python -B -m scripts.ts_strategy_engine.cli learning cases-build --manifest <output_root>\snapshots\manifest_v2.json --allowed-root <output_root>\snapshots --bundle <output_root>\revision_02\draft_bundle | 0 | 最终5案例、47标量 |
| python -B - 内联最终核验程序 | 0 | 原生类型、哈希、bundle、公开包及Git状态核验 |
| git -C <code_root> diff --exit-code -- <11个启动记录文件> | 0 | 相关文件无修改 |
| 两树git rev-parse HEAD / branch --show-current / status --porcelain=v1 | 0 | 前后HEAD、分支与工作区状态一致 |

审计错误为docs/06_MODULE_MAP.md的managed_projection_drift；16个警告为额外工作树所有权审查等已有发现。已记录，未执行sync/apply或修复；此状态文档发现不能当作科学失败，也不使本轮案例接口不可用。

另有两次工具编排问题：变量未定义、Windows命令载荷超过CreateProcess长度限制，均在Shell启动前失败，没有命令退出码或该次写入；分别修正变量和缩短载荷后继续。未隐瞒为成功命令。

## 范围审计：内置清单，同轮定点检查

1. 来源：6份真实原始材料可定位，字节哈希前后匹配，原始/派生身份分明。
2. 输入：逐题核对question/ID/pointer/value，未导出后续diagnosis/scientific_verdict/review；c005的上下文缺口已在新包修复。关键词检查不证明语义无泄漏。
3. 参考：全部待审核，评分reference=null；没有冒充用户或独立审核。c003题型、c004证据强度是具体审核问题。
4. 协议：沿用现有learning.yaml分类与路由。现有_load_bundle通过；47项标量与来源的规范JSON身份及类型一致，未改科学阈值。
5. 分组：1反应组、5事件，没有按成绩挑题或冒充独立反应。
6. 隔离：公开包实际仅3个允许文件，不含private、审核队列、intake或参考路径。原始报错中的执行文件路径是观测。目录分离不证明读取隔离，尚未验证盲测。
7. 范围：11个启动记录相关文件的前后字节哈希一致，代码树干净；历史树752个既有Git状态条目逐字一致，6份入题来源哈希一致。检查范围不是全盘零变更证明，不认领或回滚外部活动。
8. 结论：没有正式answers、模型成绩、幻觉率改善、TS成功率、机时节省或泛化声明。

本轮未运行pytest/Ruff/full CI，因未修改生产代码；只运行必要help、构建及产物核对。没有评分、模型API、SSH/SCP、调度、生产数据库读写/迁移、计算或训练，没有repo-state sync、状态事件apply、commit/push/merge、reset/切分支或科学接受标准修改。全部新产物局限于output_root，人工创建文件采用独占方式，已有bundle路径未复用。

## 下一步交接

审核revision_02/REVIEW_QUEUE.md中的5项问题，逐题批准或排除并确认精确证据集合。获批后在新版本创建独立审核来源、构建reviewed_bundle，不原地改写草稿。

正式答题需要只挂载审核后公开包的独立环境，或经验证的私有路径拒读配置；本轮未安装环境或更改ACL。未验证隔离只能称非盲接口试运行。本整理会话已见私有材料，不能充当被评测者。后续模型标识、提示/技能哈希、原始首份输出、异常和耗时需实际记录，未知成本不得编造。

后续评分命令（本轮未执行）：
python -B -m scripts.ts_strategy_engine.cli learning cases-evaluate --bundle <新建reviewed_bundle绝对路径> --answers <独立原始回答绝对路径> --report <新的评分报告绝对路径>

最终public_sha256（规范JSON身份，不是文件字节哈希）：
46effdb86474a049ba273155e30d7eb430bb889cfee851e0286eff796da51afd
