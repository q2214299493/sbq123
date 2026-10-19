# Fe(110) 吸附分组力损失/均衡采样：接入与测试

日期：2026-10-19。用户请求：`开始测试`。

结论：新适配器通过本地测试和 MZ73 真实 Fairchem 的无模型 CPU 接口测试。
没有加载 AQCat25 模型 checkpoint，没有 GPU 训练、推理、新 VASP 或模型晋级。
这证明代码和数据通路可用，不证明模型精度或 VASP 加速已改善。

## 实际修改

- `scripts/adsorption/force_role_data.py`：校验角色与元素、固定原子、逐原子权重，
  将数据写入 ASE DB；训练采样概率按真实数据库行序进入 NPZ。
- `force_role_runtime.py`：可求导的逐图像/结构分组向量力损失，以及单进程、
  有放回、可精确恢复的来源/阶段采样器。
- `role_force_trainer.py`：显式选择的 `RoleForceTrainer`，接入现有 EquiformerV2
  训练器接口。训练目标沿用原归一化；验证指标恢复为 eV/Å，输出分组、C/O/H、
  邻近 Fe、其余 Fe 和 replay 指标。可用 `forces_role_vector_mae` 作为开发集主指标。
- `force_finetune.py`：保留旧版适配，补齐新池的可选角色数据通路。
  发现新角色字段却仍用旧运行时契约时拒绝验证，防止“配置有权重、训练却没用”。
  新契约 v3 要求显式选择新训练器、将角色字段送入图转换，并绑定三个运行时源文件。

没有修改已部署 Fairchem 源码、旧运行包、默认 AQCat25 模型或 VASP 参数。
此次 `2:1:1:2:1` 权重与 3 Å 分组半径没有硬编码进通用损失/采样器；
数值来自各自审核过的逐帧清单。固定原子和化学角色不通过复制 C46 等编号指定。

一个 epoch 的抽样次数等于训练集长度，但**有放回抽样不保证每帧每轮恰好出现一次**。
开发集仍用原顺序/均匀遍历方式；留出集不进入训练或 epoch 选择。
采样器限单进程，多进程显式拒绝，不能默默沿用错误的分布。

## 已执行验证

| 检查 | 结果 |
| --- | --- |
| 语法编译、Ruff | 通过 |
| 相关单元/回归测试 | **124 passed，0 failed/error/skipped** |
| 真实训练/开发标签 DB 往返 | **248/60** 全部逐原子力、顺序、固定层、零 tags、角色与概率一致 |
| 原始训练池 | SHA256 不变，`6deb86d4fcb2bfbde29f7d2d6faf3f2663afa2ac04c9d8a79659c876e6234330` |
| 本地 autograd | 数值求导一致，固定原子梯度为零，角色权重实际改变梯度 |
| 本地混合精度 | FP16/BF16 输出均以至少 FP32 计算损失，梯度有限 |
| MZ73 实际 Fairchem CPU | registry 类路径、数据工厂、Subset 重排、采样、collater、损失与指标通过 |
| 断点恢复 | epoch/批次游标恢复后的抽样序列与完整序列对应后缀一致 |

真实数据只在 work 构建数据库；MZ73 使用 3 个训练、3 个验证的**合成测试夹具**，
没有上传实际结构。MZ73 的 Torch 为 `2.4.1+cu121`，本机为 `2.12.1+cpu`。
CUDA 被隐藏且未初始化。框架导入会读取其既有球谐常数 `Jd.pt`，不是模型 checkpoint。

独立证据复核重新检查原池、数据库和当前源文件哈希、测试 XML，以及手算结果：

- 真实标签加人为 `0.02 eV/Å` 三分量偏移，得到 `sqrt(3)*0.02 = 0.03464101615 eV/Å`；
  这是损失计算检查，不是 ML 预测误差。
- 原生接口合成测试的归一化损失约 `0.17320509`，恢复物理单位后约
  `0.50009805 eV/Å`，与指定测试偏移及归一化比例一致。
- 原 46 帧新留出和 16 帧已观察留出未建立训练/验证 loader。
  canonical 标签完整性校验可以读取其记录，不等于用于梯度或模型选择。

## 测试中发现并修正

1. 原生 CPU 首次失败来自测试夹具：归一化对象需要可调用接口，且模拟 ASE DB
   析构需要初始化空数据库列表。已修正夹具，保留首次 stdout/stderr/退出记录。
2. 新适配器的混合精度测试发现 Double/Float 点积冲突。已统一损失计算精度，
   避免把静态权重先量化为半精度，再用独立 FP16/BF16 回归和 MZ73 CPU 测试确认。
   这是本次新代码的工程问题，不能据此解释旧 checkpoint 的 C 力误差。

最终原生测试为 `native_cpu_smoke_4.*`；早期成功记录与失败记录均保留，没有覆盖。
没有独立 `report-quality-gate` 技能可用，以数值重算、来源/单位/哈希及实际接口测试替代。

## 证据与复现

产物：`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_runtime_test_20261019_v1/`
中的 `local_smoke_receipt.json`、`native_cpu_smoke_4.json`、对应 receipt、
`final_scoped_tests.xml` 和 `verification_receipt.json`。
源码与测试入口：`archive/fe110_adsorption_runtime_test_20261019/`。

```powershell
python -m pytest -q tests/test_adsorption_role_runtime.py archive/fe110_five_c2_adsorption_20261006/test_adsorption_finetune.py archive/fe110_five_c2_adsorption_20261006/test_launch_adsorption_finetune.py tests/test_b3_ml_governance.py archive/fe110_adsorption_pool_rebuild_20261019/test_pool.py archive/fe110_adsorption_calibration_20261018/test_current_trajectories.py
```

证据生成器均拒绝覆盖已有结果；不要原样重跑数据库构建或已存在的原生 attempt。

## 未验证及下一步

CPU 半精度张量测试不等于 GPU 上的完整 AQCat25 前向、反向、优化器和 AMP 测试。
新适配器还没有形成获准提交的正式训练包；打包时需包含新源文件、实际 CLI/PYTHONPATH、
冻结起始 checkpoint、分组指标选择及训练预算。原来的部署脚本不能被当作已完成的新训练包。
O/H/replay 指标可用于审查，但本次没有训练曲线，也未验证实际早停/保留性能。

下一步：准备 v3 受限训练对照包供审核。实际 GPU 执行仍需单独授权；
模型精度、结构是否偏离及 VASP 步数/耗时收益必须在后续验证，不能以本次测试替代。
