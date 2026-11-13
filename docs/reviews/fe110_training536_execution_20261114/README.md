# 536帧均匀两epoch小试执行与候选回收

执行日期：2026-11-14，Asia/Shanghai。用户授权：先检查GPU资源，预检通过后启动536帧均匀两epoch、学习率1e-5、单GPU最多30分钟；保持512/536包及78/53/16不变，不提交新DFT。

**训练本体完成：1072次原生迭代、1072次实际optimizer更新。唯一原生开发best已回收并验SHA；没有重训或模型推广。** 原作业14505在训练后的候选导出定位环节退出1，Slurm原始`FAILED/1:0`和producer退出1均保留，不能写成调度器COMPLETED。后续仅用CPU核查既有checkpoint并完成文件回收。

## 1. 执行身份与结果

| 项目 | 实际证据 |
|---|---|
| 原生Slurm作业 | 14505，MZ73，gpu分区，1 GPU／4 CPU／32 GB |
| 原训练请求SHA256 | `5c378d116b09746c3b7ddd07ec41ae16733ecafc04be13ddc05dc8eb2850af04` |
| 独立执行契约SHA256 | `157472cc216c752958e9dbbe0898d2be8ca881e0b2469d4845cd2d7344e7f92f` |
| 原始预训练初始化 | `/home/sbq/sbq/aqcat25/demo_single/model.pt` |
| 初始化SHA256，训练后仍一致 | `e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50` |
| GPU | NVIDIA GeForce RTX4090，24564 MiB；分配前空闲24066 MiB，无计算进程 |
| GPU UUID | `GPU-e72f50ad-d93f-c404-04c4-51dccc85727e` |
| 编号映射 | Slurm全局GPU3，作业内NVML GPU0，模型`cuda:0` |
| 环境 | Torch2.4.1+cu121，CUDA12.1 |
| 训练结果 | 2epoch，1072次原生迭代，1072次实际参数更新 |
| 开发集主指标 | `forces_role_vector_mae = 0.06199433411567066 eV/Å` |
| 候选SHA256 | `2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0` |
| 候选大小 | 126,477,568 bytes |

本地候选：`C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/training536_execution_20261113_v4/returned/candidate.pt`。

原生best：`/home/sbq/sbq/fe110_force_training536_execution_20261113_v4/checkpoints/2026-11-14-00-04-16/best_checkpoint.pt`。其物理路径位于`/home/ubuntu/hdd/sbq/sbq/`。远端导出副本、原生best和本地回收副本的SHA完全一致，原生best未被改写。

原生best是weights-only checkpoint，包含`state_dict`、normalizers、config、`val_metrics`等，不含epoch/step和`best_val_metric`顶层字段。指标取自该best自身的`val_metrics.forces_role_vector_mae.metric`，numel=78。不得因缺少进度字段而把它描述成未训练完成，也不凭文件名虚构best的epoch。训练完成与实际更新数由独立同进程回执证明。

## 2. 配方和数据边界

使用已准备、已通过原生CPU审核的536小试配置，没有应用上一轮提出的新角色或阶段权重：

- 原始AQCat25初始化，清除旧优化器、调度器、scaler和进度；全参数可训练；原架构与normalizer不变。
- 536训练、78开发；每帧1/536有放回采样；训练可动原子均匀权重、固定18Fe权重0；开发角色权重沿用原值。
- AdamW，lr1e-5，weight_decay0.001，batch1，梯度累积1，seed42，AMP；cosine两epoch、warmup一epoch，clip100、EMA0.999。
- force-only；energy系数0；energy head零梯度图连接保留。没有拟合绝对能量或相对能量。
- 每536次迭代评估／保存，只用原78开发集选择原生best。没有heldout/quarantine loader或独立保留集推理。
- 实际参数均在同一CUDA设备；首两次原生反向与更新检查通过，loss有限、energy head梯度为0，没有额外测试训练步。

原78开发集仍缺C2H3和完整C3H2O近稳定区域的充分覆盖。本次主指标只支持这次可行性试训，不证明末段结构优化改善、预训练通用能力保留或VASP加速。

## 3. GPU预检、失败记录与恢复

1. 项目标准入口同时检查BUCT和BUCT2。两者登录会话的NVML均失败；BUCT2资源摘要显示所有5张GPU已分配，未选择或操作该主机的作业。
2. MZ73登录会话读取`/dev/nvidiactl`和GPU设备返回EPERM；已核查驱动与用户态库版本一致。通过原生Slurm分配GPU，在作业内完成真实资源和CUDA预检，而非绕过预检直接训练。
3. 预检作业14496在旧环境包装器的路径检查退出2，用时1秒，无模型训练。旧脚本要求逻辑根目录与物理目录相同，但本机`/home/sbq/sbq`映射到`/home/ubuntu/hdd/sbq/sbq`。初次终态曾现场观测，后续Slurm短期记录已清除，原始bootstrap日志与回收失败查询均保留，不伪称现在仍可查询该终态。
4. 独立v2只做CPU环境预检，没有提交GPU作业；进一步确认venv解释器链接到`/usr/bin/python3.10`。后续包装器仅允许这个已确认的只读解释器目标，所有任务写目录仍严格绑定到上述物理工作边界。没有修改共享环境脚本或根后端策略。
5. 预检作业14504在查询Slurm全局编号3时NVML退出6，用时9秒；未初始化训练模型。随后在作业内枚举可见GPU并按UUID绑定，确认该卡被重编号为NVML0。
6. 作业14505通过作业内资源、CUDA、614行DB及原生CLI预检，完成唯一一次模型训练。原生CLI把checkpoint写入执行根目录的`checkpoints/`，初始导出仅搜索`output/job_14505/`，因此训练完成后返回1。
7. 不重训、不以last权重替代best。CPU读取唯一原生best、检查有限性和自带78帧开发指标，逐字节复制为候选并回收。保留所有失败回执和原作业退出码。

所有新输出均在独立执行目录；初始阶段包、公共脚本、已有作业和旧模型没有被覆盖、清理、取消或重启。不存在第二次模型训练尝试。

## 4. 实际预算

| GPU分配 | 用时 | 模型更新 |
|---|---:|---:|
| 14496，bootstrap预检 | 1秒，现场观测值 | 0 |
| 14504，编号查询预检 | 9秒，有原生终态快照 | 0 |
| 14505，训练及退出 | 177秒，有原生终态快照 | 1072 |
| 合计 | **187秒＝3分7秒＝0.0519444 GPU小时** | **1072** |

14505原生CLI记录164.069143秒；其余时间包括预检、初始化与退出。资源时间使用Slurm RunTime及同一服务器进程记录，没有混减本机和服务器时间戳。

执行上限为Slurm29分钟＋已查明的KillWait30秒，另有1700秒进程watchdog和10秒强制退出余量；把前期10秒分配计入后，所提累计保守上限1780秒。实际没有触发超时或停止其他作业。CPU恢复、哈希和文件传输没有分配GPU。

## 5. 验证与证据

证据根目录：`calculations/fe110_reico_pilot300_20261022/training536_execution_20261113_v4/`。失败预检分别保留于v1/v2/v3独立目录，不覆盖旧记录。

主要原始证据：

- `submission_return/submission_receipt.json`、`executor/execution_contract.json`：原生提交与独立执行绑定。
- `checkpoint_*/scheduler.stdout`：原生RUNNING和FAILED/1:0终态，未由进程回执推断调度状态。
- `returned/allocation_preflight.json`、`execution_device.json`：实际资源、UUID、模型CUDA绑定。
- `returned/native_two_backward_check.json`、`training_completed.json`：同进程启动和1072次真实更新。
- `returned/slurm-14505.log`、`job_exit_record.json`：训练过程与导出失败原始记录。
- `returned/candidate_recovery.json`、`checkpoint_metadata_inspection.json`：原生best格式、开发指标与CPU恢复，0额外训练更新。
- `returned/input_integrity_after.json`、`final_verification.json`：远端输入、本地冻结包及候选一致性。

最终13项检查全部通过：512/536的12个关键文件哈希不变；原78/53/16分区和审核等级不变；原准备请求、任务指针及根后端策略不变；远端准备包7个核心输入SHA不变；原始预训练SHA不变；本地/远端候选与原生best一致；权重有限；训练进程已退出；原生checkpoint/results/logs都位于独立执行根目录。

限定范围Python语法、Ruff和原生shell语法检查通过；53项相关CPU回归覆盖预算、授权、保留集loader、GPU编号映射、占用拒绝及终态文件筛选。没有运行全仓库测试，没有通过运行NEB、DIMER或DFT验证代码。

## 6. 科学状态与下一步

状态为`TRAINING_COMPLETE_NATIVE_BEST_RECOVERED_WRAPPER_FAILURE_PRESERVED`。这是一次已完成的小试与已冻结身份的候选模型，不是生产模型推广或科学验收。

没有新DFT、ML结构优化、VASP交接、独立保留集推理、原始数据修改或旧模型覆盖。`tasks/current_task.md`原六作业基准指针保留，没有接续或篡改其状态。

下一步只建议：单独审核新536候选与冻结512候选在相同开发结构上的分组成、分角色力误差；独立完整C3近稳定验收缺口继续保留。
