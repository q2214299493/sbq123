# B.2.2.3 跨相基元反应契约验收

现有交换契约和 Reaction Network Builder 已支持显式的 `cross_phase_elementary`。两个独立合成案例分别验证了两相反应物形成界面产物，以及三相接触中产物驻留在第三相的情况。两例的网络级别均为 `STRUCTURALLY_VALID`。该结果验证数据表示与守恒算法，真实催化体系的能垒和机理仍需独立证据。[逐项机器回执](validation.json)

## 职责与分类

| 对象 | 权威来源 | 本次检查 |
| --- | --- | --- |
| 相、表面、界面和位点 | 原催化剂目录及 B.2.2.1 所属关系 | 每条跨相事件显式列出相、表面和单一界面引用。已知接触须连接所列各面和相，参与物种、位点或已绑定 TS 须能解释各面角色。 |
| 物种身份与反应计量 | 物种目录和反应两侧的 species ID 与正整数系数 | 同组成物种保留独立身份。每侧按系数计算元素和电荷，产物可位于新相。 |
| 跨相转移 | B.2.2.2 的 `interphase_transfer` | 同一分子的两侧驻留态保持分子数，各自足迹决定释放及消耗的空位。既有路径照原输入重放。 |
| 跨相基元反应 | V1 反应 schema 与部分网络定义 | `cross_phase_elementary` 支持多分子反应及分子数改变。只有反应记录显式指定分类，程序才按该分类解释。 |
| 过渡态位置 | 可选 `ts_species_id` 及已有 TS 结构引用 | 完整过渡复合物须与所引用结构、表面和界面匹配。核对有证据的元素、电荷及瞬时足迹。稳态源项排除该中间结构。独立 Grade A 审核仍由原模块负责。 |
| 库存与源项 | 既有位点审阅、B.2.1 占位和 B.1.3 计量投影 | 按单一库存核对两侧占位和空位。配置共享物理容量时使用同一库存 ID；重复认领物理成员使受影响的容量不可用。 |
| 科学与执行资格 | 原网络审核及各引擎的独立准入流程 | 结果分别列出电子能、Gibbs、参数、审核、MKM 和 KMC 状态。 |

## 界面范围与未知项

两相样例的两个反应物分别位于 A、B，产物横跨同一已声明的 A/B 接触。三相样例声明一个连接 A、B、C 的接触，反应物位于 A、B，产物仅占 C 的两个位点。仅有 A/B 和 B/C 两个接触无法证明存在 A/B/C 共同接触，本契约要求为每个有依据的事件声明其实际范围。

对于只有独立表面绑定的物种，部分定义可显式填写 `interface_id: null`。这种记录保留分子及库存计量，界面核实为未知，网络保持 DRAFT。引用不存在的相、表面、库存或界面会产生错误。界面专属物种或位点仍须指定相符的接触。缺失组分或电荷分别保留相应未知项；完整 V1 交换路径继续要求已知物种化学字段。缺失足迹只阻断依赖该物种的库存证明。

## 分子、元素与库存手算

两相样例在一个明确定义的合成计数单元中，将 A 上的两个带 +1 电荷 H 标签和 B 上的一个带 −2 电荷 O 标签组合为一个中性界面产物。两侧均含两个 H 和一个 O，总电荷为零。分子数由 3 变为 1。构造样例的电荷和可逆性均为测试声明。

| 两相单元 | 初始占位 / 空位 | 最终占位 / 空位 | 空位变化 | 容量 |
| --- | ---: | ---: | ---: | ---: |
| A | 2 / 1 | 1 / 2 | +1 | 3 |
| B | 1 / 3 | 2 / 2 | −1 | 4 |

若遗漏释放 A 与消耗 B，汇总后的总位点数仍可相等，逐库存检查会拒绝该输入。若 A 的反应物足迹未知，仍可独立检查 B，包括拒绝 B 上已知的矛盾。B.1 单位反应进度投影与 B.2.1 有限计数单元独立重建了上表。

三相样例的两个合成反应物分别提供一个 He 标签和一个 Ne 标签，第三相的产物保留两种元素。三个库存的空位变化依次为 +1、+1、−2；每个库存的占位与空位变化之和均为零。该样例没有绝对容量观测，可逆性也未知，反向反应保持为空。两个样例均未生成动力学速率。[源项、方向和守恒残差](validation.json)

## 资格矩阵

| 维度 | 两相界面产物 | 三相接触产物 |
| --- | --- | --- |
| 结构表示 | STRUCTURALLY_VALID | STRUCTURALLY_VALID |
| 界面范围 | 已核实合成目录绑定 | 已核实单一三相接触绑定 |
| 端点计量 | 元素、电荷及 A/B 库存守恒 | 元素、电荷及 A/B/C 库存守恒 |
| 电子能证据 | 缺失 | 缺失 |
| 热化学证据 | 缺失 | 缺失 |
| 动力学参数 | 缺失 | 缺失 |
| 科学审阅 | 未获接受 | 未获接受 |
| MKM 资格 | blocked | blocked |
| KMC 资格 | blocked | blocked |

数值字段标作 `supplied` 仅表示已提供相应字段。完整参数和已获科学接受的网络仍需本引擎的原生模型与执行资格。两例都缺经过支持的 TS 处理或无势垒依据。Fe(110) 归档网络的版本和 blocked 状态已经单独重放核实。

## 本轮文件清单

- `configs/kinetics/reaction.schema.json`
- `scripts/multiphase_contracts.py`
- `scripts/reaction_network/catalog.py`
- `scripts/reaction_network/builder.py`
- `scripts/reaction_network/cross_phase.py`
- `scripts/reaction_network/site_review.py`
- `modules/reaction_network/README.md`
- `tests/test_cross_phase_elementary.py`
- `tests/fixtures/multiphase/cross_phase_counting_cell.json`
- `tests/fixtures/multiphase/cross_phase_interface_product.json`
- `tests/fixtures/multiphase/cross_phase_three_phase.json`
- `reports/multiphase/stage_b2_2_3/validation.json`
- `reports/multiphase/stage_b2_2_3/completion.md`
- `reports/multiphase/stage_b2_2_3/regression.md`
- `reports/multiphase/stage_b2_2_3/handoff.md`
- `modules/state_handoff/events/history-stage-b2-2-3-cross-phase-elementary-20261122.json`

[双树测试和历史哈希](regression.md) · [待审状态交接](handoff.md)
