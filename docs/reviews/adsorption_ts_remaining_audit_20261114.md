# 吸附能与过渡态流程剩余问题复核（2026-11-14）

复核对象是当前 `C:/Users/86177/Desktop/work` 的实际代码与配置，以及相关全局 skill。
这是软件与规则一致性复核；没有查询远端作业、运行模型、重新分析真实计算结果或接受新结果。
原有科研任务、原始数据、执行门禁及三种非等价初始构型要求保留。

## 本次已修复

1. 规划器从 `configs/dimer_gate.yaml` 的 `eligibility.parent_methods` 读取可用候选方法；删除五个反应族重复的方法白名单。旧模板保留优先顺序，但按现行策略补齐或移除候选方法，不修改历史模板。当前工作区包含 `gpu_ml_neb_reviewed_path`；候选列表本身不构成执行授权。
2. 将普通 NEB 与 CI-NEB 的连通性配置拆开。普通 NEB 仍要求原有连通性证据；CI-NEB 的下坡检查按已批准协议作为可选诊断，仍需当前收敛的真实 climbing-image 来源、端点约束路径、匹配的频率结构与已接受反应模式。同步配置加载器、生产结果契约和测试。
3. 将吸附复核的收敛解析、末步 TOTEN/力提取及原始字节 SHA256 合并到同一次 OUTCAR 流式读取。公共 `parse_final_outcar` 保持原有输出字段，单独调用只读一遍。缓存命中仍须检查真实文件，缓存与输出均在最终证据核验后写出。
4. 为发布分支补入当前工作区已有的 CI-NEB 验收实现及注册层的按来源检查，避免“配置放宽、实现仍旧”的不完整迁移；不改变已批准科学规则。
5. 发布版 OUTCAR 解析同步当前工作区的 SCF 边界修正：编号循环内先出现 sigma0 能量、后出现 EDIFF 标志时仍归属同一电子循环。新增两项回归先复现旧版失败，再验证修正；没有改动收敛阈值。发布分支派生能力报告仅刷新受本次修改影响的源码哈希。

旧冷缓存调用链静态可确认七次 OUTCAR 全量遍历（四次哈希、三次解析）；未将其作为实测耗时结果。
新增合成样本集成测试实测：冷缓存两次全量读取（解析/哈希一次、最终校验一次），热缓存一次，输出记录一致。
没有跳过最终校验来追求单遍冷读。

## 剩余问题（按风险排序，本次未扩展修复）

| 风险 | 问题与证据 | 影响与边界 |
|---|---|---|
| P1 | 全局 skill 规则仍滞后：`C:/Users/86177/.codex/skills/catalysis-data-retrieval/SKILL.md:19` 未提供仓库已批准的 `NO_WHITELIST_MATCH` 后受控权威期刊回退；`imaginary-freq-correction/SKILL.md:35` 要求阈值未设置一律 `Ungraded`，遗漏已批准的显式审核单虚频分支。对照 `configs/skill_routing.yaml`、`configs/adsmind_lite/evidence_gate.yaml`、`docs/10_TS_VALIDATION_PROTOCOL.md`。 | 会使合法资料检索或已审核 TS 流程被额外拦截。应同步全局路由文本到仓库现行协议，不能为此删掉审核或编造阈值。 |
| P1（发布一致性） | 当前工作区已有 `scripts/ts_strategy_engine/gpu_dimer_parent.py`、`scripts/prepare_gpu_path_dimer.py` 与四项 DIMER parent 方法；`sbq123/main` 基线 `2e1e21cc` 缺少该运行实现，只有三项方法。本次分支保持部署策略适配，未把整套既有 GPU 实现夹带进小修。 | 当前工作区规划器已列出 reviewed GPU path；仅检出发布分支不能据此宣称直接 GPU-path DIMER 功能已部署。完整发布该既有功能需独立核对依赖、门禁和测试。 |
| P2 | `scripts/adsmind_lite/candidate_generation.py:150` 的通用生成器只实现配置指定的单原子锚定；`configs/adsmind_lite/prescreen_rules.yaml:78` 的 CHO C/O 双中心模式需要经审核的多锚定结构模板。 | 是明确的能力缺口，会停止部分双齿构型生成。当前拒绝行为有必要，不能删除检查后用单锚定几何冒充双齿模式。不能据此宣布三种模式覆盖完成。 |
| P2 | 全局 `neb-transition-state/SKILL.md:32`、`neb-analysis-workflow/SKILL.md:35` 及仓库 `skills/catalysis-data-retrieval/SKILL.md:48` 仍使用强制 matched/final statics 表述；现行方法协议第82行允许兼容收敛的 SIGMA0.20 最终 TOTEN，不要求额外单点。 | 可能引入不必要的静态计算准备或人为阻塞。实际能量兼容性、收敛性、注册与执行授权仍须保留。 |
| P3 | `scripts/ts_strategy_engine/dimer_analysis.py:294` 仍输出 `requires_frequency_and_connectivity_validation=True`；已批准 DIMER 连通性是可选诊断。搜索 `scripts/`、`tests/` 未发现该字段的读取者。 | 当前发现的是误导性输出字段，未发现它能授权执行或绕过验收。应单独兼容性清理，不能据此重算历史结果。 |

未把白名单优先、三种化学合理且非等价初始模式、原始构型覆盖、兼容能量约定、Grade A 和哈希绑定执行门当作“不合理限制”；这些均有当前用户或协议依据。
本次没有证据证明旧 long-bridge 算法或审核模板未消费问题在当前已更新 builder 路由中再次出现。

## 验证

- 当前工作区：232 项相关回归通过，后端契约 9 项重跑通过；新增 SCF 边界测试在发布版先复现失败，再修正。
- 发布分支：171 项定向回归通过；修正后 124 项解析/缓存/收敛回归、51 项策略/CI-NEB/缓存补充回归通过。语法、导入、`ruff check scripts modules tests` 和 `git diff --check` 通过。
- 扩大回归中发现的发布版旧注册、模板契约及派生报告哈希差异均已补齐；不把失败、中断或源文件变更期间的结果计作一次完整全套通过。
- `repo-state sync --safe-only` 没有应用变更、没有待处理审批提案；结束审计 0 个错误。任务快照及投影清单哈希与开始时一致；错误日志同期发生变化，本次未请求编辑或覆盖它。
- 原始字节哈希覆盖 LF、CRLF、CR 与非法 UTF-8；检查末步未完成/重新启动不能继承旧收敛标志、缺失能量或力拒绝、文件变动阻止缓存与输出、旧缓存与科学接受状态隔离。
- 新测试全部使用合成 VASP 输出；不产生科学结果或计算成本。
- 未验证真实远程环境的性能加速比例、真实历史计算的科学结论，或尚未迁移的 GPU 运行分支发布效果。
