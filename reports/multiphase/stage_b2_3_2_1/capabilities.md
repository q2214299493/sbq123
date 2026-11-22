# Zacros 4.0 多相原生能力矩阵

**原生证据同时覆盖不等容量和同一分子跨类型占位。** 发行包示例 102 在 15 节点显式图上运行，四类位点容量为 3、3、6、3。末帧的 `CO3***` 在物种表计为 1，空间快照的三个节点记录同一实体 ID 和三个不同腿号。项目 `dent.zip` 独立验证一个双齿实体跨 Ni、Cu 位点。氧化物 CO₂ 的具体七节点图和动力学仍缺证据。[证据索引](evidence.json) · [氧化物评估](oxide.md)

判定范围为 Zacros 4.0 与当前 SBQ123 导出器。`verified_native` 表示有对应的原生输入和输出；`supported_with_restrictions` 表示已验证的原生构件只能在表列条件下使用；`unverified` 表示指定组合缺少原生回执；`unsupported` 表示指定表示方式会丢失必要语义。科学资格、原生能力和本轮执行权限独立记录。

| 能力及审计范围 | 判定 | 原生证据、适用边界及可观测量 |
| --- | --- | --- |
| 多个位点类型 | verified_native | 示例 102 的 general 输出列出四种类型，lattice 输出逐节点给出类型。项目晶格 Ni/Cu 有两种不同别名。 |
| 多个独立库存 | verified_native | Ni/Cu 晶格各 9 个节点。用项目 site_id 与节点的一一归属，可分别恢复占用数和空位。一个物理节点只有一个容量；多个竞争构型共享该节点。 |
| 不等容量 | verified_native | 示例 102 的节点类型计数 3、3、6、3 与 general 输出逐类相符。示例 103 的四类容量为 2163、1689、237、711。4∶3 是待建氧化物实例。 |
| 多齿吸附 | verified_native | 项目双齿实体跨两个节点，示例 102 的三齿 CO₃ 形成事件实际发生 1 次。两者的分子计数均可回到实体身份。 |
| 同一分子跨两种位点 | verified_native | `dent` 的正向产物和反向反应物均为同一 HCu* 实体，腿 1 在 Ni、腿 2 在 Cu。初始两个占位只产生 1 个表面分子。 |
| 相间转移 | supported_with_restrictions | 示例 103 在已连接的 fccCu 与 fccPdCu 两类位点间有 H 跳跃，过程计数分别为 14,395 和 13,506。把此事件解释为两个项目相之间的转移，还需域归属、接触边和驻留态别名。B.2.2.2 的具体 `move` 无原生回执。 |
| 跨相基元反应 | supported_with_restrictions | 已验收的 Ni/Cu 双位点解离/复合跨两个项目库存。示例 102 展示已指定类型与邻接的三节点化学事件。将 B.2.2.3 多反应物步骤映射到同一图，须确认各参与物、空位和产物腿共用的局部嵌入。 |
| 界面产物 | supported_with_restrictions | `dent.zip!/dataset.json` 将 H2-bridge 绑定 `junction` 和两个表面；原生步骤产生一个跨两类位点的实体。独立界面 ID 由项目数据保存。B.2.2.3 指定的 A+B+B 三齿产物没有对应原生回执。 |
| 产物驻留第三相 | unverified | 第三相的物种和双位点足迹可在通用契约中表达。尚无保留 A、B、C 及同一三相接触的 `on-third` 原生输入和结果。当前缺 C 上两个目标节点与反应物之间的已评审局部图。 |
| 显式晶格邻接 | verified_native | 随附 102/103 使用 `lattice explicit`；项目控制使用 `periodic_cell` 和含平移的 `neighboring_structure`。项目导出器目前只写后一种。本地有限非周期图的直接导出为 `unsupported`。 |
| 多位点事件匹配 | verified_native | `dent` 初始 15 个空对吸附匹配和 1 个解吸匹配。交换 seed 腿序的原生诊断丢失该解吸匹配，仍正常退出。几何图、两侧模式及腿序都影响允许事件。 |
| 反向事件和可逆性 | verified_native | 厂商 102/103 使用 `reversible_step`，原生分别统计两个方向。项目使用两条有依据的定向 `step`；警告 4008 已记录。单条显式不可逆步骤也有原生实例。可逆性未知时，正反系数与方向的执行映射保持阻断。 |
| 重启与轨迹统计 | verified_native | `split` 在事件 8 写检查点，`resume` 续至 20。拼接的物种和过程记录与 `continuous` 字节一致。原生表末采样在 19。短轨迹可报告窗口计数和均值，稳态及独立统计误差仍未确定。 |
| 仅靠相名跨多个独立图发起同步事件 | unsupported | 当前工作流中的一次事件须匹配同一原生晶格上的连通局部图。网络的 interface_id 或反应式无法单独声明跨图邻接。 |
| 用单一原生文件完整反推项目域和版本 | unsupported | 版本、物种/库存 ID、所属表面/相及具体界面依赖数据集与清单绑定。两个接触可能有相同的类型名；只留原生别名会丢失身份。 |

吸附物相互作用也有独立对照。吸引和排斥归档分别验证每条异类占用键 −0.04 和 +0.04 eV；全覆盖时各有 18 条键。排斥模型有警告 804010。相互作用的能量与局部速率模型须有共同的评审来源。[Phase 2.5.1 矩阵](../phase2_5_1/capabilities.md)

## 原始资料定位

- Zacros 4.0 User Guide，2024-07-19，共 101 页。第 21 页给出齿数，第 50–54 页给出周期及显式图，第 60–68 页给出事件与方向，第 69–71 页给出种子和重启，第 81–84 页给出空间轨迹、过程统计与物种计数。安装手册、发行压缩包内手册和项目原生回执的手册 SHA-256 一致。官方教程说明了如何逐个编号同类节点以及如何给出邻接。[官方分发入口](https://zacros.org/software/obtain-zacros) · [官方晶格教程](https://zacros.org/resources/tutorials/11-lattice-input-for-a-fcc-100-surface?showall=1) · [官方实体与腿号教程](https://zacros.org/resources/tutorials/4-tutorial-1-ziff-gulari-barshad-model-in-zacros?start=3)
- 索引列出发行包内 `examples/102/`、`examples/103/` 使用的文件及哈希。102 的末帧事件号为 107895。实体 1 的腿 1、2、3 分别落在节点 3、2、1，类型依次为 cn4、br42、cn2。103 的两类位点跳跃计数取自 procstat 自身末采样；异步输出须按各自时钟解释。[发行包成员与核对数值](evidence.json)
- 项目 Phase 2.5 的空晶格单点与 Phase 2.5.1 的八个归档分别核对。归档 ZIP、清单、原生输入及回执列出的输出成员均以原始字节计算摘要。B.1 保留的轨迹窗口与单位可独立重放。[空晶格回执](../phase2_5/native_validation.json) · [八个基准回执](../phase2_5_1/zacros_validation.json) · [B.1 输出资格](../stage_b1_4/zacros_qualification.json)
