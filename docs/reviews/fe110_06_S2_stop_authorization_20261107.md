# 06_S2 单作业终止授权

2026-11-07，用户针对06_S2作业9963758已出现C-O断键趋势、仍未收敛的诊断，明确回复：

> 可以停止了

唯一授权动作：在sunboquan-codex上终止LSF作业9963758。目标目录为 `~/sbq/Fe110/adsorption/c2_site_supplement_20261107_v1/06_S2`。

终止前核对当前原生调度状态与作业绑定，生成当前哈希绑定STOP_JOB门，由canonical executor调用bkill；之后核验原生终态。保留输入、CONTCAR、XDATCAR、OUTCAR、OSZICAR和已取得的诊断快照。不删除数据，不重投、不改参，不将未收敛结构/能量录为正式完整吸附态；其余9个VASP作业不停止或修改。
