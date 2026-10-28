# Fe(110) 512帧：从头训练与微调对照准备

**已获两项训练、总计≤1 GPU小时的明确授权，并已在GPU1启动顺序训练。** NequIP随机初始化模型已证明实际参数在CUDA（216,736参数）；20-epoch AQCat25微调在其结束后通过新的独占检查再启动。两项尚未完成，不据此声称精度或加速。没有新增DFT、测试集训练、自动重试或模型晋级。

目标限于当前Fe(110) C₂/C₃优化。这是工作流对照，不是覆盖全部Fe–C–H–O化学空间的通用模型，也不单独识别“有无预训练”的因果效应：两条路线的网络规模、架构、学习率和批量不同。

## 已授权的两项具体训练

两项在MZ73 GPU1顺序运行，使用独占检查；每项总墙钟最多30分钟，合计最多1 GPU小时。启动前重新核对GPU UUID、至少20,000 MiB空闲显存及无其他compute进程；不驱逐或停止其他任务，不沿用GPU0共享例外。

|项目|NequIP从头训练|AQCat25微调对照|
|---|---|---|
|初始化|随机初始化，无预训练checkpoint|原始AQCat25，非旧微调权重|
|模型|NequIP 0.19.1，3层、l_max=1、32 features，约21.6万参数|原AQCat25架构|
|截断|5 Å|保持原配置|
|学习率|0.001|0.00001|
|批量|4|1|
|epoch上限|100|20|
|更新/迭代上限|12,800次参数更新|10,240次原生训练迭代；不混同实际AMP参数更新次数|
|停止|开发集停滞20轮可提前停止；墙钟上限仍有效|固定20轮或墙钟上限|
|选模|完整78帧开发集的原角色加权可动力向量MAE|同一开发集和同一指标|
|预算|最多30分钟、1 GPU、4 CPU、32 GB内存请求|最多30分钟、1 GPU、4 CPU、32 GB内存请求|

单seed=42的首轮是可行性试验，不是统计显著性或充分训练证明。两条路线保留均匀帧有放回采样；训练按可动原子均匀加权，开发评估沿用原角色权重。不会把20轮微调结果与两轮试训差异全部归因于模型架构。

## 数据及物理边界

- 冻结源manifest：`ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee`。
- 原512训练/78开发/53保留及16个历史观察留出继续隔离；NequIP只导出512+78，无测试文件、随机重划分或测试loader。微调沿用原包；其清单保留留出来源信息，但不生成留出数据库或loader。
- 原始固定Fe力完整保存，损失权重为0；其余原子保留原权重。开发集原角色权重不是均匀权重，不能在换框架时擅自统一。
- 使用17位有效数字导出extxyz，逐帧重读590帧，坐标/晶胞/周期边界/原始力/权重精确一致；对原POSCAR坐标按既有1e-12 Å序列化容差核验。元素顺序、样本/作业身份与磁性等级保留。
- 训练磁性等级仍为258局域正Fe、248旧来源审核、6总磁矩限定，没有升级审核等级或证明磁性全局基态。NequIP本次输入元素及几何，没有显式多磁态输入，只对应既定标注分支。
- 两路线均force-only。NequIP的每元素能量偏移固定为0；这属于未确定的能量零点，不能用于跨组成吸附能比较。邻居数和力尺度初始化仅使用训练集。
- 原覆盖限制不变：C₂H₃的4个≤0.05 eV/Å帧仅来自10_B；C₃H₂O仍无这一低力区间。换框架没有补齐缺口。

## 实际完成的验证

1. 590帧导出独立重放，原始力、原始固定力和训练/开发权重不变；NequIP v2数据副本的SHA与原导出清单一致。
2. 原20-epoch微调包完整通过本地及MZ73原生包/CLI预检，核对全部训练/开发DB数据与包内namespace；未实例化AQCat25模型或调用CUDA。
3. 本地独立CPU环境的NequIP实际完成两次更新和开发评估。MZ73原生环境再以四种组成的训练子集完成两次CPU更新，验证子集来自开发集，未使用保留数据。
4. 原生checkpoint的`global_step=2`，Adam状态step最小/最大均为2；52个张量状态有限且位于CPU；CUDA未初始化。损失中的两个非张量元数据字典单独保留，不错误地交给`torch.isfinite`。
5. 主工作区48项相关测试通过，包含与原grouped-force目标及固定原子零梯度的一致性、原两轮预算门不变、新20轮严格数据绑定、路径和授权拒绝回归。限定Ruff、任务源语法检查通过；未跑全仓库测试。

本地环境：NequIP0.19.1 / Torch2.12.1+CPU。MZ73独立环境：NequIP0.19.1 / Torch2.4.1 / E3nn0.6.0 / Lightning2.6.6 / NumPy1.26.4 / SciPy1.15.3 / MatSciPy1.1.1。独立环境只读复用原Torch等包，新依赖安装到新venv，未修改旧AQCat25环境。

服务器环境目录：`/home/sbq/sbq/fe110_scratch512_env_20261028_v4`。CPU预检目录：`/home/sbq/sbq/fe110_scratch512_cpucheck_20261028_v2`。它们不是正式GPU训练输出目录；CPU临时checkpoint不是可用候选。

## 已纠正并保留的失败记录

预检捕获开发权重均匀假设、NequIP能量偏移字典接口、Windows/Linux路径、OpenMP重复库和依赖索引获取问题。现分别保持原权重、使用元素字典与PurePosixPath、本地隔离数值库、在原生隔离环境安装PyPI哈希校验的公开wheel；不使用`KMP_DUPLICATE_LIB_OK`。

Windows长命令限制改为长度前缀stdin传输；首次原生路径失败发生在训练前。修正路径后的两项原生CPU运行均成功，随后仅修复checkpoint元数据的后处理并复用已成功输出，没有为此重跑模型。旧环境安装尝试、旧配置/请求、失败本地包和原始stdout/stderr均保留，没有覆盖原数据。

## 冻结请求与执行边界

本地证据根：`calculations/fe110_reico_pilot300_20261022/scratch512_20261028_v1/`。

- 当前NequIP包：`package/nequip_v2/`；请求SHA256：`cd0fadb4d199094fcfeb9f1b0e736207bf92fe60664183b83f58ff16f14a0469`。
- 当前微调包：`package/finetune/control/`；请求SHA256：`87a20cb4ae75a09dd423e296d28c5559fec97aeadeb4a05a15148d21deb3c272`。
- 当前汇总：`review_receipt.json`、`reviewed_requests_v2.json`、`export_verification_v2.json`、`native_cpu_v2.json`、`native_postcheck_receipt.json`、`final_tests.xml`。
- `execution_exception_proposals_v2.json`保留最初提案。用户随后明确选择“启动两项训练，总计≤1 GPU小时（推荐）”，见[user_authorization.md](user_authorization.md)；canonical后台策略已追加本次两项精确范围，旧条目不变，没有沿用旧训练授权或伪造调度ID。
- 新NequIP执行器拒绝缺失授权、过期哈希、未知输入、留出loader和超预算配置；正式调用还要求当前canonical范围例外、独占GPU检查、实际CUDA参数设备回执及写一次的退出记录。
- 微调只在明确的`fe110_scratch512_comparison_v1`及冻结512源SHA下允许20轮；旧两轮请求默认门槛不变。预算预检通过不构成执行授权。

## 验收与下一步

正式GPU训练完成并冻结各自开发集选中的候选后，才能比较固定结构误差及低力区方向；不能按已观察的保留误差反复选模。最终加速仍须另行审核和授权同起点DFT对照，使用相同0.02 eV/Å标准、相同化学终态，统计离子步/SCF/核时、失败率及训练/标注摊销成本。

已验证正式NequIP模型CUDA参数设备；正式训练完整性、候选精度、训练充分性、DFT几十步内收敛和实际加速仍待结果审核。下一步：按需检查本次顺序运行，终止后回收两个候选、开发指标、退出/设备/预算证据；不自动增加训练、保留集推理或DFT。

## 正式执行回执

2013个生产输入上传后逐项SHA核验通过；当前精确请求的原生预检通过，原始AQCat25权重/架构在CPU核对。一次顺序启动已返回控制进程PID1363554（无调度ID），NequIP生产者PID1363559，CPU affinity 0–3；实际GPU UUID为GPU-450609b3-d1fd-ac33-d03a-79891be402da。启动快照尚未出现终止回执，不能称为已完成。

序列请求SHA256：`dde58bdc7d1eae203b7a9ca1f7dd002ed2348e67b2c7b69e4387bfca6fc67c79`。`authorization_receipt.json`、`upload_reservation.json`、`production_upload/preflight/launch`回执、`startup_checkpoint.json`与`after_launch_checkpoint.json`保存绑定和启动证据。序列对NequIP复用canonical GPU锁、RSS/墙钟预算检查；微调仍调用现有canonical直接执行器，不直接手写训练替代其门禁。

仓库管理同步仍被既有`sbq_catalyst_agent_workflow.egg-info/PKG-INFO`分类后变化阻塞，未改动该无关文件；不影响上述原生训练执行。

授权与顺序调度回归加入后，主工作区和发布副本各55项测试通过；当前任务源语法与限定Ruff通过。checkpoint_progress进度补读曾遇到SSH连接关闭，未重启/重提训练；截至该失败读取，只有此前已保存的启动/设备证据可用，后续进度需新快照。

后续TCP检查和只读SSH快照已恢复：`final_start_checkpoint.json`仍确认序列控制器存活、NequIP CUDA设备回执存在，尚无终止回执或第二项启动记录。网络补读没有触发训练重启或重提。
