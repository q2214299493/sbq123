# 新旧模型C₂/C₃配对DFT：四项已正式提交

2026-10-27。**用户明确确认的四份冻结输入均已通过规范`SUBMIT_VASP`门和执行器提交成功；四份独立成功回执及初始调度证据齐全。首次快照均为PEND，未审核电子、力、磁性或最终结构，不宣称加速。**

## 作业与范围

以下调度状态来自同一次精确四作业号LSF查询，客户端北京时间2026-10-27 **22:20:52**。

|配对体系|模型来源|VASP作业号|首次调度状态|
|---|---|---:|---|
|10_A C₂H₃完整候选|旧control|9925060|PEND|
|10_A C₂H₃完整候选|新512|9925063|PEND|
|05 C₃来源的CO＋C₂H₂候选|旧control|9925062|PEND|
|05 C₃来源的CO＋C₂H₂候选|新512|9925065|PEND|

四个原始ML起点/权重和247帧审核见`docs/reviews/fe110_pair2_20261027/README.md`。C₂旧/新模型用47/48步达到ML目标；C₃旧68步达到ML目标、新80步用尽仍有0.228697 eV/Å，且两条C₃轨迹均失去原C–C连接。**本轮C₃是解离候选的DFT诊断，不是完整C₃成功、真实DFT断键或稳定性证明。** 不隐藏该负面结果，不追加ML步数或重新选模。

每项32MPI核、每节点32核、最多80离子步、DFT可动原子力标准0.02 eV/Å、EDIFF1e−5、LORBIT11。保持已审核Fe45五层/底18固定、PBE/PAW-PBE、ENCUT400 eV、Gamma5×5×1、ISPIN2、ISMEAR1、SIGMA0.20 eV、IBRION2/POTIM0.20和按物种生成的2.2/0初始磁矩。两模型之间的方法和资源输入不变。

仅使用`sunboquan-codex`，队列`Gkn_normal`。提交前账户MAX仍为128、RUN为32；按既有配额排队，没有停止其他任务或修改调度限制。首次四项PEND的具体排队原因未另行诊断。

远端根：`~/sbq/Fe110/adsorption/force512_paired2_20261027_v1/`，下为`{10_A,C3_05}/{control,new512}`。

本地提交证据：`calculations/fe110_reico_pilot300_20261022/paired_submission4_20261027_v1/`；其中`inputs/{10_A,C3_05}/{control,new512}`保留四份精确执行副本。原`paired_relaxation2_20261027_v2/dft_screen80/plan.json`及24个输入字节未改变，原暂停的05/07完整分子DFT目录没有恢复。

## 授权和实际执行核对

用户针对明确的四项、32核/80步/0.02标准、约1,670–1,890核时历史参考（不是上限）答复：“提交全部4项（推荐，完成C₂/C₃配对诊断）”，见`user_authorization.md`。本次只更新这四份输入的授权与提交状态，不改原准备包中历史的`VASP_execution_authorized=false`投影。没有自动续算、重试、新GPU、训练或模型推广。

本轮结果按冻结模型的评估证据保留，不自动回填512训练包或用作重新选模；10_A的既有整作业/家族隔离继续有效。

执行前逐项核对24个输入哈希和规范吸附预检。新执行副本保持四个原bundle哈希；四个独立授权绑定当前workdir、目标目录、输入bundle、规范门证据和POTCAR来源。

两套POTCAR只在VASP服务器读取并检查：PAW-PBE家族、Fe-C-H/Fe-C-O-H顺序及全文SHA均匹配此前审核分支。规范执行器复制后、`bsub`前再次核对远端全部输入及POTCAR哈希。未下载POTCAR内容或发布密钥。

四个远端目标及reservation提交前均不存在。四份本地/远端独占reservation和四份成功`submission_record.json`一致；四个作业号互异，每份成功回执绑定原bundle及实际执行门SHA。没有未知提交状态，没有重复提交。

首次只读预检在55秒后超时，未上传或提交。随后TCP/SSH身份检查及带分阶段计时的完整只读检查均成功；原超时的具体原因未确定。复用600秒以内、SHA绑定且目标集合完全一致的成功只读快照，再形成四个执行门。原失败诊断完整保留，没有因此重试任何计算。

## 来源登记与验证

已按规范append-only plan/review/apply登记**88条元数据**：4 calculations、4 jobs、4 job_status_history、76 files；全部INSERT、零UPDATE、零科学结果。这里是四个任务的作业/文件来源，不是88个结构或结果。4份POTCAR作为remote-only许可输入记录，内容不入Git。

注册plan SHA：`736186f814db0cf550ec05790704b3eaf4c056134ae657bc76c5fb69121f295a`。已检查保存plan仅涉及上述四表和四个实际作业号，再绑定审核、应用并逐项回读88行。24个提交输入、四个规范门/实际回执和四个reservation的独立一致性复核通过。

主工作区153项、发布副本136项相关测试通过；均无失败或跳过，显式文件语法、限定Ruff和diff空白检查通过。覆盖新增四项范围/重复提交拒绝、规范执行器、执行门、LSF证据、吸附预检及registry写入；主工作区另含既有registry CLI测试，未为数量一致复制无关旧测试。测试没有启动额外科学计算。

规范证据文件为`ready_for_submission.json`、四份`submission_record.json`、`submission_completed.json`、`submission_summary.json`、`submission_integrity.json`及`registration_verification.json`。初始调度快照只证明PEND；不把调度完成、SCF收敛、离子/力收敛、几何有效和科学接受合并为一个状态。

仓库管理投影仍受既有`sbq_catalyst_agent_workflow.egg-info/PKG-INFO`分类后变化阻塞；未修改该无关文件或自动批准管理投影。

## 下一步

下一次按用户请求检查这四个作业的实时调度和计算文件。完成后分别审核正常终止、逐帧SCF、磁矩、坐标—力对应及DFT最大力≤0.02，再核对真实化学身份、位点和同一最低点。只有兼容且同一经审核终态的配对，才比较离子步、SCF总工作量、VASP耗时、CPU核时及分别列出的GPU/标签/训练共享成本；尚无实测加速比或本轮实际核时结论。未创建定时监控。
