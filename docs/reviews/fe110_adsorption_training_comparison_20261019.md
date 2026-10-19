# Fe(110) 吸附受限训练对照包：待审核

日期：2026-10-19。范围：仅准备，**未提交 GPU、未上传实际数据、未训练或晋级模型**。
完成两组 runtime-v3 本地包及哈希绑定、数据库核对、137 项相关测试和 MZ73
无模型命令行检查。精度和实际加速效果仍未验证。

## 对照设计

| 项目 | control 对照组 | treatment 改进组 |
| --- | --- | --- |
| 初始化 | 同一个原始 AQCat25 checkpoint | 同左 |
| 训练结构/逐原子力 | 冻结的 248 帧 | 完全相同 |
| 训练目标 | 每个可动原子的均匀向量力误差 | 每帧清单定义的角色加权向量力误差 |
| 训练采样 | 均匀、有放回 | 来源/阶段均衡、有放回 |
| 开发集与选 epoch 指标 | 同一 60 帧、共同角色加权向量力 MAE | 完全相同 |
| 最大预算 | 2 轮、496 个优化步、30 分钟 | 完全相同 |

两组均 batch=1、seed=42、学习率 1e-5、单 GPU/4 CPU/32 GB；按顺序运行，
最多同时一张 GPU，总训练墙时上限 60 GPU 分钟，不自动重试。
两轮是小规模对照预算，不是“已足够训练收敛”的结论；超时保留部分输出，不自动加时。

原始 checkpoint：`/home/sbq/sbq/aqcat25/demo_single/model.pt`，SHA256：
`e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50`。

共同初始化是待审核选择：使用原始 AQCat25 隔离新策略效果，不额外做原始/2185
初始化搜索，也不根据新留出集挑初始化。已知 2185 的局部 C 力回归不等于原始模型一定更好。
两组不是两种势函数，也不是严格复现旧训练：control 同样有放回，可能有些帧一轮重复、
有些未出现。这个最小对照同时改变权重和采样，只能评价组合方案，不能分别归因。

## 数据与方法边界

- 原池 SHA256 `6deb86d4fcb2bfbde29f7d2d6faf3f2663afa2ac04c9d8a79659c876e6234330`
  未变；treatment 清单与其字节一致。control 仅派生训练行两个权重/概率字段，
  不改力、坐标、顺序、固定层、来源、开发/留出划分。
- 复用已测试的 ASE DB。control 只在独立副本更新训练元数据；两组开发 DB/NPZ
  与已测试版本哈希相同。原始数据及旧包未覆盖。
- 46 帧新留出不训练、不选 epoch；16 帧已观察留出继续隔离。包内留出来源/结构
  只供 canonical 完整性核查，没有 heldout.db 或模型 loader。
  3 个实际偏离结构属于训练候选，不能再当独立验证。
- 角色与权重来自审核清单，本次 `2:1:1:2:1` 和 3 Å 分组不是通用物理标准。
  固定 Fe 0–17 的训练权重为零；原始力保留。只训练力，能量损失为零。
- 标签沿用统一 PBE/ENCUT400/Fe45/Gamma5x5x1/ISPIN2/ISMEAR1/SIGMA0.20 分支。
  中间帧不是已接受吸附终态，不生成可报告吸附能。C₂H₃ 仍只有测试覆盖，不宣称可推广至 TS。

## 运行与开发集审核

新包完整包含 scripts 命名空间及适配器，启动时将包的 runtime 置于 PYTHONPATH 首位。
新 `role_training_job.sh` 不修改旧 wrapper 或部署的 Fairchem。仍需独立的精确
request-hash 授权，不能用本轮准备请求直接运行。

真实 OCPTrainer 的 `eval_every` 单位是优化步。旧模板值 1 会每步跑完整开发集；
本包改为 248，即每轮一次，并每轮保存断点。这个调整只减少此次训练对照的调度开销，
不能用于解释原有 VASP 离子收敛缓慢。

共同 `forces_role_vector_mae` 选择开发集最佳 epoch，返回 C/O/H、邻近 Fe、其余 Fe、
replay 物理单位指标。O/H/replay 回归作为人工审查软警告，不设零容差门。
本包没有实现“保留性能自动早停”，也不凭总指标自动选择生产模型；训练后还需分组曲线
和实际偏离结构审查，再决定候选是否值得独立验证。

## 已执行验证

- Python 编译、相关 Ruff、Bash 语法检查通过；**137 passed，0 failed/error/skipped**，
  包含既有角色/采样/授权/池治理回归。
- 两组全部 248/60 DB 行的坐标、原始力、顺序、固定层、零 tags、角色元数据与清单一致。
  独立复核确认组间训练几何与力完全相同，以及原池、request/绑定 artifact、共同配置与预算。
- MZ73 真实 Fairchem CLI 参数合并和 registry 类路径解析通过。使用 RAM-only 模块与
  实际配置/启动命令，未加载模型、未初始化 CUDA、未传实际结构/标签。
  此项**不等于已验证部署磁盘上的 PYTHONPATH**；磁盘预检逻辑已封装，待授权后执行。

本地初次 Ruff 检出新 preflight 复杂度/拆分后未定义变量和辅助脚本未用导入，已修正通过；
一次 SSH 只读检查引号错误改用 stdin 脚本解决。这些不是旧模型科学误差的原因结论。

## 审核标识与产物

包目录：`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_comparison_20261019_v1/`。

| 请求 | SHA256 |
| --- | --- |
| comparison_request.json | `f5db5cb7b1e98d6153bba8bbc41a0d0697fd29c79162a4ef0298a91969660987` |
| control/training_request.json | `dbad960b964805277333d21bce0a1669e38085c9ab742f5ed53a88a9a5b2d026` |
| treatment/training_request.json | `8b740e698d2bac32bb9f918012372a1aaf4e410d9bfef61397bb55ce95ab69ca` |

同目录 `verification_receipt.json`、`scoped_tests.xml`、`native_cli.*`、`native_cadence.*`
保存证据；`archive/fe110_adsorption_training_comparison_20261019/` 提供不覆盖原结果的生成/复核入口。

## 剩余风险与下一步

尚未执行授权后的真实磁盘部署、checkpoint 架构/哈希、GPU 显存/CUDA/AMP 完整前后向、
优化器及实时 Slurm 可用性预检。旧 direct-execution 例外不能给本包授权。
单 seed 两轮可能不足以改善或稳定收敛，不承诺显著加速。

下一步：用户审核两组设计和预算；通过后另行授权该精确哈希包的部署/预检与 GPU 训练。
训练后先冻结候选，再单独评估独立留出、几何保留和配对 VASP 步数/耗时，
不能用代码测试或更低 ML 力替代实际加速验证。
