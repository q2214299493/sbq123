# Fe(110) 定向补充14份任务提交 — 2026-10-25

**已成功提交12个新单点和2个最多80步优化，共14份。14份原生回执齐全，没有重试、不明提交结果或扩大范围。**

首次提交后LSF快照：**2026-10-25 23:44:46 北京时间，2个RUN、12个PEND**。RUN/PEND仅表示调度状态，不能证明VASP电子收敛、离子收敛或科学标签合格。

## 作业清单

|构型|组成|用途|LSF作业号|首次快照|
|---|---|---|---|---|
|family_0010_step015|C2H2O|单点|9922611|RUN|
|family_0021_step004|C2HO|单点|9922612|RUN|
|family_0022_step006|C2H2O|单点|9922613|PEND|
|family_0024_step007|C3H2O|单点|9922614|PEND|
|family_0033_step005|C2HO|单点|9922615|PEND|
|family_0041_step016|C2HO|单点|9922616|PEND|
|family_0048_step005|C3H2O|单点|9922617|PEND|
|family_0055_step015|C2H3|单点|9922618|PEND|
|family_0061_step005|C2H2O|单点|9922619|PEND|
|family_0072_step007|C3H2O|单点|9922620|PEND|
|family_0079_step014|C3H2O|单点|9922621|PEND|
|family_0097_step017|C3H2O|单点|9922622|PEND|
|family_0099_step020|C3H2O|最多80步优化|9922624|PEND|
|family_0023_step020|C2H3|最多80步优化|9922625|PEND|

两个优化分别用于尝试补C3H2O完整近稳定帧（9922624）和10_B以外的C2H3低力来源（9922625）。不保证80步收敛，不自动续算。全部为32MPI核，PBE/ENCUT400/Gamma551/SIGMA0.20/ISPIN2/LORBIT11，Fe45与底部18固定Fe保持原样。

## 已执行的提交检查

- 用户在明确的14份范围和867.78–1022.75参考核时提示后回复“1提交”；原文及上下文冻结在user_authorization.md。授权不包含两个备选、暂停05/07来源、额外重试/续算或模型训练。
- 提交前busers实查账户MAX=128，NJOBS/RUN/PEND均为0；VASP可执行文件和Intel环境存在。14个目标目录及预留锁均不存在。
- 两种远端POTCAR的PAW_PBE家族、Fe/C/O/H或Fe/C/H顺序及SHA256与审核输入相同；POTCAR正文未下载或加入Git。
- 原生execution_gate生成并验证12个SUBMIT_DIAGNOSTIC_VASP和2个SUBMIT_VASP门禁。逐项由scripts.neb_agent.submission执行：独占本地/远端预留、仅上传绑定文件、在目标目录复核全部输入和POTCAR哈希，再调用bsub。
- 14份成功回执与授权目标、bundle及gate哈希一致；最终输入哈希重查通过。原生预留/回执保留在各自输入目录中，不能从准备时的历史submitted=false字段推断当前未提交。
- 以这14个真实作业号一次查询LSF；全部调度证据通过原生schema及raw-query哈希检查。没有把不属于本批的9922623计入。

## 登记与验证

本次仅登记14个calculation、14个job、14条初次调度观测和246条输入/来源文件元数据，共288条INSERT，0条UPDATE。14个POTCAR文件只记录远端位置与哈希/字节数；未复制许可正文。原始采样来源或已审核DFT标签的父记录均保留。

登记计划先在内存快照验证并单独复核，随后经原生registry-write计划哈希/数据库指纹审批与事务写入；288条记录全部回读一致。这14项对应的科学results表记录数为0，没有把提交、RUN或PEND当作合格标签或最终吸附能。

计划SHA256：`ad6d8b1e028bc4b3844605012c8fc4c673a156993c5fbf369ad57f52e18e77cd`。

主工作区119项直接相关门禁/提交/调度证据测试通过；新代码语法与Ruff通过。发布副本另执行新任务测试，实际结果见checkpoint.json。14个原生回执、72份上传输入文件的哈希及288条登记回读检查通过。原485帧审核视图、366帧训练包、分区和磁性审核等级未改；没有训练新模型。

初次登记回读脚本把CLI摘要字段insert_count误当成保存回执字段，在数据库读取前报错。检查真实保存回执后改用inserted/updated，完整回读通过；没有重复apply，失败说明保存在本地。

本地提交证据：calculations/fe110_reico_pilot300_20261022/grouped_submission_20261025_v1/。输入和每份原生预留/回执：calculations/fe110_reico_pilot300_20261022/grouped_inputs_20261025_v1/。远端新根目录：~/sbq/Fe110/reico_grouped14_20261025_v1/。同目录jobs.json为精确14项提交清单与首次快照，checkpoint.json保存验证绑定。

## 尚未验证与后续

电子SCF、逐帧局域磁矩、几何变化、DFT力/低力覆盖、新模型精度和实际优化加速均未审核。优化中的新训练帧仍需按真实轨迹逐帧审核和隔离，解离或磁性异常不能当成完整低力锚点。

下一步是在后续检查中按完成批次回收，先审核SCF、磁矩和原始力/坐标对应，再决定数据纳入；不自动训练或扩充计算。
