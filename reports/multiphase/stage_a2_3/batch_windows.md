# P3 第二组 · DRC 批次

基线为第一组 Windows 检查点 `247b13df5333661b48a6413f28f4d77128761874`。将既有 eligibility、scan、reuse、prepare 和批次 LIMITS 移至 drc_batch_plan。原 drc_batch CLI 保留旧函数入口；执行器和报告直接引用批次计划模块。报告使用 drc_pair_records 读取并核验扰动对。故障注入用例在新的 compare 查找位置注入，保留原拒绝断言。

两套 Windows 工作树均通过此前 140 项回归及 2 项新增回归，共 142 项通过、0 项失败。新用例约束原批次入口的别名和三模块到 CLI 的依赖边界。6 个变更 Python 文件均通过 py_compile 和 Ruff。扫描所有受维护 Python 导入（含局部导入）后，开发树 331 个节点、1160 条边，发布树 290 个节点、1056 条边。仅余 sensitivity_study 与 sensitivity_report 一组循环。

对照各树修改前快照，原批次计划、执行、CLI 和报告各函数 AST 相同。10 个批次 CLI 帮助及缺参路径的退出码和输出摘要一致。用封存的 phase3_2_1/result.json 离线重建 network_report.md，完整字节与原件一致，SHA-256 为 `8bdf53984cedc94740d005f797d7061c01a28bc49ce70a815e826f158eb2a756`。实际覆盖计划重建、批准绑定、预算、停首错和部分结果重用，未启动原生计算或写生产库。Linux 的独立数值身份待办仍保留。
