# 536帧均匀两epoch小试：独立执行包与预检

2026-11-13。用户本轮授权：“应直接准备536小试执行包并完成预检”。

**结论：执行包、本地数据预检和MZ73原生CPU预检已完成；当前GPU资源预检阻塞，未启动训练。** BUCT与BUCT2均返回 `Failed to initialize NVML: Unknown Error`，可用GPU、显存和计算进程无法完整确认。没有选择GPU index/UUID，没有复用512训练授权，没有提交Slurm或直接启动训练进程。

## 1. 执行包与身份

本地根目录：`C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/training536_smoke_20261113_v1/`。

| 项目 | 路径或SHA-256 |
|---|---|
| 独立训练请求 | `package/control/training_request.json` |
| 请求SHA | `5c378d116b09746c3b7ddd07ec41ae16733ecafc04be13ddc05dc8eb2850af04` |
| 原生配置 | `package/control/config.yml` |
| 配置SHA | `7fcf7b7964dbb618772a1c5e151154759c73f558f74048ba8169755f35a2a776` |
| 冻结536 manifest SHA | `02ef3dcbf5306733856429b51406767d6e62f6fbc200c13b91a117a4a737bcd2` |
| 原始AQCat25初始化 | MZ73 `/home/sbq/sbq/aqcat25/demo_single/model.pt` |
| 初始化在线SHA，前后相同 | `e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50` |
| 原生CPU回执 | `native_return/native_preflight.json`；SHA `2871ad1092dcd88dcea3ffd195bcee94aeec36e62e4cc225b59d81bb2920848a` |
| 逐参数清单 | `native_return/parameters.json`；SHA `f766e85dc0637465d9daff77108f8c148ba1857e6ad56f6c5b0f407694fbf83b` |

为完成用户要求的原生预检，副本已放入MZ73新目录 `/home/sbq/sbq/fe110_force_training536_smoke_20261113_v1/`。其规范物理路径位于已观察的 `/home/ubuntu/hdd/sbq/sbq/` 下；没有写旧数据包或旧模型目录。服务器原始checkpoint只读，没有上传或复制权重。

原536包的2759项inventory文件逐一验大小及SHA；原目录全部2760个文件复制后逐字节哈希一致。加入独立配置、绑定运行时和CPU预检契约后，共2777个部署文件，全部在传输接收端核对清单、大小和SHA；拒绝重复、越界及未绑定归档项。原始512/536包不变。

## 2. 准备的训练配方

| 项目 | 已准备值 |
|---|---|
| 数据 | 536 train、78 development；53 heldout和16隔离成员不变 |
| 初始化 | 原始AQCat25参数；不从旧512微调模型恢复优化器或进度 |
| 模型 | 原Hydra／8层aqformer_backbone_film与原normalizer；模型配置和损失与已运行512配方一致 |
| 采样 | 每帧1/536，有放回；不增加阶段因子，不修改逐原子角色权重 |
| 规模 | 2 epoch、batch1、梯度累积1、seed42、AMP；1072次原生迭代上限 |
| 优化器 | AdamW，lr1e−5，weight_decay0.001；cosine调度2epoch、warmup1epoch |
| 其他 | clip100、EMA0.999、num_workers0；force-only，energy系数0 |
| 评估／保存 | 每536次；只用原78开发帧的`forces_role_vector_mae`选择唯一best，再冻结SHA |
| 训练预算提案 | 1 GPU、4 CPU、32 GB RAM、30分钟／0.5 GPU小时；0自动重试 |
| 执行权限 | `training_authorized=false`；未创建direct执行请求、训练授权、启动marker或控制进程 |

1072是原生迭代上限。AMP可能跳过参数更新，不能把它称为已保证的1072次实际更新；未来必须分别记录。现有`warm_start`入口会清除旧optimizer/scheduler/scaler及选模状态，重置epoch/step；本轮没有调用获准的warm-start，也没有写任何模型文件。

已有控制器在名义截止点触发退出，历史上包含退出的总时间曾超出约2秒。`execution_policy_proposal.json`因此仅提出1770秒触发、30秒退出余量；这项运行时约束尚未激活或实测。训练执行时须以新范围绑定并核验，不能称现有控制器已经证明严格含退出≤1800秒。

## 3. 原生CPU预检实际结果

MZ73 Python环境实际运行了包内canonical `verify_training_package` 和 `check_native_cli`，随后按Fairchem原生`registry`、`match_state_dict`和严格`load_state_dict`构造并加载CPU模型。

- 原生状态：`PASS_NATIVE_CPU_PACKAGE_CLI_CHECKPOINT_PARAMETERS_NO_TRAINING`。
- 实际校验train/dev共614行ASE DB的坐标、元素顺序、原始力、固定掩码、tags、角色元数据及metadata；manifest标签的静态完整性校验不属于保留集模型评估。
- 原生CLI解析与绑定配置一致；trainer从本包namespace加载，只有train/val，无heldout/test loader。
- 原始checkpoint在线SHA匹配；架构完全一致，严格加载无缺失或多余键，全部参数有限且位于CPU。
- CPU原生检查耗时10.887835秒，峰值RSS958004 KiB；4个CPU affinity；Torch `2.4.1+cu121`。这些是CPU预检资源记录，不是训练耗时或GPU可用性证明。
- 模型前向0、反向0、优化器实例／更新0；CUDA未初始化；没有warmstart或候选权重输出。

| 参数组 | 参数tensor数 | requires_grad参数量 | 冻结参数量 |
|---|---:|---:|---:|
| backbone | 374 | 27,967,680 | 0 |
| energy head | 9 | 148,353 | 0 |
| forces head | 25 | 3,129,345 | 0 |
| 合计 | 408 | **31,245,378** | **0** |

因此当前配方是全参数可训练，不能称作只训练力头。energy head保留requires_grad与原有零系数图连接，能量目标仍为0；参数可训练状态不代表本轮测过梯度、更新或能量拟合。

## 4. GPU预检和执行边界

按项目入口实际调用一次 `python -m scripts.gpu_resources`，同时检查BUCT与BUCT2；返回码1。两个主机均可连接，但NVML失败；节点Slurm资源摘要不能替代GPU显存、UUID和进程清单。因此当前不能安全绑定GPU，未尝试CUDA前向／反向、分配GPU、提交作业、停止服务或修复驱动。

`execution_policy_proposal.json`保留空GPU index/UUID，未修改根`configs/execution_backends.yaml`。已有512授权的目录、UUID、请求SHA和迭代上限不覆盖536。包内Slurm脚本只做语法和CLI解析检查；未来建议的direct执行路径仍需新的后端范围与精确授权，不能把参考Slurm入口称作已获准可提交。

在资源可见性恢复后，仍需一次新鲜资源／环境检查及具体GPU绑定，再完成新执行范围、预算及精确请求的授权。当前CPU通过不能替代GPU运行预检。没有因NVML失败自动换主机或重试资源检查。

## 5. 验证和冻结边界

- 三个新增Python源文件语法检查、限定Ruff通过；部署包的两个shell脚本在MZ73上分别`bash -n`通过，未执行脚本。
- 33项既有相关回归全部通过，0失败／0错误；XML在`owner_regressions.xml`。
- 五项负向探针均拒绝：旧1024迭代上限、20epoch越界、保留集loader、旧512评估间隔、无效训练授权。最后一项实际经过canonical `warm_start`授权拒绝，未创建模型输出。
- 模型、force-only损失、normalizer、开发选模指标与模板一致；没有同时改变阶段权重或角色权重。
- 512/536的12项关键文件前后SHA一致；78/53/16及磁性审核等级不变。原始512 manifest仍为`ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee`。
- 旧`tasks/current_task.md`及已有错误日志漂移保留；未接续六作业基准，也未改写任务指针。没有更改锁定DFT方法、旧权重、旧执行授权或现有作业。
- 没有训练、推理、ML/DFT结构优化、DFT单点、NEB/DIMER或自动科学验收；本轮GPU训练消耗0。

来源与回执还包括：`preparation_receipt.json`、`deployment_inventory.json`、`local_preflight.json`、`cpu_preflight_receipt.json`、`negative_guard_verification.json`、`shell_syntax_receipt.json`、`gpu_resources.stdout`。原生证据以原始文件字节通过scp返回并验SHA，没有从控制台截取重写。

新增源码位于 `C:/Users/86177/Desktop/work/archive/fe110_training536_smoke_20261113/`，入口分别为`.prepare`和`.transport`；二者拒绝覆盖已有包或重复部署。`.transport`只部署新副本并运行CPU预检，没有训练入口。重新执行前应复用已存在回执，不重复上传或构建。

**下一步：只读复查GPU资源可见性，在检查完整通过后为本请求绑定具体可用GPU。**
