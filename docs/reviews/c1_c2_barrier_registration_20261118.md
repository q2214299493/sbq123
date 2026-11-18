# Fe(110) 两套电子能垒与策略登记 — 2026-11-18

新分析和引用审核副本位于 `outputs/c1_c2_barrier_registration_20261118_v1/`
的 `ch_co/`、`int06_mid/` 下。原始 VASP 结果和旧 Grade-A 验收均保留。
本轮只解析、审核、登记已有证据，不启动 VASP、频率作业、GPU 或 MKM。

## 两套当前审核

- CH＋CO：重生成 Dimer 分析，仅四个连通性说明字段与旧格式不同。
  以相同结构、末态模式和软残差重新绑定现有审核，再生成 VFA 分析。
- INT06→MID：原 CI-NEB 路径和目标振型不变，保存的频率判据与当前子配置一致。
  使用现行配置重新解析 VFA；当前门独立复验 CI-NEB 鞍点、端点绑定和几何审核。
- 两套 VFA 的 POSCAR/OUTCAR 都是原字节副本。频率、振型、Grade A、
  原子映射、反应契约及兼容指纹不变；未加做下坡连通性测试。
- 两份新门禁均为 `VALIDATED_TS`，含 `APPROVE_TS_CANDIDATE`，
  而且分别绑定精确能垒记录申请。正式能垒仍由登记 owner 校验能量链和策略后写入。
- IS/TS/FS 同属 PAW-PBE、ENCUT=400 eV、Gamma 5×5×1、ISPIN=2、
  ISMEAR=1、SIGMA=0.20 eV 生产分支；两套分别核对原子顺序、晶胞、
  固定层、电子收敛及最终输出。两段各用自己的兼容指纹，未跨段相减。

## 登记与验证

两套能垒与对应 Grade-A 策略均已登记，并由数据库读回验证。

| 反应段 | IS / TS / FS | 正向 (eV) | 反向 (eV) | 反应能 (eV) |
|---|---|---:|---:|---:|
| CH＋CO → CH–C–O | 9839757 / 9998592 / 9842136 | 0.97360174 | 0.31429371 | +0.65930803 |
| INT06 → MID（表面 H 迁移） | 9748648 / 9796856 / 9737143 | 0.16732341 | 0.09964185 | +0.06768156 |

- CH＋CO：`fe110_ch_co_sigma0p20_review_20261118`；策略
  `fe110_ch_co_grade_a_strategy_20261118`。
- INT06→MID：`fe110_int06_mid_sigma0p20_review_20261118`；策略
  `fe110_int06_mid_grade_a_strategy_20261118`。
- 回执：输出根目录的 `energy_receipt.json`、两套
  `barrier_registration_receipt.json` 与 `registration_verification.json`。
  SQLite quick_check、外键、原验收记录与文件哈希、策略证据及数值读回均通过。

鞍点能量使用独立于吸附松弛的窄入口：要求当前门禁、已登记 Grade-A 记录、
原鞍点 OUTCAR 哈希、兼容设置、收敛及实际末步 TOTEN 一致。
12 条前置记录的 canonical registry plan 在内存快照验证并按授权写入，全部为追加。
原作业调度历史保留；沿用已存终态证据，不把本次科学审核冒充新调度查询。
CH＋CO 初态使用此前审核通过的重分类共吸附状态，不改写原 C₂HO 目标的拒绝。
相关回归 182 项、Python 编译和范围内 Ruff 检查通过。

本次能量的约定是 `fe110_converged_toten_sigma0p20_v1`，仅为电子能垒；
不能直接当作活化自由能或定量 MKM 速率输入。策略只迁移路径构造、选峰、
精修和振动验证方法，不迁移具体构型、索引、坐标、模式或能量。

RSI 未另行调用：本轮按明确授权执行已有分析重绑定和确定性的登记校验，
不需要模型提供新科学意见。
