# Stage B.2.2.1 · 多相结构身份与归属验收

**通过结构身份验收。** 同一材料的不同相、同一相的多个表面、同一对表面上的不同界面和独立位点库存均能保持各自身份。只知道参与相时可以先记录界面，待有证据再填写表面。所有身份仍归原项目目录管理。验收范围为数据模型与离线校验。

## 归属矩阵与契约审计

| 对象 | 既有契约 | 本轮补齐及校验 |
| --- | --- | --- |
| 材料与相 | 项目拥有材料，材料拥有独立 phase_id。相已有名称、结构 ID、结构来源和自己的评审记录。 | 增加开放文本 phase_category、物理描述和可选电荷。非 accepted 的相可省略组成，完整交换格式中的 accepted 相仍须给出组成。同一材料下两个相可以具有不同表面和证据状态。 |
| 表面 | surface_id 引用一个 phase_id，原契约可记录三指数或四指数、终止面、缺陷和结构来源。 | 无适用晶面指数时可给出 surface_descriptor。可登记以 Å 为单位的两个面内向量或三个晶胞向量，以及坐标约定。已声明矛盾的相、材料或界面归属会在构建时暴露。 |
| 界面 | interface_id 是主键。旧记录由显式列出的至少两个表面确定参与域，同相不同表面形成的既有边界仍有效。 | 可直接登记至少两个不同的 phase_ids。尚无表面或只知道部分表面时，保留已知关系。界面不得跨项目，明确的表面归属必须与参与相一致。相同时存在不会生成界面，相对或表面对相同也不会合并界面 ID。 |
| 位点与物理容量 | 每个 site_id 隶属一个表面，位点类型是项目局部标签，B.2.1 按规范库存 ID 计数。 | 可由 interface_id 把某个库存限定到特定界面，适用于定义、人工位点映射、占位、空位和覆盖率。不同构型共享物理池时引用同一个 site_id；显式枚举成员时沿用 B.2.1 的重复容量检测。 |
| 物种位置 | species_id、物质状态、surface_ids、interface_id、结构与足迹已分别存储。 | 界面物种可以位于已登记接触面的一侧，也可以跨多个库存。单侧物种仅占用自己声明的表面。两个不同驻留位置可有不同物种身份及相同分子组成。气相物种无表面占位。 |

网络层继续使用原 catalog、物种指纹和内容寻址版本。新增的只读 `--identity-report FILE` 从同一目录输出按 ID 索引的归属、来源和问题；没有反应记录也可以审计。读取历史网络时先核对其原始内容版本。完整交换和网络构建对矛盾的已声明引用继续报错。诊断报告允许单独查看其他有效关系，不会把报告当作经过批准的网络。[契约说明](../../../modules/kinetic_data/multiphase_contracts.md) · [入口用法](../../../modules/reaction_network/README.md)

## 四个案例的实测结果

| 案例 | 相 / 表面 / 界面 / 库存 | 复核结果 |
| --- | --- | --- |
| 通用结构样例 | 3 / 4 / 3 / 4 | 两个不同相同属 film，ordered 有两个表面。contact-a 与 contact-b 具有**相同的两个参与相和相同的两个表面**，分别拥有 rim-a、rim-b。另一个三相界面仅声明参与相，表面列表为 null。四个库存都使用 anchor 标签，身份仍独立。样例反应数为 0。 |
| 既有 Ni/Cu 网络 | 2 / 2 / 1 / 2 | 从归档表面解析 junction 的参与相 fcc-Ni、fcc-Cu。原网络版本 `ccee8d834cb47dd351476361d5ef2339b178398046de7a78924bd1e0f4a41127` 通过内容核验。B.2.1 的 2 Ni-top + 1 Cu-bridge 重复单元及原有归一化结果通过回归。 |
| 合成氧化物 | 1 / 1 / 0 / 2 | oxide-alpha 拥有 oxide-012；酸位和氧位均属于该表面。双齿 CO₂ 保持一个分子身份，两个库存各计其贡献。原 fixture 未声明界面。 |
| 归档 Fe(110) | 0 / 1 / 0 / 0 | 原网络版本 `2a80b67c31201600a1858780bbe6c176b03f489fe24383441fca4f195b395483` 通过内容核验。零表示该快照中相应的目录行数。已知的是表面标识，所属相、结构引用和本例库存仍缺证。历史网络继续保持原有阻断状态。 |

一致重命名相、表面、材料、界面、库存和物种 ID，并倒置记录和参与列表顺序，逆映射后得到相同归属和物种可区分性。内容寻址的版本仍绑定原始输入，重新命名不要求得到相同的网络哈希。[四例机器回执](identity_validation.json) · [通用测试定义](../../../tests/fixtures/multiphase/synthetic_identity_domains.json)

## 来源、未知信息与适用范围

- 所有报告都记录输入文件的实际 SHA-256。结构来源字段记录外部工件路径和声明的 SHA-256，两者与报告输入文件摘要承担不同职责。只读入口核验结构来源的格式；确认外部坐标文件的实际内容仍须取得原件并核对字节。
- Ni/Cu 历史样例中两个体相、两个表面和一个界面引用的五个 synthetic XYZ 路径在本次发布工作树中无对应文件。保留原合成记录和网络身份，不据此声称五个结构已获独立核实。氧化物和通用样例也不因通过结构测试而获得实验或动力学资格。
- 对缺失的表面相归属，报告保留该表面的身份及已知库存。对未归属的参与相，报告列出待补的表面。网络不从材料名称、晶面标签、组成或另一条界面记录补全归属。重复主键会阻止按该主键建立唯一索引，需先消除歧义。
- 足迹未知时，受影响的库存仅限于该物种可能的表面和界面。审阅一个界面不能重分配另一界面专属的位点。没有实际物理成员或共享映射的证据时，单凭同名位点无法判断物理重叠。
- 若未来研究相间转移，已可分别标识两侧驻留状态。判断两者之间是否存在传输事件仍需独立的机理、计量和速率证据。本轮没有生成传输步骤、速率或执行计划。

## 变更文件

- 目录记录 schema：`configs/catalysis/phase.schema.json`、`configs/catalysis/surface.schema.json`、`configs/catalysis/interface.schema.json`、`configs/catalysis/active_site.schema.json`。
- 覆盖率报告的可选归属字段：`configs/kinetics/mkm_coverage.schema.json`。
- 契约与网络入口：`scripts/multiphase_contracts.py`、`scripts/reaction_network/catalog.py`、`scripts/reaction_network/builder.py`、`scripts/reaction_network/site_review.py`、`scripts/reaction_network/__main__.py`。
- 覆盖率归属读取：`scripts/baseline_mkm/kinetic_analysis.py`、`scripts/baseline_mkm/molecular_coverage.py`。
- 文档：`modules/kinetic_data/multiphase_contracts.md`、`modules/reaction_network/README.md`。
- 测试与 fixture：`tests/test_multiphase_identity.py`、`tests/fixtures/multiphase/synthetic_identity_domains.json`。
- 本目录：`identity_validation.json`、`completion.md`、`regression.md`、`handoff.md`。
- 状态事件：`modules/state_handoff/events/history-stage-b2-2-1-structural-identity-20261122.json`。

[双树验证](regression.md) · [State Handoff](handoff.md)
