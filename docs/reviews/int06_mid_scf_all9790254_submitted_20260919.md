# INT06–MID 固定结构 ALGO All 诊断已提交

2026-09-19，用户明确回复“提交”，授权上一条方案中的一项单点诊断，不授权整条 NEB、Dimer 或训练。

- 作业：9790254；后端：sunboquan-codex；首次现场查询 LSF PEND，尚不能称 VASP 已开始。
- 80 MPI 核，排除 gknew0440；原 GPU1635 image05 POSCAR 不变。
- 相对9789598输入，唯一显式 INCAR 变化：ALGO Normal → All。保留 NSW0、IBRION-1、EDIFF1e-7、NELM200、PBE/ENCUT400/Gamma5×5×1/ISPIN2/SIGMA0.20及原 MAGMOM。
- 冷启动，无旧 WAVECAR/CHGCAR；没有 ISEARCH、新混合参数或额外几何约束。
- POSCAR SHA256：`0bada36d9cb23959e3a956c97058eb09b35723a9750e099ea6f11f0941c58ece`。
- 输入包 SHA256：`2a677ddce3a6ba827668861526022e253a1c6dfa43a7c831e769cc434e7c0617`。

已验证：源计划哈希、唯一参数差异、几何及固定掩码、INCAR custodian PASS、diagnostic_static preflight PASS、当前执行门明确允许 SUBMIT_DIAGNOSTIC_VASP、远端 POTCAR 和完整输入哈希、提交回执。提交后抽查远端 POSCAR/INCAR/KPOINTS/script.lsf 哈希与本地相同。

准备过程中本地辅助脚本曾使用错误的预期状态名称，改用实际门状态并仅恢复授权绑定；首次 CLI 调用因 PowerShell 展开未加引号的 `~`，在创建提交预约前被拒绝。核实没有提交预约后修正引号；最终只有一个成功提交回执，没有重复作业。未修改执行门或提交器源码。

计算目录：`calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_mid_dimer_gpu1635_parent_scf_all_20260919/`。

远端目录：`~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_dimer_gpu1635_parent_scf_all_20260919`。

该计算仅诊断电子求解路线，不提供 TS 接受或势垒。下一次检查电子收敛、正常结束、完整有限力、总及逐原子磁矩；不以 DONE 或某一次很小的 dE 代替收敛。授权已由9790254消耗，不自动重投或追加其他计算。
