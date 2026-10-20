# Fe(110) 11–15 初始吸附构型

最终包是 `candidates_v3/`：五种精确分子图，每种三个 POSCAR，共 15 个。

- [结构、文献依据、数值几何表与五张结构图](candidates_v3/structure_review.md)
- [独立初始几何及对称去重核验](initial_geometry_verification.json)
- [实际执行的语法、导入、Ruff、22 项测试及空检索记录校验](validation_commands.json)
- [白名单检索范围](retrieval/whitelist_search.json)
- [原始论文适用边界](retrieval/literature_context.json)
- [明确构造请求](../../configs/adsmind_lite/fe110_c2_11_15_exploratory_20261020.json)

15 项初始几何均通过，软警告 0 项；最小同物种种子 RMSD 为 0.4398 Å。
未进行 GPU 推理、预弛豫、VASP、能量提取、注册表或 Excel 写入。
文献没有给出每种三个可核验的最低能坐标；构造姿态不是已确认最稳态。
下一步：审阅 15 个候选，再决定单独的预弛豫范围。

旧 `candidates_v1/`、`candidates_v2/` 和失败的空 `verification.json`
仅在本地保留，不作为最终交付；具体修正记录见 `preparation_notes.json`。
