# 两个C₂代表的冻结536预测复用核查

日期：2026-11-18。**在本次核查的既有记录中，paper_round000/001均没有可复用的冻结536同坐标预测，已列为2项待推理。DFT力标签已经存在，新增DFT需求为0；冻结536的实际力误差仍未知。**

| 代表 | 既有DFT作业 | DFT最大可动力 / eV·Å⁻¹ | 冻结536同坐标预测 | 处置 |
|---|---|---:|---|---|
| paper_round000 | 14003 | 0.1467082641 | 未找到 | 待推理；复用原DFT标签 |
| paper_round001 | 14307 | 0.1098241639 | 未找到 | 待推理；复用原DFT标签 |

最终产物采用`results_v2`；根目录早期产物保留，不作为最终来源绑定。

- [两个代表核查及待推理CSV](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_prediction_reuse_20261118_v1/results_v2/两个代表预测核查及待推理清单.csv)
- [待推理来源清单JSON](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_prediction_reuse_20261118_v1/results_v2/pending_inference_list.json)
- [原始核查、搜索范围及来源哈希](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_prediction_reuse_20261118_v1/results_v2/audit.json)
- [10项验证结果](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/c2_prediction_reuse_20261118_v1/results_v2/verification.json)

## 模型和坐标身份

目标模型为`training536_execution_20261113_v4/returned/candidate.pt`，实际文件SHA256已核对：`2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0`。没有加载模型或执行预测。

| 代表 | 坐标文件SHA256 | DFT物理标签键 |
|---|---|---|
| paper_round000 | `3b417e26a30c6205bab5bb21947d9e4235e711679ae98711d8caecb711b38d59` | `ea885244af8f847c00d08a6be2da5fe6987bf7fcdd818cfb083219c79a01f527:1` |
| paper_round001 | `d57d1fea02710745aa23276a765210f67f306fa845a9e5f2dc6c74c13afdc6b2` | `f2eb6a380f4ed1ef06a6441486d1c6e30cdd1e8fe250339b02a8a79c5c4a368e:1` |

两者均为49原子Fe45+C₂HO，顺序Fe/C/C/O/H，底18Fe固定。既有磁性及兼容性审核资格沿用[上一轮报告](C:/Users/86177/Desktop/work/docs/reviews/fe110_c2_path_reuse_20261118/README.md)，本轮重核2个坐标和OUTCAR哈希、指定离子帧及原始力对应。job14003仍保留控制器退出0与调度器终态未知的区别，不自动科学验收或训练准入。

## 已有预测为何不能复用

已验证614帧结果的checkpoint、请求哈希、614个ID和每帧坐标来源。两个目标均没有坐标文件哈希匹配；进一步逐一比较614个输入的元素顺序、晶胞、固定掩码及数值坐标，也没有同坐标匹配。数值标准为XY周期最小镜像下逐原子最大位移≤1e-10 Å，允许XY包裹，不做刚性拟合、不用0.10 Å近重复阈值替代精确对应。

已在`calculations`及`docs/reviews`的JSON/YAML/Markdown中检索目标模型完整哈希，绑定31个相关文件。冻结536的已登记结果为该614帧预测；旧78开发缓存仍属于相同开发来源，不提供这两个CHCO坐标。搜索不穷尽未登记的远程缓存或只存在于二进制文件中的结果，因此结论限定为本次核查范围内未找到。

找到了两个目标的历史同坐标预测，并验证候选坐标及请求绑定，但它们的checkpoint均不同：

| 代表 | 历史输出目录 | 历史checkpoint SHA256 | 排除理由 |
|---|---|---|---|
| paper_round000 | `return_13883/output` | `cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0` | 与冻结536哈希不一致 |
| paper_round001 | `return_14304/output` | `209e7a50ce10beb515e19b945fbf12b25591f9ff89077acae6432ba3e16b9406` | 与冻结536哈希不一致 |

这些历史结果不能冒充冻结536预测。因此本轮不报告冻结536的RMSE、MAE、方向余弦或最大误差，相关字段保持null；DFT最大力是参考标签的力大小，不是模型误差。

## 待推理清单与验证

清单绑定2个原始坐标、目标checkpoint、原OUTCAR及物理标签键，保留C/O/H/可动Fe角色和力单位。后续若执行，应沿用冻结536原生ASE FP32、eval、tags=0及`apply_constraint=False`原始力口径，保存全部49原子力，评价时排除底18Fe。清单不是执行请求：`execution_authorized=false`，未选择服务器、未分配或提交GPU任务。

4个针对性测试通过：同坐标旧模型拒绝、同模型近重复坐标拒绝、XY包裹与Z位移区别、固定掩码变化拒绝。语法和限定Ruff检查通过；10项数据验证通过，包含614帧来源绑定、旧模型排除、未知误差保持空值、源文件哈希及冻结守卫。

512/536包及78/53/16分区、模型、协议、原任务指针均保持不变。未重新运行614预测、未启动GPU、未训练、未提交DFT、未修改远程作业或自动准入。

本轮按项目约定调用RSI一次，在`local_protocol`阶段失败：`ValueError: Codex protocol probe failed: ['features', 'list'], exit=1`。模型回合0、资料工具0，无建议或经验动作；未重试、未修改配置。该失败不改变本地文件核查结果。[RSI本次记录](C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/runs/20261118_181308_bc2b1605/review.md)；[看板](C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html)。

唯一下一步：在另行获得执行授权后，仅对清单中的2个坐标执行冻结536固定结构力预测，并与已有DFT逐原子比较。
