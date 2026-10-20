# 三组配对 VASP 松弛输入审核

2026-10-20；状态：`PREPARED_LOCAL_ONLY`。6/6 标准吸附预检通过。
本次授权只有准备，没有上传、提交、新 GPU 计算、训练或模型晋级。

## 配对范围

目录：`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/`。
每个构型下的 `baseline/` 和 `candidate/` 分别来自原始 AQCat25 与冻结微调 uniform-control 的同起点预松弛结果。
两者使用同一个原始 seed，但 VASP 实际起点是各自已审核的 **seed-origin 最终 POSCAR**；不是 minimum-drift 结果，也不是旧 VASP 最终结构。

| 配对 | 连接形式 | 原始模型起点 | 微调模型起点 |
|---|---|---|---|
|06_C|`[C]O[CH]`|`06_C/baseline/POSCAR`|`06_C/candidate/POSCAR`|
|09_C|`[C]O[CH2]`|`09_C/baseline/POSCAR`|`09_C/candidate/POSCAR`|
|10_A|`[CH][CH2]`|`10_A/baseline/POSCAR`|`10_A/candidate/POSCAR`|

原始 checkpoint SHA：`e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50`。
冻结 control SHA：`cfcac123cd56b866a1ea36cc780a3aee634f3aeec979bda4ae8bee2cc831e523`。
没有在本次几何结果上重新选 epoch/checkpoint。

## 统一输入与资源

由 `scripts.vasp_inputs.build_fe110_adsorption_relaxation` 读取当前生产配置生成，不复制旧作业模板。

- PBE/PAW-PBE、ENCUT=400 eV、Gamma 5×5×1；五层 Fe45、15 Å 真空。
- Fe0–17 固定；保持原子顺序、晶胞和全部 Selective Dynamics。
- ISPIN=2；逐物种生成 Fe=2.2、其余原子=0 的 MAGMOM。
- ISMEAR=1、SIGMA=0.20 eV、EDIFF=1e-5、EDIFFG=-0.02 eV/Å。
- ALGO=Fast、IBRION=2、POTIM=0.20、ISIF=2、NSW=300、NELM=200。
- 每任务32 MPI核、每节点32核、OMP_NUM_THREADS=1；仅规划 `sunboquan-codex`。
- 全新目录，无 WAVECAR/CHGCAR/旧优化历史；不额外安排 pilot。

每组四个文件 `INCAR/KPOINTS/POTCAR.spec/script.lsf` 字节哈希一致。
每任务最多300离子步，六任务合计预算上限1800步；这不是预估实际耗时。
六任务若全部同时运行合计192核，**尚未授权并发占用**；正式提交仍需依据当时配额安排。

POTCAR 正文只保留远端。06_C/09_C 使用已登记 Fe-C-O-H 文件及
`e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85`；
10_A 使用 Fe-C-H 及 `bd39c0ebfbbe6207bc8e1b976677b4687ae2d2956f5a74dc1dea3298adef063a`。
这是历史兼容绑定，不是本次实时远程验证；提交前必须再次核验。

## 几何摘要与保留警告

距离单位 Å，索引零基。完整来源、逐原子最近 Fe 和分子内距离在每个 `candidate_manifest.json` 中。
下面的最短原子距包含正常分子内键，不能直接解释为非键碰撞。

| 起点 | C45–O47 / C46–O47，或 C45–C46 | 最近 C–Fe | 最近 O–Fe | 最短原子距 |
|---|---:|---:|---:|---:|
|06_C 原始|1.4370 / 1.3817|C46–Fe43 1.8009|O47–Fe41 2.6323|1.1025|
|06_C 微调|1.4598 / 1.3806|C45–Fe44 1.8937|O47–Fe41 2.3481|1.1004|
|09_C 原始|1.4996 / 1.3623|C46–Fe43 1.8990|O47–Fe44 2.6464|1.0972|
|09_C 微调|1.5002 / 1.3522|C46–Fe43 1.8782|O47–Fe44 2.6210|1.0985|
|10_A 原始|C–C 1.4332|C45–Fe43 1.9851|不含O|1.0916|
|10_A 微调|C–C 1.4320|C45–Fe43 1.9960|不含O|1.0942|

六个最终分子图均保持原连接形式；固定层和晶胞检查通过。
但分子图相同**不保证同一吸附盆地**：06_C 的 C46 最近 Fe 为原始 Fe43、微调 Fe40。
06_C 两条 ML 轨迹曾短暂 C46–O47 伸长至约1.85–1.87 Å，最终恢复；该警告保留，不以距离阈值直接判成真实断键。
09_C 的吸附物 RMSD 没有改善，不能宣称三组均改善。
06_C 是训练源内诊断；09_C/10_A 已用于观察验证，三组不是新的盲测集合。

## 已执行检查

- 上游修正后的 v2 审核、返回清单、请求、轨迹审计的哈希核验。
- 六个源 POSCAR 的 review/return 双重绑定；复制后保持原字节。
- 固定层、原子顺序、晶胞、有限坐标、最终分子图复核。
- 6/6 `scripts.neb_agent.submission.preflight(kind="adsorption_relaxation")` 通过，含标准输入与已有失败重试历史检查。
- 三组方法/资源文件逐字节配对一致、无旧重启或结果文件。
- 本次准备代码与相关输入/预检测试：22通过。

首次测试收集因测试文件相对导入失败，已改为绝对导入后重跑22项通过；两次 XML 均保留。未因此运行任何科学计算。
机器清单 `batch_manifest.json` 绑定六包输入和各 `submission_preflight.json`。
清单明确 `execution_authorized=false`、`ALLOWED_ACTIONS=[]`、`NOT_SUBMITTED`。
最终准备回执为 `preparation_receipt_v2.json`。首次登记器错误地在渲染后的任务正文查找事件ID，
写出初版回执后停止、未写事件；已改为检查规范 projection manifest，初版回执原样保留。
这不改变六个输入、预检结果或科学结论。

## 完成后的比较规则

先分别审核正常终止、电子收敛、可动原子力收敛、化学身份和最终吸附盆地。
只有相容且到达同一经审核稳定态的配对，才能比较离子步、总SCF迭代、VASP耗时和CPU核时。
最终落入不同盆地或未收敛的情况应如实列为结果，不能算有效加速倍数。
另计各臂 ML 预松弛耗时，并单列 GPU、训练与标签成本及明确的摊销方式；排队时间不混入计算加速。
旧 VASP 的131/101/114步不是本次精确配对对照，不据此宣称加速。
当前只证明输入准备与一致性，**没有证明节省 VASP 步数或总成本**。

下一步：用户单独授权这六个精确哈希输入的正式 VASP 提交后，才生成当前执行门、实时复核远端 POTCAR/重复提交保护并安排运行。
