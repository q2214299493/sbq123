# 通用网络到 Zacros 4.0 的字段映射

审计链从项目的版本化网络、动力学数据集和项目配置出发，经既有 `scripts.native_model` 及 `scripts.surface_kmc` 的生成器产生原生文件。按清单哈希回读配置、数据集、输入与轨迹，才能将某个节点或事件归回具体研究项目。[既有文件契约](../phase2_5_native_contracts.md) · [原生能力证据](capabilities.md)

| 通用输入或依赖 | 原生表示 | 等价性检查与输出 |
| --- | --- | --- |
| project_id、network_version、dataset_version、parameter_set 及来源 | 清单绑定数据集、导出表、配置和原生文件哈希。项目目录保留 phase_id、surface_id、interface_id。 | 沿 site_id → surface_id → phase_id 和反应界面复核。不同域同名位点保留不同别名；共享物理库存复用同一组节点。同一对相上的两个接触须保留各自的界面 ID。 |
| species_id、phase、composition、charge、site_occupancy | 气体用 gas 声明和 `gas_reacs_prods`；表面物种用唯一 `surf_specs_names` 与 `surf_specs_dent`。齿数为每个分子在各库占位数之和。 | 一分子的多行用同一个局部实体号、不同腿号；两分子使用不同实体号。保持同组成而驻留态不同的物种映射可逆。衡算分子、元素、电荷与每个库存。 |
| site_id、cell_sites、cell_vectors_A、repeat_cell、links | `periodic_cell` 的类型、分数坐标和带平移的节点对；引擎也接受 `explicit` 的笛卡尔坐标、类型与逐节点邻接。 | 从展开图重数各类型；只把已声明允许的边用于匹配。坐标接近或相同 Miller 指数均不建立反应邻接。超胞平移必须能唯一还原实际边。 |
| reactants、products、计量、sites_consumed/released、required_sites、方向 | 对应数目的独立实体放在 `initial` 和 `final`；`sites`、`site_types`、`neighboring` 固定参与槽位与边。保留供反应匹配的旁观位及其状态。 | 同一事件原地更新各节点；空位和每条腿占用能分别反推原计量。项目使用独立的正逆模式与系数，显式单向只写获准方向。核查过程统计中的步骤和方向。 |
| local_event.site_ids、initial/final、neighbors_zero_based、patterns_per_reference_site | 零基模式边映为一基槽位编号。单侧按 (species_id, entity) 分配相同实体号，腿号沿该物种的槽位顺序递增。 | 先在静态图枚举不同局部状态转移，除以 repeat_cell 乘积 × reference_sites_per_cell，与获审的每参考位点模式数一致。实际某帧只能匹配满足占用状态的子集。cluster 的 graph_multiplicity 是能量模式的对称修正，不能充当可用反应对数。 |
| T、总压、各气体分压、每匹配的正/逆系数、级数与能量参考 | `temperature`、`pressure`、`gas_molar_fracs` 及步骤的速率参数。固定点导出使用已热化系数、零表观 activ_eng；气体 n 阶系数单位为 s⁻¹ bar⁻ⁿ，乘分压幂后为每匹配 s⁻¹。 | 与项目动力学表核对，不能再次除以模式数。交互能簇、气相能、BEP 系数须与速率模型共同绑定。厂商可逆块的 pe_ratio 表示前后指数前因子之比，不能直接读成任意条件的平衡常数。 |
| 初始分子、每条腿的物理节点，checkpoint | `seed_on_sites` 的一基节点列表为同一实体；restart 需绑定生成模型和输入检查点。 | 逐个核对腿序、唯一占位、连通性；优先恢复有来源的检查点时检查历史。两个等计数初态可有不同可用事件数。 |
| 分子与库存统计、速率输出 | `specnum` 数表面分子与累计气体交换；`history` 给每节点的实体、物种及腿，`lattice_output` 给节点类型及邻接，`procstat` 给分方向事件计数。 | 当足迹固定可按分子数 × 各库足迹回算占位；同一物种可选多种位点/足迹时需空间快照或等价别名细分。B.1 以真实采样窗口 ΔN/Δt 表示每整张模拟晶格每秒的事件数，复用计量源项。库存覆盖度则分别除以各库容量。 |

## 具体拓扑与阻断位置

| 来源反应 | 模式及事件数如何确定 | 可报告的原生观测和当前限制 |
| --- | --- | --- |
| Ni/Cu `ads` | 单齿控制中 H₂ 解离为各占一位的两个 H；`dent` 中 H₂ 形成 `junction` 上一个双齿 H2-bridge。按 Ni–Cu 边枚举，初态/终态指明同一或不同实体。 | 可核对独立库存、分子数、两个方向及轨迹。详见[Ni/Cu 回归及重放条件](completion.md)。 |
| B.2.2.2 `move` | x-a 占据 A、B 为空，变为 A 为空、x-b 占据 B。接触为 `contact`，反向交换源、目标。每个允许的有向转移对应一条匹配边。 | 结构转移量可守恒；缺真实节点边、对应局部速率及热力学依据，无法给出运行次数或净传输率。随附 103 仅验证异类位点间局部跳跃。 |
| B.2.2.3 `junction/combine` | 两个 left-H 实体、一个 right-O 和一个 B 空位需同时匹配 A、A、B、B。目标 contact-product 的一个实体跨 A、B、B，另一个 A 释放。模式要明确哪一个 A 释放、三条腿的顺序及等价排列。 | 通用库存变化已知。具体边、构型简并、产物放置和速率未绑定。其原生能力类比来源为项目双齿和厂商三齿案例，目标四节点事件未验证。 |
| B.2.2.3 `triple-junction/combine` | 两个不同相的单齿反应物释放 A、B，第三相 C 两个空位容纳同一 on-third 双齿实体。须给出同一三相接触中 A、B、C、C 的连通事件图。 | 第三相绝对容量、联合邻接、动力学与反向声明均待补。不得把第三相产物移到 A 或 B 或把未知反向当零。 |
| 氧化物 `fixture-adsorption` | 一个气相 CO₂、两个异类空位和一个双齿表面产物。每个匹配必须锚定一条真实酸–氧边。 | 目标分子与库存统计可定义；实际边、匹配数与速率留空。[逐字段评估](oxide.md) |

这些映射只依赖本 KMC 引擎的局部图、动力学及原生来源。B.2.3.1 的 CATKINAS 映射可用于比较通用 ID 与版本绑定；其平均场参考位点对及未知的 Q1x2_CO2 分母不参与 Zacros 图或分子计数。[引擎架构决策](../../../docs/decisions/adaptive_mkm_kmc_optional_reactor.md)
