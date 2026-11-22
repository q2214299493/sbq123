# B.2.3.2.2 合成氧化物 CO₂ 的七节点映射

**对本轮声明的有限开放链，全空时有 6 对可吸附酸–氧位。两个初始 CO₂ 分子可以共存；放入后还有 2 对可选空位，但两对共享一个氧位，最多再放 1 个分子。整张图最多同时容纳 3 个桥式 CO₂。**

## 模型的来源与范围

沿用原始计数观察的 **4 个 acid-A 和 3 个 oxygen-B**，以及同一计数单元内的 2 个 CO₂。任务中“3 个酸位、4 个氧位”的条件与该记录不符。网络定义给出 oxide-alpha、oxide-012、两个位点类型、一酸一氧的分子足迹及反应 `fixture-adsorption`。它给出的表面矢量和类型级相邻说明无法确定这七个节点的具体边。[结构定义](../../../tests/fixtures/multiphase/synthetic_oxide_site_network.json) · [计数观察](../stage_b2_1/oxide_observations.json)

本轮选用上次审计中第一张假想图，以便与已审反例直接比较。开边界、邻接、原生编号、各实体的腿序及二维示意坐标都是 `synthetic_test_assumption`。每个节点只出现一次，无周期复制、跨胞平移或首尾环绕。边的来源是明确列出的图；示意坐标只为填写原生候选的笛卡尔位置，不能用来推断真实键长或新增边。真实氧化物的配对数仍未知。[上轮图的出处](../stage_b2_3_2_1/oxide.md) · [七节点、别名与分子初态](../../../tests/fixtures/multiphase/synthetic_oxide_bridge_graph.json)

## 晶格与逐边结果

原生编号 1–4 分别对应 acid-1 至 acid-4，类型为 Lewis 酸；5–7 对应 oxygen-1 至 oxygen-3，类型为碱性氧。按路径行走的顺序为 **1—5—2—6—3—7—4**。两座桥中，腿 1 在酸位，腿 2 在氧位。

| 边（腿 1，腿 2） | 初态酸位 / 氧位 | 可吸附 | 完整分子的解吸模式匹配 |
| --- | --- | --- | --- |
| (1,5) | bridge-1 / bridge-1 | 否 | bridge-1 |
| (2,5) | bridge-2 / bridge-1 | 否 | 否，两个分子各占一端 |
| (2,6) | bridge-2 / bridge-2 | 否 | bridge-2 |
| (3,6) | 空 / bridge-2 | 否 | 否 |
| (3,7) | 空 / 空 | 是 | 否 |
| (4,7) | 空 / 空 | 是 | 否 |

以 1 至 7 为行、列顺序的无向邻接矩阵如下。1 表示有显式边。

```text
      1 2 3 4 5 6 7
1     0 0 0 0 1 0 0
2     0 0 0 0 1 1 0
3     0 0 0 0 0 1 1
4     0 0 0 0 0 0 1
5     1 1 0 0 0 0 0
6     0 1 1 0 0 0 0
7     0 0 1 1 0 0 0
```

初态占用酸位 2/4、氧位 2/3，两库存分别余 2、1 个空位。最大匹配有直接证明：三个氧位给出上界 3，互不重叠的 (1,5)、(2,6)、(3,7) 达到该上界。固定这两个初始实体时，第三座桥也可改用 (4,7)。表中的两个解吸匹配只判断实体及有序腿是否符合反向模式；原反应的 `reversible` 仍为 null。[机器可读矩阵、逐边结果及最大匹配](mapping.json)

## Zacros 候选与独立复核

候选使用 4.0 手册第 52–54 页的 `lattice explicit`。包含两个 site_type、7 行节点、逐节点的邻接编号及开放边界。表面别名 `CO2bridge*` 的齿数为 2；正向从两个各自为空的节点生成同一实体的腿 1、2，气相 CO₂ 系数为 −1。反向结构模式交换两侧并释放 1 个气相 CO₂。已有 `pattern_header`、`slots`、`state_input` 负责候选的模式、腿号和种子。它们与既有生产导出入口分别使用。温度、分压、速率和可逆性尚无本案例的参数依据。候选中没有执行计划，原生解析及求解均未验证。[原生字段与种子片段](mapping.json) · [4.0 手册及原生归档索引](../stage_b2_3_2_1/evidence.json)

匹配器沿显式边按两类位点排序，逐端核对初态实体，并用增广路寻找最大二分匹配。独立测试从输出的原生格式文本读回图和种子，再调用仓库的 `lattice.embeddings` 枚举有序匹配，按实体比较每条边。另用小图穷举所有不相交边的组合验证最大值。第二张同容量、同种子的连通图得到 7 条边、1 条可用空边。另一个检验在原六边图上改变种子，使两座桥均合法但已无可加空边，说明初态可能限制剩余同时占位数。[实现](../../../scripts/surface_kmc/bridge_topology.py) · [反例和独立回读测试](../../../tests/test_oxide_bridge_topology.py)

从仓库根目录可用以下只读命令重建 JSON 输出。两棵工作树独立生成的报告 SHA-256 均为 `bb0f706fefc969bdf67a5fa44b2c21f8f61ed2e09f1778a76d6b1b6d342e0971`。程序根据同一份输入字节解析数据并核对来源哈希。

```powershell
C:/Anaconda/python.exe -m scripts.surface_kmc.bridge_topology tests/fixtures/multiphase/synthetic_oxide_bridge_graph.json
```

## 验证与交付

发布基线 `524de00178f705dd5f09d75bf2dd8c64e64c9fb6`；开发树 HEAD 为 `233d5a6c`，其现场项目文件独立核对。两树均逐字节检验 46 个既有来源与基线 Git 对象一致，包括结构、库存、归一化审计、Zacros 能力矩阵与既有原生归档。修改范围为新增离线入口、夹具、测试、报告和模块文档链接。

| 工作树 | 改动前专项 | 改动后专项 | 另行运行 |
| --- | --- | --- | --- |
| Windows 开发 | 658 通过，8 排除 | 676 通过，8 排除，38.89 s | 2 项架构边界通过；py_compile 和 Ruff 通过 |
| Windows 独立发布 | 658 通过，8 排除 | 676 通过，8 排除，38.45 s | 2 项架构边界通过；py_compile 和 Ruff 通过 |

原有 658 项沿用[上轮专项范围](../stage_b2_3_2_1/completion.md)（在同一 pytest 命令中加入 `tests/test_oxide_bridge_topology.py`）。新增 18 项覆盖逐边回读、同时占位、增广路径、非连通图与同类型非反应边、重复边、缺失节点、错误类型、共享端点、腿序、边界、编号置换和输入哈希变化。8 项原生重放测试按任务约束显式排除。这是离线专项验证，原生执行次数为 0。

本轮文件如下。

- `modules/surface_kmc/README.md`
- `scripts/surface_kmc/bridge_topology.py`
- `tests/fixtures/multiphase/synthetic_oxide_bridge_graph.json`
- `tests/test_oxide_bridge_topology.py`
- `reports/multiphase/stage_b2_3_2_2/mapping.json`
- `reports/multiphase/stage_b2_3_2_2/completion.md`
- `reports/multiphase/stage_b2_3_2_2/handoff.md`
- `modules/state_handoff/events/history-stage-b2-3-2-2-oxide-bridge-topology-20261122.json`

[State Handoff 提案及同步结果](handoff.md)
