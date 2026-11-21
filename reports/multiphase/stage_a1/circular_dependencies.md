# 静态循环与运行影响

两个源树具有相同四组强连通分量，展开的直接边及双顺序导入结果见 [依赖图](dependency_graph.json)。此前失败测试只显示遍历时遇到的第一个环。

| 强连通分量 | 造成回边的职责 | 当前影响 | 后续处理 |
|---|---|---|---|
| scripts.native_model、scripts.baseline_mkm.native、scripts.surface_kmc.native、scripts.surface_kmc.lattice | 装配器选择渲染器，渲染器及晶格工具反向使用装配器定义的 conditions、integer 或 token。 | 延迟导入允许现有入口载入。领域与适配器层仍不可单向替换。 | P2 |
| baseline_mkm.drc_pair、drc_report | 扰动对的运行路径发布报告，报告读取扰动与核验逻辑。 | 变动格式会牵涉执行端加载。 | P3 |
| baseline_mkm.sensitivity_study、sensitivity_report | 研究流程调用报告，报告解析研究记录并使用研究模块定义。 | 单独复用估计或重放结果仍依赖研究编排。 | P3 |
| baseline_mkm.drc_batch、drc_batch_execution、drc_batch_report | 批计划、执行和报告互引批次定义与结果检查。 | 修复原生装配器一处仍不能通过整图无环测试。 | P3 |

后面三行的模块前缀均为 scripts。已实际测试每组的两个导入顺序。探针成功只验证导入时的表现，不能排除其他调用顺序或运行时初始化风险。优先保留已验收模型字节、签名、CLI、执行预算和部分结果恢复语义。
