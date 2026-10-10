# Fe(110) C₂ 吸附专用 AQCat25 微调包审核

本次完成本地准备与数据检查，**未提交训练、GPU 预测或新的 VASP 作业**。
这是吸附预松弛力模型候选，不是 TS 微调，不更改 VASP 物理参数、现用模型或吸附能数据库。

## 本次审核对象

最终包：`calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_review_v3/`

入口：`training_request.json`

请求 SHA256：`2e1b517270395b414c8e7079cf95df93656014e24ce2db3f1e6b5e0ac3c40d16`

清单 SHA256：`12a6f0e9cc94a2dad33086b7fe81c7cc4ae8f3a7ec3f1cda1b58549e8eae456b`

`v1/v2` 是未提交的本地准备草稿，保留其字节与证据；仅以上 v3 为本次审核对象。
v3 复用已收集的原始数据，没有重跑远程收集、模型或 DFT。

## 近重复与数据分配

使用已有 Fe(110) 表面 36 个保留上表面的对称操作、xy 周期映射及相同 H 原子置换。
保留实际吸附高度；不任意旋转分子、不平移吸附态质心、不用 45 个 Fe 平均来掩盖吸附原子差异。
不同连接异构体分开检查。现有吸附重复检查的 `0.20 Å` 在此仅用作保守的数据隔离尺度，
不是“结构错误”或“同一个 DFT 最低能态”的物理判据。

- 56 条 C₂ 轨迹帧中发现 84 对近邻关系，包括同一轨迹内部的相似帧。
- 排除 `04_cfg2` 的 step054/109/164/217/218：它们接近冻结留出作业 `04_cfg1`。
- 另排除 `01_cfg1_step109` 和 `02_cfg2_step152`：分别由最终 step110/153 代表；
  几何 RMSD 约 0.000190/0.000852 Å，最大逐原子力差约 0.00833/0.01996 eV/Å。
- 保留具有明显不同力的近几何帧，避免删除优化中重要的离平衡标签。
- 留出 16 帧及原有整作业划分不变；加入 replay 后跨分区严格等价和近重复检查均通过。

| 用途 | C₂ 轨迹帧 | 旧吸附 replay | 合计 |
|---|---:|---:|---:|
| 训练（更新权重） | 25 | 9 | 34 |
| 开发（选择 epoch、检查保留性能） | 8 | 4 | 12 |
| 冻结留出（不得训练或选择 epoch） | 16 | 0 | 16 |

开发 replay：`h2_top / ch2_top / ch2o_oend_top / c2o_hlbh`；其余 9 条只进入训练。
旧 replay 是回归保留集，不宣称为未见过物种的泛化证据。
site 审查及邻近 Fe 信息在 `near_duplicate_review.json`；这些标签不被自动登记为正式吸附端点。

## 旧数据兼容性

13 条旧标签全部通过：PBE、ENCUT400、ISPIN2、ISMEAR1、SIGMA0.20、Gamma5×5×1、
相同 Fe45 晶胞和固定底层 Fe0–17、LDIPOL=false、Fe2.2/吸附原子0 的磁性初始化、
逐物种 POTCAR 数据块哈希、源 CONTCAR 哈希及原子顺序。

最终 OUTCAR 均有 EDIFF 结束标记、required-accuracy 和正常结束证据；
逐原子力及 TOTEN 与原标签完全一致。力表几何精度、OSZICAR 电子周期/能量、有限数值和碰撞检查通过。
完整 OUTCAR 哈希、原始输入和提取力表已绑定。没有为补 replay 新算 DFT。
此结论只覆盖力标签兼容性，不补全不同吸附物的气体参考，也不自动计算吸附能。

## 拟申请的小规模训练

- 模型：现有 AQCat25，checkpoint SHA `e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50`。
- 目的：改善离平衡及近最低点 C/O 力，同时避免 Fe/H 退化。
- 只训练力；energy loss=0。力单位 eV/Å；固定 Fe 不参与损失。
- 4 个 epoch，学习率 `1e-5`，seed42，batch1；沿用已存在的模型架构和归一化设置。
- 单作业 1GPU / 4CPU / 32GB / 最长30分钟；不自动重试，不覆盖基准 checkpoint。
- 开发集选择最优 checkpoint；随后同结构对比基准/候选的 C₂ 与 retention 两组，分别报告 Fe/C/O/H。
- Fairchem 训练与原有 POSCAR 推理都保留零 atom tags，禁止 ASE DB 默认变成全1；固定层掩码保留。
- 重新初始化训练 epoch/optimizer，禁止恢复预训练进度而跳过这次小规模训练。
- 不自动晋级。冻结留出集在候选确定后另行验证，不参与此次 epoch 选择。

远程包为 `/home/sbq/sbq/adsorption_c2_finetune_20261010_v3`。
初始审核时尚未上传或提交；2026-10-10 用户“启动”后的实际执行记录见下文。
运行前必须完成 MZ73 无训练的包/运行环境预检，并取得上述请求哈希的单独用户授权。
执行器拒绝缺失、过期或不匹配的授权。这里只准备训练，不同时授权新的 DFT。

## 验证与尚未确认

已执行：Python 编译、Ruff、19 个本次单元/异常测试及14个相关回归测试，共33个通过；
训练脚本 `bash -n` 通过；最终请求和80项文件哈希验证通过；三个 ASE DB 的实际行数为34/12/16。
MZ73 只读 CPU checkpoint 检查确认基准 SHA、模型配置和 PyTorch2.4.1，未执行 GPU forward 或训练。

未确认：训练是否收敛、候选的留出误差/最低点漂移、GPU容量及完整训练运行链。
当前没有完成的 species03 CH–C–O 标签，因此不能称这次微调覆盖五种结构的全部连接异构体。
开发主数据只有一个 C₂ 完整作业，统计独立性有限；相关帧条数不等于独立样本数。
小数据调整有过拟合和其他吸附物退化风险；力专用微调后能量头也不能直接用于已校准能量排序。

真正的加速仍需在同一原始种子、相同最低能盆、相同 VASP 参数/资源下比较：
直接 VASP、原 AQCat25+VASP、候选+VASP。报告离子步和时间，并计入 GPU/标签/训练成本；
可复用已有兼容对照，但不能从单点误差下降推断已获得实际加速。

## 2026-10-10 启动记录

用户“启动”单独授权原始请求哈希 `2e1b517270395b414c8e7079cf95df93656014e24ce2db3f1e6b5e0ac3c40d16`。
未修改原请求的初始未授权快照；独立授权、预检、提交与失败证据保存在
`calculations/fe110_five_c2_adsorption_20261006/adsorption_finetune_submission_v3/`。

- 原80项绑定文件、请求、独立授权已上传；没有上传基准 checkpoint 或 POTCAR。
- MZ73 CPU 预检通过：真实 Fairchem/FiLM 注册、训练34/开发12逐行 graph/原子顺序、力标签、固定层、零 tags、基准 checkpoint 哈希及架构一致；未训练或读取留出集作模型选择。
- 首次坐标检查错误地直接比较已折回晶胞的 graph 坐标；确认读取器明确使用 `wrap_positions(...,eps=0)` 后，改用同一周期等价表达检查。原始数据和训练 runtime 未变，失败预检与修正版本均保留。
- 只提交一次训练作业 **2181**，1 GPU/4 CPU/32 GB/30分钟、4 epoch。初次调度为 RUNNING；启动检查随后确认 **FAILED，ExitCode=2:0，运行1秒**。
- Slurm日志0字节，无正常退出记录、warmstart 或候选 checkpoint，不能声称训练已开始或已提高精度。失败限定在训练启动前的 shell/bootstrap 阶段；具体是哪个检查或批处理环境值尚未确认。SSH 下路径/hostname检查通过，不等于 Slurm 环境检查通过。
- Slurm accounting 已禁用，使用 `scontrol` 已完成状态作为调度证据。诊断只执行脚本前25行（无模型），创建了失败作业的空 output/job_2181 目录；该目录不是训练输出。
- Pythoncompile/Ruff和4个提交边界测试通过。没有自动重投、提交 VASP、读取留出预测或晋级模型。

## 2026-10-10 启动问题定位和 v4 修复

用户“继续”授权无模型诊断和必要修复，没有授权 GPU 训练重投。
Slurm CPU 诊断2182复现 ExitCode2，明确失败于 environment_setup：
批处理继承 `TMPDIR=/tmp`，环境工具保留该值，随后授权写路径检查拒绝 `/tmp`。
SSH 预检时 TMPDIR 未设置，因此使用授权目录默认值。这是启动器环境处理问题，不是模型误差或训练不收敛。

最小修复：训练 wrapper 在环境设置前显式设 `TMPDIR="$RUN_ROOT/tmp"`；
提前安装现有 bootstrap 错误记录器；增加 `--no-requeue`，与不自动重试政策一致。
不修改共享环境工具，不放宽写目录安全边界，不改变结构、VASP标签、模型、优化器或训练预算。

修复对照2183在真实 Slurm 批处理中执行新 wrapper 的完整环境启动前缀，
同样继承 `/tmp`，明确切换到作业内临时目录后通过：COMPLETED/0:0、运行1秒。
两个诊断均不申请 GPU、不加载 checkpoint、不执行 Python/模型/训练；每个请求1CPU，
Slurm硬件分配显示2逻辑CPU。证据：`adsorption_bootstrap_diagnosis_v1/`。

新的 `adsorption_finetune_review_v4/training_request.json` 请求 SHA：
`9f634620c40a4da397853085f4cfcdf366548832115a641b35f34fb366bd5f2a`。
80项绑定中78项逐字节不变，仅 config.yml 中远程v3→v4路径及修复wrapper变化；
34/12/16 split、checkpoint哈希和4epoch/lr1e-5/1GPU/4CPU/32GB/30min预算全部不变。
原v3请求、失败训练2181和所有预检/诊断记录保持原样。

已验证 Pythoncompile、Ruff、26项相关测试、远程两个probe与新wrapper的bash-n、
v4完整文件绑定及本地标签验证。2183通过仅证明启动前缀修复，不证明完整训练能运行、
候选误差下降或VASP加速；冻结heldout未用于本次判断。v4尚未上传或提交训练。

## 2026-10-10 v4 授权提交与采样器初始化失败

用户“提交”授权v4请求的一次训练重投，独立授权文件与80项原绑定文件已上传。
新包远程CPU预检通过；提交前GPU0/1/3有空闲显存，GPU2接近占满。
只提交一次 **2184**：1GPU/4CPU/32GB/30min、禁止requeue。

实际结果：2184初始RUNNING，随后 **FAILED/ExitCode1:0，运行31秒**。
已通过原TMPDIR启动问题，生成warmstart并启动Fairchem、加载模型，
但在训练数据采样器构建阶段触发 `UnsupportedDatasetError`：
`BalancedBatchSampler` 要求 `natoms` 元数据，现有包没有提供。
真实源码确认即使单GPU已禁用平衡分配，也仍执行该元数据检查；仅设置
`load_balancing=false` 不足以修复。训练/开发DB共用目录，但长度分别34/12，
后续必须分别提供长度及逐行原子数相符的元数据并显式绑定各自 `metadata_path`，
不能共用默认metadata.npz或跳过标签检查。

另发现Fairchem CLI的 `build_config` 用命令行默认seed0覆盖YAML的42；
本次尚未进入训练迭代，但再次提交前必须显式传入已审核seed42，并检查合并后的实际配置。
模型参数没有进行训练更新；未生成训练候选，原基准checkpoint未覆盖。
这不是显存OOM、标签误差、训练不收敛或吸附物理不稳定的证据。

现有预检验证了AseDBDataset图转换，但没有构建实际BalancedBatchSampler，
也没有核对CLI合并后配置，因此预检通过不足以证明完整训练链可执行。
退出记录已正常保存并收回，故启动记录修复生效。
证据：`adsorption_finetune_submission_v4/` 中授权、提交回执、
training_start_2184.txt、runtime_sampler_config_diagnosis.txt和producer_exit_record_2184.json。
没有自动重投、VASP提交、heldout模型选择或checkpoint晋级。

下一步：准备各split独立natoms元数据和显式seed传递的最小修复；
无模型CPU预检须覆盖真实采样器完整遍历及CLI最终参数，再形成新哈希请求供授权。
