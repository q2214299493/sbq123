# 通用网络到 CATKINAS 的映射

离线入口接收 `reaction-network/1` 快照、与其版本绑定的 `kinetic-dataset/1`、定温配置及有来源的库存归一化文件。缺输入时可先取得有定位信息的拓扑审查结果。使用仓库根目录下的相对路径可复现已验收模型。

```powershell
C:/Anaconda/python.exe -m scripts.baseline_mkm.network_mapping reports/multiphase/phase3_0/closed_cycle_network.json --dataset reports/multiphase/phase2_5_2/cycle_dataset.json --configuration reports/multiphase/phase3_0/workflow_configuration.json --normalization reports/multiphase/phase3_1/benchmark_normalization.json --output-dir NEW_MODEL_DIR
```

| 通用字段 | 原生表达或清单字段 | 验证 |
| --- | --- | --- |
| project、network_version、dataset_version | manifest 绑定原对象，保留参数来源与配置摘要 | 重算版本摘要，从快照和审核模型重建数据集，复用已有导出和单点资格检查 |
| phase、surface、interface | manifest 保留命名域和所属关系，历史接触记录可通过关联表面解析参与相 | 核对项目目录、物种上下文和反应域。CATKINAS 方程中的位点编号表达均场库存，几何接触身份由清单保存 |
| site_id、species_id、site_occupancy | 原生库存编号和唯一物种别名。每种吸附物在该模型中占一份库存 | 按显式 ID 建表，按库存区分同组成物种，拒绝别名碰撞、跨库多齿或界面私有位点 |
| 正逆方向、计量系数、空位、所需集合 | 审核次序中的各条 `<->` 方程；manifest 同时保留正逆两侧的物种和空位字典 | 独立解析原生文本，逐项核对。已验证闭合图使用单位系数；其他系数保留在通用网络中并报告原生证据缺口 |
| 速率、单位、标准态 | 保留分方向系数、气体分压级数、标准态、等效定温 Ea/G0 与参数来源 | 复用导出器的单位转换，回读两侧系数。气体一阶为 bar⁻¹ s⁻¹，无气体因子为 s⁻¹ |
| 工况、初态 | T、冻结分压、各物种及各库存空位的初始分数、MaxTime、MaxOdeTime | 校验总压和分压、配置绑定、初始分数守恒。本入口只映射已实现的定温设置 |
| 原生归一化 | 一个参考位点对，各库存各一份；覆盖度在各自库存内归一 | 校验网络版本、归一化证据 SHA-256 及其网络来源绑定。历史配置中的周转标签与独立的定量基准一同保存在清单中 |

结构检查要求四个已验证角色能在整张图上使用一致的一一对应。依次为双库存解离、驻留物种转移、气相与驻留物种结合、产物脱附；输入列表可以使用不同顺序，可逆方程可以交换两侧。输出保持审核数据集的反应顺序。该规则依赖分子、库存和空位连接关系，可用于具有相同角色的其他项目。新材料生成同样的输入字节只能证明编码相同，其项目身份和科学适用性仍应分别审查。

Python 入口 `map_network` 返回 `(files, report)`。CLI 成功时退出 0，模型目录包含 `INPUT_phase25.m` 和 `manifest.json`。被阻断时退出 2，原生文件集合为空，审查报告可通过 `--report NEW.json` 单独保存。报告列出每一步可识别的方程形式，并区分 unsupported、unverified、missing_evidence 和 invalid。保留原快照即可补充证据再评估。成功映射的执行状态为 requires_separate_qualification_and_approval。

历史数据集级 assemble 入口仍可重放孤立步骤的输入语法；网络级 prepare / preflight 在多库存或跨相情形另查整网范围。已有执行门继续负责批准、运行及结果验收。对不同工况或尚无原生证据的拓扑，本检查点提供的回读不能替代新的原生结果。冻结分压的原生精度须按实际输出复核。[已有分压精度记录](../phase3_2_2_1/review.md)
