# C₂/C₃ 固定坐标单点提交回执

2026-11-18 20:55（北京时间）复核了 `sunboquan-codex` 的整批 LSF 状态。9个已授权的固定坐标单点全部提交至 `Gkn_normal`，每点请求32核。LSF 记录5个135分钟、4个90分钟，按申请限时计552核时。

| 候选 | 作业号 | LSF限时（分钟） | 快照 |
|---|---:|---:|---|
| `family_0073_step006` | 7743 | 135 | RUN |
| `family_0054_step005` | 7744 | 90 | RUN |
| `family_0011_step004` | 7745 | 90 | RUN |
| `family_0081_step004` | 7746 | 135 | RUN |
| `family_0094_step005` | 7748 | 135 | PEND |
| `family_0078_step005` | 7749 | 135 | PEND |
| `family_0056_step006` | 7750 | 135 | PEND |
| `family_0018_step005` | 7751 | 90 | PEND |
| `family_0042_step005` | 7752 | 90 | PEND |

提交前，比对了9份输入预检、源 POSCAR、静态输入包及两套服务器 POTCAR 的哈希。每个作业都绑定本次用户授权、目标目录及预检通过的输入包。提交器核对服务器输入后发起 LSF 提交。登记库新增9条计算、9条作业、9条调度快照和126条文件来源记录。电子收敛、坐标—力对应和磁性仍待结果审核。

本次暂缓第4点，保留原后10个备选。复核的512/536训练包及冻结模型哈希一致，78/53/16分区未改动。本次重试、GPU任务和训练均为0。

本地证据位于 `calculations/fe110_reico_pilot300_20261022/c2_c3_label9_lsf_20261118_v1/execution_20261118_v1/`，包括 `scheduler_verified.json`、`scheduler_snapshot_raw.json` 和 `registry_receipt.json`。各点原始提交回执位于同批次的 `vasp_review_inputs/`。
