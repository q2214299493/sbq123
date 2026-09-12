# SCF9753658：保存原始中心的收敛电子状态

2026-09-12用户要求“按照这个思路开始吧”。当前执行第1步：原始中心固定原子的SCF，保存WAVECAR、CHGCAR，随后根据实际收敛与文件完整性决定重启验证。没有提交Dimer。

## 输入与验证

POSCAR、KPOINTS和运行脚本与成功的SCF9752745逐字节一致。现有仓库静态builder生成后保留该诊断已审阅设置，只有LWAVE和LCHARG从False变为True；ALGO=Normal、80核、PBE、ENCUT400、Gamma5×5×1、ISPIN2、Fe初始磁矩2.2、SIGMA0.20、EDIFF1e-7、NELM200、NELMIN5、NSW0、IBRION-1、LORBIT11均保持。新目录冷启动，未读入失败Dimer输出。

几何来源与固定层审核复用已验证的同一原始中心；INCAR静态检查、输入预检、POTCAR哈希和当前绑定执行门禁通过。启动脚本与已通过bash -n的SCF脚本完全相同。远端文件系统有可用空间；本次未读取个人配额，文件系统可用空间不代表个人配额已确认。

Canonical executor提交9753658，Gkn_normal，80核；2026-09-12T13:02:29Z调度PEND。远端：sunboquan-codex:~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_scf_save_state_20260912

## 后续判据

先检查调度DONE、程序正常终止、EDIFF电子收敛和几何不变。再检查WAVECAR/CHGCAR是否完成写入、非空、格式与结构/电子设置兼容并保存哈希；不能仅凭文件存在就认为可用。只有通过后才准备读取该电子状态的固定结构重启验证，检查能量和逐原子力的可重复性；通过重启验证后再评估短程Dimer。

若SCF再次发散，先诊断电荷/磁性混合及实际运行差异，不把未收敛的重启文件送入Dimer，不自动重试。本次只提交一个SCF任务；旧9749920和9753172保持停止。无有效迁移TS或势垒结论。
