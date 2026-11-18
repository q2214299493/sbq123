# C₂/C₃ 首批十点补标预检与冻结536两帧入口

首批10点通过本地 `diagnostic_static` 预检。每点对应一个真实 REICO 坐标。后10点只保留 ID，没有为其生成输入。本轮 GPU 推理、训练和 VASP 提交均为0。

| 排名 | 候选与组成 | 补足的几何成键或 Fe 接触环境 | 最近已有标签及完整几何距离 | 历史中位／建议上限，核时 |
|---:|---|---|---|---:|
| 1 | `family_0073_step006` C₃H₂O | C–C、C–O、C–H 并存，三个 C 的 Fe 接触数为 0/1/2，O 未接触 Fe | `family_0073_step000`，0.173 Å | 20.88／72 |
| 2 | `family_0054_step005` C₂H₂O | C–C 与 O–H 并存，两个 C 各接触 3/4 个 Fe，两个 H 各接触 1 个 Fe | `family_0054_step000`，0.157 Å | 19.60／48 |
| 3 | `family_0011_step004` C₂H₃ | 最近标签已有 C–H，本帧增加几何 C–C 接触，两个 C 的 Fe 接触数仍为 0/1 | `family_0011_step000`，0.127 Å | 19.67／48 |
| 4 | `family_0001_step002` C₂HO | C–O 与 O–H 并存，在默认截断下 O 的 Fe 接触数从 2 变为 1，两个 C 均未接触 Fe | `family_0001_step000`，0.054 Å | 21.26／72 |
| 5 | `family_0081_step004` C₃H₂O | 在已有 C–O、C–H 环境上增加几何 C–C 接触，C 的 Fe 接触数保持 0/0/4 | `family_0081_step000`，0.144 Å | 20.88／72 |
| 6 | `family_0094_step005` C₃H₂O | 一个 C–C 与两个 C–O 接触并存，锚定 C 的 Fe 接触数从 3 变为 4 | `family_0094_step000`，0.130 Å | 20.88／72 |
| 7 | `family_0078_step005` C₃H₂O | C–C 与两个 C–H 并存，C 的 Fe 接触数为 0/1/1，O 与一个 H 各接触 2 个 Fe | `family_0078_step000`，0.147 Å | 20.88／72 |
| 8 | `family_0056_step006` C₃H₂O | 两个 C–C 接触连成三碳骨架，锚定最强的 C 接触 2 个 Fe，O、H 仍在多组分环境中 | `family_0056_step011`，0.164 Å | 20.88／72 |
| 9 | `family_0018_step005` C₂H₂O | C–C、C–O、O–H 并存，两个 C 各接触 2 个 Fe，O 和 H 均未接触 Fe | `family_0018_step000`，0.164 Å | 19.60／48 |
| 10 | `family_0042_step005` C₂H₂O | C–C、C–O 与两个 C–H 并存，O 的 Fe 接触数从 0 变为 1 | `family_0042_step000`，0.155 Å | 19.60／48 |

表中所有配位数按默认 1.25 倍共价半径截断计算。成键图只描述几何接触。第4点靠近已有标签，保留它的依据是所核对的三个截断下联合成键与配位类型均落在现有覆盖之外。优先复核这处接触变化的物理收益。

10点都未命中已审核目录的同坐标 DFT 力标签，也未命中历史280份静态输入的 ID 或结构哈希。最近标签只用于解释要补的环境。逐点重新核对原坐标和元数据哈希、固定18 Fe、晶胞、最短接触、原训练家族与保护分区距离，并复算首批45个几何对照。参考范围见完整证据中的 `closest_existing_catalog_label`、`closest_existing_path_reference` 和 `nearest_label_signatures` 字段。未登记的其他来源不在该目录核查范围内。

首批总计 **204.11历史中位参考核时，624建议核时上限**。每点32 MPI ranks，48核时对应90分钟，72核时对应135分钟。参考取自四种组成各6个兼容历史单点，逐点预算沿用此前两倍 P90 向上取整的规则。当前项目本地 LSF 模板没有绑定这些调度限时，执行前须落实限时并生成对应授权门。

所有输入保留原始 POSCAR 字节，按当前项目的力标签分支生成 `PBE/PAW-PBE`、400 eV、Gamma 5×5×1、`ISPIN=2`、`ISMEAR=1`、`SIGMA=0.20 eV`、`EDIFF=10⁻⁶ eV`、`NSW=0`、`IBRION=-1` 和 `LORBIT=11`。POTCAR 规格为 `Fe C H` 或 `Fe C O H`，两套服务器文件的 SHA256 都用只读查询核对了已有兼容来源。标签回收后还需检查电子收敛、同坐标全原子力、局域磁矩和相应准入资格。

- [逐点补标预检CSV](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_c3_label_preflight_20261118_v1/首批10个补标预检.csv)
- [10份审阅用VASP输入目录](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_c3_label_preflight_20261118_v1/vasp_review_inputs)
- [输入、后备ID及预算证据](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_c3_label_preflight_20261118_v1/review.json)
- [本地验证](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_c3_label_preflight_20261118_v1/local_verification.json) · [服务器POTCAR哈希](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_c3_label_preflight_20261118_v1/remote_POTCAR_hash_check.json)

冻结536专用入口为 [run_pair.py](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_c3_label_preflight_20261118_v1/pair_inference/run_pair.py)，绑定 [两帧请求](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_c3_label_preflight_20261118_v1/pair_inference/request.json)。`verify` 用已绑定的请求 SHA、原坐标和模型校验本地输入。已实测通过，错误请求哈希、有效请求哈希下增加第三帧以及无授权运行均被拒绝。`run` 需要选定主机专用授权、相同的原生 AQCat25 运行源哈希、Slurm 分配与 CUDA UUID 核对、限时及新输出目录。计算口径是原生 ASE FP32、`tags=0` 和 `apply_constraint=False`，每帧只保存49×3个原始力分量。实际 GPU 运行仍未验证。

仅这两帧对应的既有 DFT 参考后续可直接用于逐原子力比较。512/536数据包、78/53/16分区、冻结权重和原任务指针的哈希一致。C₄在本轮筛选范围之外。

RSI 完成3轮、8次资料读取，匹配经验0条。它建议保留首批排序并逐点核查标签命中和预算。RSI 读到的长CSV行有截断，表中的完整标签与成本结论来自本地核验。[RSI记录](C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/runs/20261118_200445_3e5e91f1/review.md) · [看板](C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html)
