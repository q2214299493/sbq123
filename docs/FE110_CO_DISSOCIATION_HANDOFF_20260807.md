# Fe(110) CO 解离完成交接

更新时间：2026-08-07（Asia/Shanghai）

## 当前结论

- 本任务范围已完成：Dimer TS 收敛、C/O 局部 Hessian 虚频验证、兼容电子能垒登记。
- 当前没有需要继续运行的 CO 解离 VASP/VTST 作业，也没有授权新的计算。
- 本结果是 `SIGMA=0.20 eV` 兼容分支上的电子能垒，不包含 ZPE、熵或自由能修正。

## 已接受结果

| 项目 | 结果 |
|---|---:|
| Dimer 作业 | `9656664`（DONE） |
| TS 最大原子力 | `0.016036 eV/Å` |
| 局部频率作业 | `9694935`（DONE） |
| 唯一虚频 | `537.451689 cm^-1`，mode 6 |
| 局部 Hessian 范围 | C/O，零基原子索引 `45, 46` |
| IS 能量 | `-372.01291708 eV` |
| TS 能量 | `-370.66270803 eV` |
| FS 能量 | `-372.71928137 eV` |
| 正向电子能垒 | `1.350209 eV` |
| 反向电子能垒 | `2.056573 eV` |
| 反应能 | `-0.706364 eV` |

能量约定：`fe110_converged_toten_sigma0p20_v1`，采用兼容 IS/TS/FS 最终 `OUTCAR` 的 `TOTEN`。

## 关键文件

- 结果摘要：`calculations/fe110_co_dissociation_neb_20260718/diagnostics/formal_barrier_sigma0p20_20260807/registration_summary.json`
- 哈希与兼容性清单：`calculations/fe110_co_dissociation_neb_20260718/diagnostics/formal_barrier_sigma0p20_20260807/formal_barrier_manifest.json`
- IS/TS/FS 结构：上述目录内的 `IS_job9558184/CONTCAR`、`TS_dimer_job9656664/CONTCAR`、`FS_job9622455/CONTCAR`
- Dimer 远程目录：`~/sbq/Fe110/ts/co_dissociation_topic1_20260718/dimer_handoff_job9640399_image04_20260803`
- Excel：`outputs/ts_topic1_20260806/课题一TS.xlsx`
- 数据库：`data/project_registry.sqlite3`
- 复用策略 ID：`fe110_co_dissociation_dimer9656664_sigma0p20_grade_a`

复用策略 ID 中的 `grade_a` 是已登记标识；本次正式完成范围仍是“电子能垒 + C/O 局部虚频验证”，不能据此宣称已得到自由能势垒或动力学可用数据。

## 后续复用规则

相似表面解离任务可以复用本次的路径构造、普通 NEB、Dimer 和局部频率策略；不得直接复制原子索引、MODECAR、端点坐标、能量或能垒。新体系仍需重新完成原子映射、端点兼容性、Dimer 收敛和目标虚频审核。

## 唯一可选后续工作

只有需要自由能势垒或动力学输入时，才另行计算采用一致局部活性集的 IS/TS/FS 热力学校正。该工作不属于本次已完成的电子能垒任务。
