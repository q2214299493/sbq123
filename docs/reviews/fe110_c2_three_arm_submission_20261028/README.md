# C₂三臂DFT正式提交

**用户最新“提交”指令已执行，三项均获得原生LSF提交回执。首次队列检查为北京时间2026-10-28 23:41:38，三项均PEND。** 不据此声称VASP已开始、SCF或力已收敛。

|路线|实际job ID|队列|首次状态|核数/最多离子步|
|---|---|---|---|---|
|原始共同起点直接DFT|9926805|Gkn_normal|PEND|32/300|
|NequIP终态后DFT|9926806|Gkn_normal|PEND|32/300|
|微调终态后DFT|9926807|Gkn_normal|PEND|32/300|

远端根目录：`~/sbq/Fe110/adsorption/c2_three_arm_20261028_v1/10_A/`，下为direct_dft、nequip_then_dft、finetune_then_dft。仅使用sunboquan-codex；未提交C₃、GPU或训练任务，未续算、重试、取消或改动其他作业。

## 输入与授权

三套来源和数值不变，详见[输入审核](../fe110_c2_three_arm_dft_20261028/README.md)。统一Fe45/C2/H3、Fe0–17固定、PBE/ENCUT400/Gamma5×5×1、ISPIN2、ISMEAR1/SIGMA0.20、EDIFF1e−5、EDIFFG−0.02、IBRION2/POTIM0.20、LORBIT11；MAGMOM均45*2.2、2*0.0、3*0.0。实际提交目录的18项核心输入SHA与原准备包一致。

用户授权见[user_authorization.md](user_authorization.md)。它对应这三套32核/300步输入的一次提交；不沿用旧四项80步DFT或GPU授权。历史5,742–6,504核时仅是三项均运行300步的线性参考，不是费用上限或本轮预测，无自动重试或续算。

原准备plan.json保留准备时的未授权/未提交字段，不原地改写。新提交组`calculations/fe110_reico_pilot300_20261022/c2_three_arm_submission_20261028_v1/`保存本次授权、门决策、独占提交保留、原生回执、scheduler证据及登记回读；当前执行事实以这些新证据为准。

## 提交前及执行核验

远端用户、VASP可执行文件、Intel环境、三项目标目录及提交保留均核对。目标目录和保留当时均不存在。账户MAX=128、RUN=32，本次新增3×32=96核符合余量；不停止已有9925065任务。调度器后续决定实际开跑顺序，首次PEND不等于没有提交。

实际Fe/C/H POTCAR家族和顺序为PAW_PBE Fe 06Sep2000、C 08Apr2002、H 15Jun2001；总586,593字节，全文SHA256为bd39c0ebfbbe6207bc8e1b976677b4687ae2d2956f5a74dc1dea3298adef063a，与既有批准分支一致。内容留远端；登记只记录路径、大小和SHA。

三项canonical adsorption_relaxation预检通过，分别绑定原始输入、work几何审核、数值配置、用户指令、远端目标和POTCAR，三个当前门均明确允许SUBMIT_VASP；实际提交通过scripts.neb_agent.submission执行器。原生执行器在bsub前再次核对远端输入/POTCAR，且每项独立回执，无重复提交。

## 任务登记及验证

登记前验证当前数据库schema、integrity_check=ok、foreign-key violations=0。把实际回执与同一次LSF查询分别绑定到3项任务，PEND按仓库JOB_ALIASES映射为workflow submitted；科学状态仍为Not assessed。

保存并审核的registry plan SHA为c5a03f1fe5947a9c7d7f71dfc05e2c7f13308a0732928848ef1e67d61a4ef22b，范围仅calculations/files/job_status_history/jobs。Codex在用户本次提交授权下审查该保存计划后，用approve_plan绑定审核，并按plan_sha256确认执行：3个calculation、3个job、3个status事件及57个file，共66 INSERT、0 UPDATE。66条逐项回读一致，三项均无results记录；未写科学接受、吸附能、TS、势垒或Excel数值。

主工作区提交前33项范围/来源/输入相关测试及24项共享canonical执行器测试通过，共57项；发布副本所含同范围测试亦通过。新提交/登记源语法及限定Ruff通过。登记计划在内存副本验证后应用，实际回读验证通过。未跑全仓库测试，未为验证而增加计算。

## 尚未验证和下一步

初始C–C为1.415/1.676/1.434 Å，两模型末态RMSD约0.816 Å，不能假定同一DFT最低点。SCF、总/局域磁矩、首步模型—DFT力差、最终0.02 eV/Å收敛、化学/吸附终态及实际加速均未审核。

下一次用户请求检查时，先核对三项队列和实际文件，再审核启动后的SCF、磁性及首步DFT力；只有达到相同经审核局部极小点后才比较离子步、SCF次数和核时。未创建定时或循环监控。

repo-state sync --safe-only仍因既有sbq_catalyst_agent_workflow.egg-info/PKG-INFO分类后变化退出2；未改动该无关文件，不声称managed任务视图已同步。
