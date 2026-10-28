# C₂H₃三臂DFT验收输入

**三套输入准备和审核完成后，用户明确要求“提交”；现已通过canonical执行器提交为9926805/9926806/9926807，首次23:41队列核对均PEND。** 本文件保留输入依据；本次执行授权与回执见[正式提交记录](../fe110_c2_three_arm_submission_20261028/README.md)。原准备plan.json的未提交字段保留为历史快照，不原地改写。不包括C₃。

输入根目录：`calculations/fe110_reico_pilot300_20261022/scratch512_speed2_20261028_v2/c2_three_arm_dft300_v1/`。

|目录|起始结构|此前ML步数|C–C，Å|两C最近Fe距离，Å（Fe零基索引）|
|---|---|---:|---:|---|
|direct_dft|共同原始10_A POSCAR原字节，未经过ML|无|1.415052|2.406365（41）/2.406365（41）|
|nequip_then_dft|冻结NequIP候选优化终态|34|1.676277|1.906111（41）/1.887627（41）|
|finetune_then_dft|冻结微调候选优化终态|60|1.433798|1.979251（43）/2.107711（41）|

每个目录包含POSCAR、INCAR、KPOINTS、POTCAR.spec、script.lsf、candidate_manifest.json，以及只读INCAR审核和submission_preflight.json。plan.json记录输入、来源、预算参考和无提交边界；input_verification.json记录独立复核。实际POTCAR按项目规范留在VASP服务器，本地只有物种清单Fe C H。

## 共同DFT设置

- 同一Fe45五层共同晶胞，底18个Fe固定，其余原子可动；元素顺序Fe45/C2/H3。三臂晶胞、固定位置与约束一致。
- PBE/PAW-PBE分支，ENCUT400 eV，Gamma5×5×1，ISPIN2，ISMEAR1，SIGMA0.20 eV。
- EDIFF1e−5，**EDIFFG−0.02 eV/Å**，NELM200、NELMIN5，ALGO Fast。
- IBRION2、POTIM0.20、ISIF2、ISYM0、LDIPOL=false；每项32 MPI核、最多300离子步。三项合计96核，未来提交仍须遵守账户128核及实时余量。
- MAGMOM均为`45*2.2 2*0.0 3*0.0`；LORBIT11输出逐原子磁矩。初始化相同不证明实际SCF会落在相同磁性分支，结果仍须审核。
- 新目录不带入历史WAVECAR、CHGCAR、CONTCAR或DFT输出。无自动续算、重试、GPU运行、训练或模型晋级。

INCAR、KPOINTS、POTCAR.spec和script.lsf在三臂之间逐字节相同。坐标及来源元数据分别绑定，不复制历史DFT结果。所有数值来自当前configs/true_fe110_production.yaml的routine_production及项目现有构建器；不采用skill通用示例中的较松参数。

## 来源及几何审核

原始直接DFT源SHA为04990eb8ae6dc84d9626dd0480220201664499f79c389d1c6070081325497d4b，独立复核确认该臂ML_performed=false、模型SHA及ML步数为空，POSCAR字节与原始源一致。NequIP后和微调后POSCAR SHA分别为0f2bc2ef2a49e1600dfed1c2d523a513d9f99d5ab8b71bbb2315a099d51d9fc2及f54659b82e5a7bb8c23780443e0878d85364c46b36c0276d683af2bce5c7cea1，均与已回收审核末帧一致，未调整坐标以改善结果。

三套结构都保留原始C₂H₃连接，未出现原子重叠、埋入表面或约束变化。原始/NequIP后/微调后最短非键距离分别为1.870392/1.766510/1.826786 Å，最近H–Fe分别为2.488319/2.293340/1.855822 Å；最低吸附原子均在最高Fe之上。没有O原子，不套用C–O几何判据。

**NequIP末态C–C为1.676 Å，明显长于另两臂；两模型C₂末态的吸附原子RMSD约0.816 Å。** 这属于待检验差异，保持源结构不变；不能假设三臂会落入同一个DFT局部极小点，也不能用此前34对60个ML步判断实际加速。三者的几何资格不是稳定吸附态或DFT低力的证明。

历史10_A的114步DFT任务使用不同POSCAR，不充当本次纯DFT基线。历史观察体系的属性保留，不称为新盲测；原512/78/53、16个观察隔离样本和磁性审核等级不变，本次没有纳入新训练标签。

## 未来验收和成本

分别审核正常终止、逐帧SCF、总/局域磁矩、可动原子DFT最大力≤0.02 eV/Å、真实化学状态/位点及相同局部极小点。只有达到相同经审核终态和磁性分支的路线才能计算加速比。不同终态、SCF失败或300步用尽仍不达标时，只报告状态和成本，不算成功加速，不自动续算。

保存ML接续首帧与模型末帧的坐标对应和力误差，重点区分可动Fe与吸附物；统计达到标准所需离子步、SCF总次数、VASP elapsed及分配核时。排队、ML推理、训练/标注摊销分开列出；不能以ML自身0.10目标代替DFT验收。若比较收敛能量，使用既定SIGMA0.20分支的兼容最终OUTCAR TOTEN；本次不准备缺少参考元组的吸附能计算。

旧10_A两项计时样本按三项均运行300步线性放大的参考量为约**5,742–6,504核时**。这是不同起点/节点/SCF难度的历史量级，**不是本次费用上限、耗时预测或收敛保证**，不作为本次速度基线；提前收敛会减少实际成本，排队另计。

后续正式提交阶段已核对sunboquan-codex实际PAW-PBE POTCAR顺序/SHA、32/128核占用及本次96核余量，并绑定用户“提交”指令和新门决策。三个门均允许SUBMIT_VASP，三项已分别提交；详见独立提交记录。原准备包的ALLOWED_ACTIONS为空只表示准备时状态，不代表后续提交未发生。

## 已执行验证

两份ML来源与原始共同起点绑定复核，三项几何检查、只读INCAR审核和统一提交预检通过；独立读取实际INCAR核对力标准、300步、50个MAGMOM与LORBIT，并复核18个核心输入哈希、三臂方法/资源一致及新目录无重启文件。55项相关来源、构建器、preflight和几何回归通过；新任务源语法和限定Ruff通过，未跑全仓库测试。

实际DFT力、SCF、收敛步数、磁性分支、同一终态和加速仍未验证。下一步按用户请求检查已提交三项的队列和实际计算文件；不自动重试或续算。

repo-state sync --safe-only仍被既有sbq_catalyst_agent_workflow.egg-info/PKG-INFO分类后变化阻塞，退出2；未改动该无关文件，不声称managed任务视图已同步。
