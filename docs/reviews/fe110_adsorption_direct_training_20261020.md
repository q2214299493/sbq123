# 吸附微调 GPU1 直跑：启动后 DDP 退出，修复待重新授权

客户端日期：2026-10-20。用户在明确 GPU1 直跑/目录别名修正/两组顺序各30分钟、
不自动重试的范围后回复“跑”。本次已执行一次真实 GPU 启动；不是仍停留在准备。

## 实际结果

- 直跑ID：`direct-adsorption-role-ab-20261020-v1`；控制器PID `2888886`，
  control PID `2888895`。无 Slurm 作业号，`scheduler_job_id=null`。
- 北京时间00:22:34启动、00:22:52退出，生产者约18秒；exit1。
  模型参数实际位于CUDA `cuda:0`，对应物理GPU1
  `GPU-450609b3-d1fd-ac33-d03a-79891be402da`。
- control 在第二次forward的DDP检查处失败，未完成一个epoch，未输出有效候选checkpoint。
  第一次forward/backward已发生，但不能据此声称完成一次有效优化器更新。
- controller依约停止；treatment未启动，没有自动重试、晋级、留出模型评估或新VASP。

## 输入、预检与工程修正

冻结comparison仍为`f5db5cb7b1e98d6153bba8bbc41a0d0697fd29c79162a4ef0298a91969660987`，
两组原请求仍为control `dbad960b964805277333d21bce0a1669e38085c9ab742f5ed53a88a9a5b2d026`、
treatment `8b740e698d2bac32bb9f918012372a1aaf4e410d9bfef61397bb55ce95ab69ca`。
原模型、248训练/60开发/46留出划分、原始力与原请求绑定文件均保留原字节；
16帧已观察留出仍隔离。新增直跑层单独绑定，不执行旧Slurm wrapper。

直跑请求SHA256：`b0cc4cf03ee9e2fd52fa0c7deb86f204e771b15263be8001af703f29af7d6203`。
后端权威配置只增加本次独立例外；不改默认Slurm角色，不借用旧任务例外。
规范化路径核查接受已实测的`/home/sbq/sbq`→`/home/ubuntu/hdd/sbq/sbq`，
仍禁止逃逸该边界。GPU UUID/既有进程/共享互斥锁、4CPU affinity、32GiB进程树RSS、
各1800秒/总3600秒及只终止本执行器子进程组的限制已实现。

第一次SSH连接在握手前关闭；TCP和随后连接复核恢复，未重复任何模型运行。
原生CPU磁盘预检发现POSCAR坐标在Windows/Linux矩阵换算后有机器舍入差异：
两组各308行，最大`1.7763568394002505e-15 Å`。晶胞、PBC和原始力逐位相同。
新增、单独哈希绑定的CPU预检适配只对坐标读回使用`atol=1e-12 Å, rtol=0`；
原始文件哈希、力、晶胞、PBC、角色/概率、固定层仍严格检查。没有移动或优化结构。
适配请求SHA256：`1ef4e590e27a2e8d372075c907e290b2e8d4dd41b1857896cc8feff6b3905b3b`。
补充预检是纯CPU，未覆盖原失败日志或任何已绑定文件，两组均通过实际CLI/架构检查。

## 已确认的训练器根因

实际错误：`Expected to have finished reduction in the prior iteration`。
DDP报告未获梯度的参数索引374–382。用同一warmstart在CPU上只构建模型、不做forward，
确认这9项全部是`output_heads.energy.energy_block.*`，总可训练参数张量408项。
MZ73原生BaseTrainer即使world_size=1也构造默认DDP，没有启用unused-parameter检测。

新`RoleForceTrainer._compute_loss`原实现只返回力损失，丢掉能量输出的计算图依赖。
这使能量头没有梯度，阻塞下一次DDP reduction。本次退出是新适配器的执行缺陷，
不能据此判断AQCat25对这些吸附态的精度，也不需要新增VASP标签来修复这个错误。

最小源码修复：对已存在的能量输出增加`0.0 * out["energy"].sum()`图连接。
能量损失系数仍为零，力目标/权重/采样/梯度不改；不是开始拟合能量。
修复只在仓库源码和CPU回归中生效，已失败的远程GPU运行时仍保留原版，未热修改或重投。

## 验证

- 本地相关回归174项通过，包含GPU身份/预算/授权、源哈希、进程组保护、坐标数值边界、
  严格力比较与既有角色/采样/治理测试；编译及作用域内Ruff通过。
- MZ73真实Torch/DDP的CPU双头小模型回归：旧代码完成一步后复现同类DDP错误；
  修复代码连续两步通过，能量头梯度严格为零，力损失和力梯度与旧代码首步完全一致。
  这不是AQCat25完整模型训练，不初始化CUDA。
- 11份原生产者/预检/诊断文件及训练日志已按原字节收回，并与远程SHA256逐项核对。
- 首次本地测试曾使用pytest保留fixture名、辅助脚本有unused import，已修正；
  均在GPU执行前，非本次DDP退出原因。

新角色源码SHA256：`af3019d8755bb3a91bf2c97dae5c491f60dc8d90bb4792773cb1fb6cb2e4a90e`。
CPU回归证明小模型/DDP机制修正，不替代完整AQCat25 GPU/AMP与优化器验证。

## 产物与下一步

证据目录：`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_direct_20261020_v1/`。
`package/`保存原执行请求；`portable_preflight/`保存补充CPU适配；`returned/`保存原字节证据。
`collection_receipt.json`记录来源哈希，`scoped_tests_postfix.xml`记录修复后回归。

下一步只需重新绑定修复后的运行时和两组请求，并申请一次新的GPU执行授权。
不要继续使用旧请求热替换源码；不改结构、VASP参数或训练目标，不自动重投。
新运行中应先确认同一进程连续两次原生前后向成功，再继续其余授权步数；
仍无模型晋级或实际VASP加速结论。
