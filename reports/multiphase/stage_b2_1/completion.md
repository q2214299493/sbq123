# Stage B.2.1 · 跨库存分子数与位点守恒验收

Ni/Cu 和合成氧化物均通过独立的分子计数和逐库存守恒检查。变更集中在已有覆盖率分析入口。研究者可为观测选择一个计数参照，读出该参照上的分子数，以及每个库存的容量、已占与空位数。原有 B.1 速率契约继续保留各引擎的原生分母。

## 手算与现场结果

对每个库存，将每种分子在计数参照内的数量乘以它在该库存的占位重数，再求和。空位数等于该库存容量减去已占数。重复单元上的平均数可以为小数。

| 系统与库存 | 容量 | 分子对该库存的贡献 | 已占 | 空位 | 占用比例 | 空位比例 |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Ni/Cu · top-Ni | 2 | H2-bridge 0.30，H2-top 0.50 | 0.80 | 1.20 | 0.40 | 0.60 |
| Ni/Cu · bridge-Cu | 1 | H2-bridge 0.30 | 0.30 | 0.70 | 0.30 | 0.70 |
| 氧化物 · acid-A | 4 | co2-bound 2 | 2 | 2 | 1/2 | 1/2 |
| 氧化物 · oxygen-B | 3 | co2-bound 2 | 2 | 1 | 2/3 | 1/3 |

**Ni/Cu。** Phase 3.1.1 的 H2-bridge 在一个 interface-repeat 内有 0.30 个分子，一个分子跨 Ni-top、Cu-bridge 各占一位。H2-top 的归档观测是每个 Ni-top 0.25 个，折合每重复单元 0.50 个。两种物种在同一 top-Ni 库存竞争，容量只登记一次。计算所得空位比例与归档独立给定的 0.60、0.70 一致。新观测文件在归档输入的基础上仅增加计数参照字段。原观测 SHA-256 为 `ed8efa9cb2a3bb6c7ad9fe4888fa211ac535d23b119bccf2cb9796ea3a96f3db`。[归档输入](../phase3_1_1/observations.json) · [计数输入](interface_observations.json) · [验证结果](interface_validation.json)

**合成氧化物。** 原 fixture 给出 oxide-alpha、oxide-012 晶面、斜晶格矢量、Lewis 酸位和碱性氧位，以及一个 CO₂ 跨两位的足迹。它没有给出样品容量、吸附量或速率。为检验算术，单独建立一个有限样本，明确列举四个酸位成员、三个氧位成员，声明两个吸附 CO₂。这些数只属于合成测试输入。只读取结构时，分子数、容量、占用比例和空位比例均保持未知，原网络的 MKM 状态为 blocked。原 fixture SHA-256 为 `24d5c34d33ec332a131e5f957dcb83ff4816e29c5d4c6ba05c47c854d87c6aa2`。[原始结构定义](../../../tests/fixtures/multiphase/synthetic_oxide_site_network.json) · [有限样本声明](oxide_observations.json) · [验证结果](oxide_validation.json)

## 缺失、冲突与库存所有权

| 情形 | 可保留的信息 | 受影响的结果 |
| --- | --- | --- |
| 足迹未知，分子参照明确 | 每参照的分子数、其他表面的库存 | 可能表面上该物种的贡献未知。独立空位测量仍可限定总量。 |
| 明确零占位或零分子数 | 零值及其已知依据 | 空足迹不会消耗位点。已知零分子增量产生零占用。 |
| 容量未知，足迹及分子计数已知 | 该物种占用的位点数，其他库存的完整余额 | 该库存的空位数及依赖容量的比例未知。 |
| 分子参照缺失 | 独立测得的总空位比例、对应容量已知时的库存总量 | 分子数与未获独立测量的份额未知。 |
| 两个命名参照需要换算 | 同一库存的明确容量比可作为换算证据 | 缺少共同依据或容量比互相矛盾时，目标分子计数未知，原参照的观测仍可读取。 |
| 观测足迹与网络的一部分冲突 | 计数模式保留已同意的库存贡献，以及有独立参照的分子数 | 冲突库存的贡献留空并列出库存 ID。未知库存身份、非法重数等无效输入仍按原契约拒绝。 |
| 多个构型占同一物理位点 | 由足迹明确引用同一规范库存 ID，在同一池中竞争 | 若两个独立库存重复声明同一物理成员，相关池留空并提示统一映射。其他库存继续计算。名称相同不会触发合并。 |

计数参照内可列举完整的物理成员，也可使用已有的每参照容量。成员表和数值容量同时给出时必须一致。没有物理成员证据时，分析只能使用项目声明的库存身份，不能从几何标签发现隐藏重叠。原有不含计数参照的合法报告保持原输出，Phase 3.1.1 的 CLI 快照逐字节通过。[入口及字段说明](../../../modules/baseline_mkm/README.md)

## 置换与 B.1 源项

两个案例各自重新构建网络，同时置换物种、库存与观测行的顺序，并对相、表面、位点和物种 ID 进行一致重命名。逆映射后，逐物种计数和足迹、逐库存贡献、占用、空位与活动度检查结果相同。另将 Ni、Cu 的位点类型名称设为相同，两个独立库存仍保留各自的容量和空位。网络内容变化仍产生其自己的版本，数据产品按对应网络解释。

独立的有限增量检查复用 B.1 的 `build_matrices` 与 `project_progress`，将一次给定反应进度投影到物种和空位，然后对照两个占位快照的差。Ni/Cu 取 +0.10 个反应事件当量，跨界面分子增加 0.10，两类空位各减少 0.10。氧化物取 +1，吸附 CO₂ 增加 1，两个库存各减少 1 个空位。此核验不含时间维度。B.1 的 CATKINAS 参考位点对是 1 Ni + 1 Cu；本次 Ni/Cu 覆盖观测的参照是 2 Ni + 1 Cu。Zacros 双齿归档仍按一个完整模拟晶格归一化。三个分母都回溯至各自的记录。

## 交付文件

- 现有分析入口与计数实现：`scripts/baseline_mkm/analysis.py`、`scripts/baseline_mkm/kinetic_analysis.py`、`scripts/baseline_mkm/molecular_coverage.py`。
- 覆盖率报告字段与用法：`configs/kinetics/mkm_coverage.schema.json`、`modules/baseline_mkm/README.md`。
- 独立测试：`tests/test_inventory_accounting.py`。
- 本报告目录：`interface_observations.json`、`interface_validation.json`、`oxide_observations.json`、`oxide_validation.json`、`completion.md`、`regression.md`、`handoff.md`。
- 历史事件：`modules/state_handoff/events/history-stage-b2-1-inventory-conservation-20261122.json`。

[两套工作树的回归明细](regression.md) · [State Handoff 待审事项](handoff.md)
