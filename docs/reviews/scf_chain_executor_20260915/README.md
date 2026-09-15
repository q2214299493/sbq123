# 三阶段 SCF 恢复执行器：代码实现，未提交计算

2026-09-15。用户“可以”授权实现与测试限定范围的三阶段执行器；
不是对未审核生产输入的 VASP 提交授权。本轮未上传、提交、停止或重投任何计算。

## 实现范围

同一个 LSF allocation 最多运行以下三个固定几何静态阶段：

| 阶段 | 输入约束 | 放行条件 |
|---|---|---|
| A 固定原子密度 | ISTART=0、ICHARG=12；不读取已有电子态 | 数值电子残差、正常终止、实际参数、完整有限输出及几何通过 |
| B 自洽冷启动 | ISTART=0、ICHARG=2；禁止读取 A 的 WAVECAR/CHGCAR | A 通过；B 收敛；与审核基线比较总能、逐原子力矢量、局部及总磁矩；重启文件完整性检查 |
| C 重启复现 | ISTART=1、ICHARG=1；仅复制 B 已验证并绑定哈希的电子态 | B 通过；证明实际读取 WAVECAR/CHGCAR；同时比较基线与 B |

三阶段间只有 ISTART/ICHARG 可以不同。NSW=0、IBRION=-1、共线 ISPIN=2、
ALGO=Normal、LMAXMIX=4、LWAVE/LCHARG 开启；不支持其他方法/自旋分支混入。
本次待审核的并行方案仍为 80 ranks、NCORE=8、NBANDS=320；执行器不自行改参数。
POSCAR、晶胞、固定层、KPOINTS、POTCAR 及其物理分支必须先由原输入审核确认。

任一阶段失败，不启动下一阶段。软件异常或进程中断留下阶段目录，返回
UNKNOWN_NEEDS_RECONCILIATION，不会自动重算。已完成阶段恢复时重新核对原始
输入/输出哈希并重新计算阶段门；跨 allocation 恢复需要新审核，不能绕过提交保留记录。

## 权限与数据边界

- 新提交类型：`scf_repair_chain`；仍使用 canonical `SUBMIT_DIAGNOSTIC_VASP`。
- 根执行门要求额外的 `scf_chain_scope`：manifest SHA、三个阶段、最多一个
  allocation、禁止自动 retry。普通单点授权或口头“通过测试”不能替代此范围。
- canonical submit 在最终哈希复查后才向 bsub 传递 `SCF_CHAIN_PERMIT`。
  运行时再核对包、目标目录、LSF allocation 和可执行文件身份。
  这是项目受信任执行器的委托凭据，不是抵抗恶意主机管理员的加密签名。
- `scripts/ts_strategy_engine/execution_gate.py` 导出的阶段门负责放行；解析器只生成证据。
- A 仅为非自洽诊断，不能成为能垒、吸附能、训练标签或生产重启来源。
- C 通过仅标为 `NUMERICAL_REPAIR_VERIFIED`，`scientific_acceptance=false`；
  不自动启动 Dimer、登记 TS 或报告能垒。

## 阈值与审核

`scf_chain.json` 的 `policy` 必须显式提供：

- `geometry_A`：固定几何的输出舍入容差，单位 Å。
- `baseline` 和 `restart`：分别指定 `energy_eV`、`force_vector_eV_A`、
  `local_moment_muB`、`total_moment_muB` 的正数 `warning` / `stop`。

超过 warning 但不超过 stop 会记录 `PASS_WITH_WARNING` 并允许下一阶段；
超过 stop 才阻止后续执行。没有零容差默认值，也不把测试里的示例阈值带入生产。
实际生产阈值尚待审核，不能靠调大阈值追认已失败的数值分支。
这次没有证明 NCORE 调整一定解决根因；若 A 再失败，不自动追加混合参数试验。

## 命令与包结构

```text
python -m scripts.neb_agent.scf_chain_bundle --output RUN/scf_chain_runtime.pyz
python RUN/scf_chain_runtime.pyz --precheck --workdir RUN
python -m scripts.neb_agent.submission preflight --workdir RUN --kind scf_repair_chain
```

运行时为标准库 zipapp，包含当前版本 canonical 电子解析器和阶段门，
无需在 VASP 节点安装 ASE/pymatgen。构建和 precheck 不运行 VASP；已有 zip 不覆盖。
生产包需要 INCAR（与 A 完全一致）、A/B/C.INCAR、POSCAR、KPOINTS、POTCAR.spec、
baseline.json、scf_chain.json、精确匹配的 script.lsf、scf_chain_runtime.pyz。
POTCAR 仍由 canonical 提交流程在授权源复制，禁止打入发布包。

baseline.json 必须是审核后的真实基线，包含完整 state（能量、全部力与磁矩）、
geometry、原始 source_files SHA 和 review_status。生产封装时要回查原始来源，
不能把测试数据或手填“REVIEWED”当成真实审核。

每阶段生成 started.json、receipt.json 及原始输出；链级生成 scf_allocation.json。
WAVECAR 检查标准 VASP 5.4 复数文件头、记录长度、带数、ENCUT、晶胞和文件大小；
CHGCAR 检查几何和两套有限、完整的共线自旋网格。它们不是波函数物理有效性的证明，
实际读取和重启复现仍必须由 C 验证。

## 验证记录与未验证项

验证命令和结果见本目录 `validation.txt`（最终运行后生成）。测试全部使用合成
输出/模拟提交；测试中出现的作业号不是生产作业。已有真实 9752745 文件的只读复核
已读取 50 个力矢量和 50 个局部磁矩，正常终止及电子收敛均通过；
TOTEN=-388.28288317 eV，总磁矩=105.0208746 μB，实际 NCORE=1、NBANDS=320。
NCORE 必须读取 `distr: ... NCORES_PER_BAND=`，不能读取 VASP 横幅中的建议值 4。

尚未验证远端 Python 版本、LSF 凭据传递、真实三阶段执行、真实 B→C 重启文件，
也未证明数值根因已修复。下一步是封装并审核本次真实输入、阈值和运行环境；
通过后另行取得这一个三阶段作业的提交授权。
