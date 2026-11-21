# 模块职责与实际可用范围

路径相对仓库根目录。表中“有实现”指可以定位到代码或契约。原生运行的证据另列于 [原生回执核查](native_evidence.json)。

| 所有者或边界 | 取证入口 | 输入 → 输出 | 验证及范围 |
|---|---|---|---|
| 吸附与 DFT | modules/adsorption_workflow、scripts/adsorption、modules/adsmind_lite、modules/catalysis_data_retrieval | 来源、晶面及结合方式 → 候选构型、计算后结构和能量 | 位点标签只支持候选。结构收敛、重排及兼容能量分支需要各自证据。 |
| MLIP 训练和验证 | scripts/aqcat25_ts_training_data.py、scripts/aqcat25_ts_checkpoint_validation.py、scripts/mlip_same_structure_benchmark.py、scripts/fe110_mlip_selection.py | 带标注构型与训练配置 → 数据库、模型检查和同构型评估 | 模型、训练集、留出集和适用域各自绑定。预测鞍点须回到 TS 验证。Fe 专用模型选择限于该项目。 |
| NEB / DIMER / 振动 | scripts/ts_strategy_engine/execution_gate.py、scripts/ts_validation/dimer_frequency_gate.py、scripts/ts_validation/analyze_vfa.py | 路径、力、方向和绑定模态 → 指定动作或待复核证据 | 搜索方向、频率交接、虚频方向、连通性和 TS 资格可分别成立。 |
| Scientific Intake | scripts/scientific_intake.py | 本地、用户或外部证据 → 按字段及目标操作评估可用性 | 用户接受与科学评审分别记录。外部修正可凭结构、单位、模型、来源及条件审核。 |
| 热化学 | scripts/thermochemistry/engine.py、frequencies.py、harmonic.py（同目录） | 各状态频率或审核后的预计算修正 → 条件化热修正与反应自由能 | 独立核对结构和活动子空间，检查 TS 反应坐标、ZPE 归属和温度。 |
| 网络与位点 | scripts/reaction_network/builder.py、site_review.py、thermodynamics.py（同目录） | 物种、确认足迹、空位和化学计量 → 有版本的反应图和闭合检查 | 支持多表面和界面。图连通仅代表候选路径。位点、元素、电荷及动力学资格单独检查。 |
| 参数与导出 | scripts/kinetic_parameters/engine.py、export.py（同目录） | 条件范围、正逆能垒、标准态、简并度及速率定律 → 条件化参数与引擎表 | 单位及基准有约束。只有相应条件与模型的有效参数可下传。 |
| 原生模型装配 | scripts/native_model.py | 引擎表、结构化配置 → 不可变模型、清单与校验和 | 装配、回读、发布模型文件与授权执行是独立步骤。见 P2。 |
| CATKINAS 与 MKM | scripts/baseline_mkm/native.py、single_point.py、single_point_result.py（同目录） | 平均场模型、条件、绑定计划 → 原生输入与已核验单点 | 合成闭环已验证。适配器限制原生可表达的占位；覆盖分析器具备的能力可能更广。 |
| Zacros 与 KMC | scripts/surface_kmc/native.py、lattice.py（同目录）、scripts/native_model.py | 晶格、占位、邻接、局域能及事件 → 原生输入和可绑定重启材料 | 八个有限步合成案例留下原生回执；通用生产运行器、统计稳态结果提供者仍缺。 |
| 分析与灵敏度 | scripts/baseline_mkm/kinetic_analysis.py、molecular_coverage.py、pathway_analysis.py、drc_pair.py、sensitivity_study.py（同目录） | 已核验通量、覆盖和成对扰动 → 竞争关系、方向通量和响应 | 分子覆盖按声明基准，空位按库存；路径、通量和定量贡献有不同证据要求。 |
| 科学优先级 | scripts/scientific_priority/engine.py、evidence.py、proposals.py（同目录） | 缺证、敏感性与来源 → 排序建议、评审提案 | 可给出下一条取证建议。提案与运行批准分开。 |
| SPC 与 Research Ticket | scripts/scientific_priority/proposals.py、scripts/baseline_mkm/single_point.py，外部 scientific-problem-compiler/src/spc/models.py 和 export.py | SPC 提案和问题身份 → 项目绑定；运行结果 → 人审工单 | SPC 使用 ExecutionProposal 和 ResultEvidenceSubmission。H7 有隔离回执及只读问题绑定。跨引擎结果往返仍需验证。 |
| Registry | scripts/registry_write.py、scripts/registry_mutations.py、scripts/registry_acceptance.py | 结构化批次、来源及审查 → 登记与资格记录 | 批次验证与生产写入可分开。P1 列出分析入口对 CLI 的反向引用。 |
| State Handoff | scripts/state_manager、modules/state_handoff | 事件与证据哈希 → 提案、受管投影与决定历史 | safe-only 仅限免审变更。历史事件、当前模块状态和科学回执用途不同。 |
| 执行门 | scripts/ts_strategy_engine/execution_gate.py、scripts/baseline_mkm/single_point.py、scripts/baseline_mkm/drc_batch_execution.py | 被批准的动作、模型、计划、预算 → 有界执行与回执 | 计划变化后须重验。已有 DRC 批次的预算只适用于其计划。 |
| 理想反应器 | modules/reactor_simulation/README.md、configs/kinetics/simulation_run.schema.json | 已声明的模型、供率方、工况 → 计划运行记录 | 可登记运行类别。CSTR/PFR 方程、稳态或轨迹解及验证回执尚缺。 |
