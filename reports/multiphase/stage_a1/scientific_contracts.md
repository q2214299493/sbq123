# 科学数据契约图

| 交接 | 现有契约或实现 | 关键语义与拒绝条件 |
|---|---|---|
| 项目 → 表面与物种 | configs/kinetics/bundle.schema.json、species.schema.json；scripts/multiphase_contracts.py | 材料、相、表面、界面和位点须可引用；组成、荷电、结构身份、吸附构型和 site_occupancy 各有来源。null 表示未决，审定的 0 才参与相应零值运算。 |
| DFT / MLIP / 外部数据 → Intake | configs/kinetics/scientific_intake.schema.json；scripts/scientific_intake.py 的 assess_field、thermal_routes | 将记录 ID、来源、数值、单位、结构/方法、审核与用途绑定。模型预测、计算观察和审核结论区分。缺局部作业 ID 可采用可追溯外部记录。 |
| Intake → 热修正 | scripts/thermochemistry/engine.py 的 validate_subspace、compare_subspaces、precomputed、check_ts_correction | 各状态自证结构、原子映射、约束和 Hessian 维数；不同活动空间与频率缩放需要独立依据。检查温度、标准态、能量零点、ZPE 与热焓增量归属。原始 TS 与已审反应坐标绑定；预计算修正须说明其排除处理。 |
| 热修正 → 反应 | reaction.schema.json；scripts/reaction_network/builder.py、thermodynamics.py | 同一条件和参考下 ΔG = G_FS − G_IS，正逆能垒差应等于 ΔG。网络绑定结构和已确认反应身份。逐域检查带化学计量的占位、空位、元素、电荷；反向需要可逆性证据。缺端点可报告电子能。 |
| 反应 → 参数 | kinetic_parameter.schema.json；scripts/kinetic_parameters/engine.py | 参数绑定 reaction_id、温压区间、能量基准、标准态、正/逆速率表达式、简并和覆盖项。正逆属于同一参照时核对详细平衡；有单位的速率常数之比须先通过标准活度转换。 |
| 参数 → 平均场 | scripts/kinetic_parameters/export.py 的 per_bar、catkinas_energy_pair；scripts/baseline_mkm/native.py | 输入压力用 Pa 表达，适配器按气相总反应级数用 (100000 Pa / p°)^order 转换到以 bar 分压计算的系数。平均场活度取决于声明的覆盖基准、空位和模型。 |
| 参数 → 晶格事件 | 同一 export.py 的 verify_event、zacros；scripts/surface_kmc/lattice.py、native.py | 事件率以匹配的局域构型为条件。绑定晶格位点、齿数、邻接、方向、等价嵌入、成对相互作用及模型范围。平均场通量无法单独确定这些量。 |
| 模型与计划 → 运行 | simulation_run.schema.json；scripts/native_model.py、scripts/baseline_mkm/single_point.py | 清单绑定数据集/网络版本、条件和输入哈希，运行绑定计划和批准。执行状态、数值收敛、科学有效性、审批为独立字段。 |
| 运行 → 分析 | mkm_analysis.schema.json、mkm_coverage.schema.json、mkm_drc.schema.json；scripts/baseline_mkm/kinetic_analysis.py | 方向/净通量分开；跨库存物种按一个分子基准报告，各库存分别守恒。路径枚举上限、图可达、多反应物可行性、通量贡献分别解释。 |
| 分析 → 供率与反应器 | kinetic_analysis.py 的 physical_factors；simulation_run.schema.json 的 reactor 输入 | 可用时提供单位面积、催化剂质量及反应器体积归一化。带有效条件和不确定度的可调用速率提供者、反应器边界条件、求解结果协议仍缺。P6、P11 |
| 科学结果 → 优先级、SPC、Ticket | scripts/scientific_priority/proposals.py 的 spc_reference、review；single_point.py 的 ticket_binding | 需保留问题哈希、输入证据和审核状态。外部提案审核、科研结论及本地执行授权各自独立。P10 |

除注明完整路径外，表中 schema 均在 configs/kinetics 下。有 1.0.0 命名空间的 bundle/species/reaction/kinetic_parameter/simulation_run 使用 schema_version；MKM 分析系列按 format 判别。格式版本、网络/数据集内容版本、引擎版本和批准计划摘要是四种不同身份。现存 schema 之间没有统一的跨引擎结果升级器。拟议兼容测试见 P6、P7。

单位换算必须同时保留分母。例如 phase3_0/result.json 的 turnover_basis 为 one_event_per_reference_site；phase3_2_0/result.json 的 normalization 指定 reference_site_pair，列有一份 Ni-top 与一份 Cu-bridge 及附件哈希。重复利用数值前需解析对应记录的实际基准。物理位点密度和催化剂装填量均不得由上述标签推断。
