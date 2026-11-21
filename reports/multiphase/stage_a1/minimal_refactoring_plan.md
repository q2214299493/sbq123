# 最小实施顺序与验收条件

本表是 Stage A.1 的建议清单，须经研究者审核后再进入实施。必要性按目标区分。完整跨尺度产品的前置工作不应妨碍当前科学证据登记和局部分析。

| 项 | 当前问题 | 影响文件/模块 | 最小改动 | 收益 | 回归风险 | 必需验证 | 必要性 |
|---|---|---|---|---|---|---|---|
| P1 | 分析层依赖 Registry CLI | scripts/baseline_mkm/analysis.py、registration.py，scripts/registry_write.py、registry_mutations.py | 两处直接导入现有 registry_mutations.validate_registry_batch，保留 CLI 转出 | 消除两条逆向引用，范围最小 | 低，原入口猴子补丁或异常处理可能受影响 | test_b5_architecture_boundaries 的 CLI 边界、test_registry_write、test_registry_write_cli、MKM 分析/登记的有效与冲突批次 | 必要，建议首个独立变更 |
| P2 | 原生渲染回引装配器，装配器又从参数 CLI 取 read | scripts/native_model.py、baseline_mkm/native.py、surface_kmc/native.py、surface_kmc/lattice.py、kinetic_parameters/__main__.py | 下沉已共享的 token、integer、conditions 至低层原语，保留旧导入；读文件改用同语义已有读取入口或薄兼容层 | 装配单向依赖适配器 | 中，压力和标识符异常或输入字节可能变化 | 两树重算 SCC，test_native_model、test_native_advanced，逐字节比对两个引擎模型和旧清单，非法压力及多齿失败样例 | 必要，随后处理 |
| P3 | 三组研究流程与报告相互引用 | scripts/baseline_mkm/drc_pair.py、drc_report.py、drc_batch*.py、sensitivity_study.py、sensitivity_report.py | 一次拆一组，让编排调用报告，报告接收已检查事实；确需复用时仅提取纯读/核验函数 | 可离线复核，整图恢复无环 | 中，成对批准、停首错或重放判断可能受损 | test_mkm_drc、test_mkm_drc_batch、test_mkm_sensitivity，覆盖部分结果、零重试、预算和回执重用，按旧清单比对结果 | 必要，须独立于 P2 验收 |
| P4 | 视图与当前权威来源不同步，治理测试锁定旧状态 | docs/06_MODULE_MAP.md、scripts/generate_capability_readiness.py、reports/capability_readiness.json 和 .md、tests/test_b6_governance.py | 明确当前与历史投影语义；用固定历史样例测规则，当前视图按已核定的来源重生，保留历史快照身份 | 状态可信、可重复生成 | 中，误把模块 Active 当作研究项目已验证 | 连续生成两次比字节，对照两树不同 module_status；验证缺科学回执的 Active 模块仍不能执行 | 必要，独立治理变更 |
| P5 | 热化学和 NEB 的 OUTCAR 入口命名重叠 | scripts/thermochemistry/frequencies.py、scripts/ts_validation/analyze_vfa.py、scripts/neb_agent/utils_vasp.py 及原调用者 | 明确命名专用频谱读取入口，继续共享 frequency_header，核对旧导入兼容方式 | 科学量有唯一明确的解析职责 | 中，模态符号、索引、历史导入路径 | test_code_structure、test_thermochemistry 与原 TS 合同，含不完整频谱、已审虚频索引和 Grade A 绑定 | 必要 |
| P6 | 归一化、误差和物种源项没有跨引擎结果契约 | configs/kinetics、scripts/baseline_mkm/kinetic_analysis.py、scripts/surface_kmc、modules/reactor_simulation | 先定义一个可版本化的供率接口，复用网络 ID/计量/单位；接受原始基准，转换资料充分时再输出物理源项；不确定度可标未知 | 保住位点、体积及事件语义，使后续消费者可检验 | 高，位点对重复或 mol 与个数混淆 | 正逆/净速率、非单位计量、Pa/bar、跨库存、缺密度、面积/质量/体积等价、统计误差及旧版本读取 | 对跨尺度交接必要 |
| P7 | 基准数据提取依赖固定项目和反应名 | scripts/scientific_priority/benchmark.py、scripts/fe110_mlip_selection.py、configs/kinetics 与项目清单 | 仅在引入第二套数据时，把通用选择参数化；保留既有 Fe 工作流和基准入口，项目清单承载范围和映射 | 新体系可复用同一核心 | 中，迁移可能破坏既有标签或选错模型 | Fe 历史结果重放、任意元素/晶格和反应名称的第二配置、缺相/模型身份时仅阻断相关用途 | 对跨项目复现必要 |
| P8 | 已有原生案例和大网文献缺少统一复现设计 | reports/multiphase 历史回执、tests/fixtures/multiphase、Scientific Intake | 使用 A/B/C 清单和观测量，先离线重放 A；B 逐层检查，C 在来源和范围确定后再纳入 | 原生、物理与论文复现分级可追溯 | 中，套用合成容差或重复启动长作业 | A 独立解、B 位点守恒和种子统计、C 原始图表对照和有界枚举；缺项/后端不支持可部分验收 | 必要，C 的具体论文可选 |
| P9 | 有 Zacros 原生案例，尚无通用统计结果提供者 | scripts/surface_kmc、scripts/native_model.py、configs/kinetics/simulation_run.schema.json | 优先离线读取已归档轨迹并实现 P6 输出；通用有界执行和重启后置，复用已验收原生装配 | 获得可比较的随机源项 | 高，时钟、重启片段、相关样本和嵌入计数可能重复 | 分段与连续轨迹，零事件及净消耗、缺采样窗、种子区间、清单/重启哈希、局部相互作用 | 对通用 KMC 分析必要，新执行后置 |
| P10 | SPC 和 H7 现有接口部分覆盖单点 | scripts/scientific_priority/proposals.py、scripts/baseline_mkm/single_point.py、外部 SPC models.py/export.py 与 H7 | 用现有外部模型传递绑定问题和结果证据，协调层保留幂等标识和人工审阅 | 结果和下一研究问题可衔接 | 中，跨库副作用或误授予执行权限 | 临时工单库往返、重复回传、过期问题、缺失 SPC、结果审核与执行授权独立 | 对跨系统交接必要 |
| P11 | 有反应器运行壳和归一化工具，缺求解 | modules/reactor_simulation、simulation_run.schema.json 与 P6 供率方 | P6 验收后先做等温理想 CSTR，再做 PFR；有可靠焓、热容和换热证据后再扩能量方程 | 从本征速率得到有定义的转化率 | 高，空间基准、负流量、超出条件域、误差传播 | 零反应、一级解析解、元素闭合、入口/体积极限、温压越界、误差传播；非等温另验绝热守恒 | 对反应器目标必要，非等温可选 |
| P12 | 两个 TS 工具重复摘要格式检查 | scripts/ts_strategy_engine/dimer_gate_common.py、ml_neb_path.py | 待两个文件自然变更时共用同语义的小校验；保留大小写与错误行为 | 减少局部漂移 | 低，但在执行门链路 | 有效大小写、非字符串、错误长度与非十六进制，以及原门拒绝路径 | 可选，当前保留 |

P7 的位点检测入口还涉及 scripts/adsmind_lite/site_detection.py 与 configs/adsmind_lite 的 surfaces.yaml、site_rules.yaml。新增自动检测器时按项目选择已有或经审查的算法，同时复测未知晶面的显式位点与待审路径。

审核后的最短实施路径是先单独提交 P1，再验证 P2；P3 按强连通分量拆分。P4、P5 各自可单独验收。建立 P6 与 A 级基准后按实际项目推进 B、KMC、工单及反应器。当前没有启动 Stage A.2。
