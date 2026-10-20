# Fe(110) 11–15 初始吸附构型

最终包是 `candidates_v5/`：五种精确分子图，每种三个 POSCAR，共 15 个。
后续复核修正了第 12、13 项共六个近线性 C–C–O 模板，其余九个保持原始字节。
15/15 通过扩大后的初始几何检查；这不是弛豫稳定性或最终最低能验收。

- [最终结构、逐项合理性表与五张结构图](candidates_v5/structure_review.md)
- [最终 POSCAR 的独立分子图、键长和固定层回读](candidates_v5/independent_readback.json)
- [33 项相关测试、语法、导入及 Ruff 的实际输出](geometry_review_validation.json)
- [旧 v3 复核中发现的六个待修正线性中心](candidates_v5/previous_version_chemical_audit.json)
- [白名单检索范围](retrieval/whitelist_search.json)
- [原始论文适用边界](retrieval/literature_context.json)
- [明确构造请求](../../configs/adsmind_lite/fe110_c2_11_15_exploratory_20261020.json)

15 项初始几何均通过；最小同物种种子 RMSD 为 0.8076 Å。
未进行 GPU 推理、预弛豫、VASP、能量提取、注册表或 Excel 写入。
文献没有给出每种三个可核验的最低能坐标；构造姿态不是已确认最稳态。
下一步：审阅 15 个候选，再决定单独的预弛豫范围。

旧 `candidates_v3/` 及此前交付包保留来源，不再作为最新版使用。
本地草案 v1/v2/v4 同样保留。具体修正记录见 `geometry_review_notes.json`。
