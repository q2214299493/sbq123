# C2 补充12构型：GPU启动器修复与双机独立重投

## 结果与边界

2026-11-07 00:41:57 CST，已依据用户“修复”及双机独立运行授权提交：

| 后端 | 新 Slurm 作业 | 请求 SHA256 | 最新原生状态 |
|---|---|---|---|
| MZ73 | 11721 | `3235ca9065c139e6ea2dbc4a86a8c008949d5573043c08822abb682b4b24ad72` | PENDING(Resources) |
| BUCT2 | 1357 | `c190a59bcfd01e435a281e92b719aef9cbe71ca592c32312eddcee0369d93388` | PENDING(Resources) |

两份独立执行，不要求对端先停止，不再等待 winner permit。先正常完成、且通过 work 端位点/连接/几何审核的结果才可采用；不是先启动即取消另一份，也不是程序退出0就算结构合格。

原始12个POSCAR、冻结FT512权重和优化预算完全不变：05_S1/S2、06_S1/S2、07_S1、09_S1、11_S1、12_S1、13_S1、14_S1、18_S1/S2；每个最多80步、预测力目标0.10 eV/Å、LBFGS maxstep0.20 Å。单卡/4CPU/32GB/600秒，Torch分配上限16GiB。没有训练、权重晋级、CPU回退、VASP或正式能量登记。18的7吸附原子域外提示及无排序限制保留。

## 旧作业和根因证据

- MZ73 11396：原生控制器记录00:02:44启动、`WEXITSTATUS 1`；生产者记录在 `nvidia-smi -i 1` 返回6后退出，未加载模型、优化0步。旧日志没有保存该命令的完整stdout，因此不能追溯证明当时所有设备映射细节，也不能归因于结构、势函数精度或显存不足。
- BUCT2 1355：替换前检查准确UID、请求Comment及PENDING状态后取消；后续 `scontrol` 明确显示 `CANCELLED`。旧文件和失败证据保留，没有删除计算数据。
- 两台SSH登录会话受管理员DevicePolicy限制，登录NVML错误不代表任务内GPU不可用。没有改变安全规则、驱动或其他人的作业。
- 旧脚本错误地把 `SLURM_JOB_GPUS` 直接作为NVML查询索引，并在MZ73复用了要求UUID可见性的direct-only模型证明。BUCT2旧包还带有不符合最新授权的首启动许可等待。三处执行层问题均已在新包中替换，旧哈希绑定包没有暗改。

## 修复和验证

1. 在真实Slurm分配内，用CUDA逻辑设备0获取物理PCI地址，再按该地址查询NVML并核对UUID/PCI；不把Slurm全局编号、CUDA逻辑编号、NVML编号混用。C接口按[NVIDIA CUDA Runtime文档](https://docs.nvidia.com/cuda/archive/12.1.0/cuda-runtime-api/group__CUDART__DEVICE.html)核对。
2. 按实际模型参数所在设备证明CUDA执行，同时记录原生job-ID；CPU参数、其他计算进程、显存不足和身份不匹配仍拒绝。保存命令退出码、stdout、stderr及安全的设备环境变量，避免重复丢失根因。
3. MZ73无模型短测试11716发现当前驱动不支持查询字段 `minor_number`；移除该非必要字段后，11720真实CUDA运算和物理PCI/UUID查询通过。测试中CUDA_VISIBLE_DEVICES=0，分别映射到物理41:00.0、A1:00.0。没有优化任何结构。
4. BUCT2短测试1356因资源忙未获分配，不算CUDA验证通过；新1357在获分配后执行同样设备检查。
5. 两台原生 `bash -n`、50项包内工件哈希、12份handoff、请求/授权/模型与CUDA运行库哈希、定制Fairchem导入和CPU张量预检通过。既有可信vendor常数的torch.load FutureWarning保留，没有修改模型加载语义。
6. 8项针对性单元测试通过；`tests/test_gpu_resources.py`和`tests/test_aqcat25_handoff.py`共8项回归通过；`tests/test_registry_write_cli.py`4项回归通过；限定目录Ruff及6个Python文件语法检查通过。
7. canonical registry plan/review/apply及回读通过：181条作业/文件/状态元数据，2条旧workflow终态更新；零科学结果。1355在通用registry中映射为FAILED终态，但明确保留原生CANCELLED及“人为替换、非结构失败”的原因。

尚未验证：新生产作业实际模型加载、12个构型优化、位点/连接保持、DFT收敛和实际加速收益。目前只是排队，不是再次优化失败。

仓库末尾 `repo-state sync --safe-only` 已执行一次，遇既有分类冲突 `sbq_catalyst_agent_workflow.egg-info/PKG-INFO` 后退出1，未重试或修改该无关文件；GPU提交及registry回读不依赖此同步。

## 可复现路径与下一步

- 源码：`archive/fe110_c2_gpu_repair_20261107/`。
- 本地不可变包、预检、短测试、提交、原生快照和registry凭证：`calculations/fe110_c2_site_supplement_20261106/gpu_independent_repair_20261107_v1/`。
- 两台独立远程根目录：各自 `/home/sbq/sbq/fe110_c2_supplement_independent_20261107_v1`。BUCT2复用已验证的原3.10环境，不再传输3.5GB环境。
- 进度检查：`python -m archive.fe110_c2_gpu_repair_20261107.transport status`，后续快照追加，不覆盖既有证据。
- 下一步仅回收首先完成的合格预测载荷，逐构型审核初末位点、Fe配位、连接、H归属、解离/脱附及重复组，再决定VASP；本次不自动提交VASP。
