# 冻结536固定结构力诊断：标签核查与已有开发缓存

日期：2026-11-14。**科学任务尚未完成：新的逐帧预测被GPU入口连接故障阻塞。**已完成614帧标签核查、冻结checkpoint缓存指标复核及后续分析准备；不能把本报告称为完整的训练/开发逐帧诊断。

用户授权：“先用已有、审核合格的训练/开发标签诊断冻结536的固定结构力误差，再决定哪些新单点值得计算。”本轮未训练、未优化结构、未提交DFT、未启动GPU作业、未运行新势函数预测，未使用53保留测试或16隔离帧进行预测/选点。

## 1. 固定对象与执行阻塞

冻结536候选SHA：`2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0`。
源文件：`calculations/fe110_reico_pilot300_20261022/training536_execution_20261113_v4/returned/candidate.pt`，126,477,568字节。本轮没有更换checkpoint、恢复训练或重新选择epoch。

按项目入口执行了一次`python -m scripts.gpu_resources`：BUCT/MZ73（36039）与BUCT2（55909）均返回连接关闭，可用性未知。一次针对性SSH握手诊断确认：TCP已建立，在收到远端SSH版本并进入认证前，对端关闭连接；不能解释为GPU已满、密码错误或作业状态。未重复循环连接，也未上传或启动预测任务。

本机已装环境缺少该模型原生Fairchem/e3nn/torch_scatter，WSL未安装。基础Anaconda只读加载checkpoint时出现OpenMP重复运行库错误，未使用不安全的重复库覆盖设置。随后使用已有`care_fe110_ft`的CPU PyTorch环境成功只读加载checkpoint元数据，CUDA未初始化，没有model forward。没有安装或修改环境来替换原生预测实现。

本地已回传训练结果中只有checkpoint和开发集汇总，没有可核查的614帧逐原子预测。远端其他缓存目前无法查证。GPU入口恢复后应先查缓存，有兼容结果则复用，否则再执行本次授权的固定结构预测。

`tasks/current_task.md`仍指向另一项六作业VASP对照任务，本轮保留该任务指针，没有查询或干预那些作业。

## 2. 614帧标签资格与隔离

复用所属模块`validate_label_row`核查每帧结构、原子序、底18个Fe固定掩码、力数组有限性、原标签文件SHA、力/能量元数据与来源一致性。既有原始证据的SCF和坐标—力对应均通过。

| 分区 | 原包帧数 | 原始E/F/局域Fe磁矩证据完整 | 保留原force-only范围、缺局域磁矩 |
|---|---:|---:|---:|
| 训练 | 536 | 285 | 251 |
| 开发 | 78 | 18 | 60 |
| 合计 | 614 | 303 | 311 |

303帧用于严格主分析，311帧应按原资格单列敏感性分析；这只是诊断分层，**不改变任何标签磁性等级或准入状态**。53测试、16隔离及其他外部来源没有进入预测清单。

严格训练子集中≤0.05 eV/Å的24帧全部是C₃H₂O/0099训练家族；严格开发18帧没有≤0.05 eV/Å帧。原force-only范围仍有训练侧C₂HO低力9帧、C₂H₂O低力17帧、C₂H₃低力4帧等，开发侧也有低力帧，但其逐原子磁矩证据缺口保留。不能因缺局域磁矩就自动宣布原force-only标签无效或要求全部重算。

低力使用全部可动原子的最大DFT力，排除固定18个Fe，包含上27个Fe与吸附质。它是标签区间，不证明结构是独立稳定极小值。

## 3. 可核实的缓存结果

以下数值直接从本轮只读加载的冻结checkpoint原生`val_metrics`中恢复，并与已绑定的native-best恢复记录核对。**它们是原78开发帧的既有缓存，含18严格+60原force-only范围，不能拆成严格子集或分组成/力阶段的新结果。**

| 原子角色 | 原子观测数 | 力向量MAE（eV/Å） |
|---|---:|---:|
| 吸附C | 161 | 0.100748 |
| 吸附O | 75 | 0.087649 |
| 吸附H | 143 | 0.032635 |
| 近邻可动Fe | 410 | 0.057780 |
| 其他可动Fe | 1696 | 0.023833 |

近邻/其他Fe沿用原标签角色掩码。它们不是本轮按误差重新分的组。

![已有78帧开发缓存角色误差](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/force_diagnosis536_20261114_v1/cached_development_role_MAE.png)

可确认：C/O的每原子平均误差更大，近邻Fe约为其他Fe的2.424倍。全部可动Fe合并向量MAE为0.030442 eV/Å。Fe贡献约70.01%的绝对向量误差总和，同时占84.75%的原子观测；这些是绝对误差统计，**不是平方误差贡献率**，不能由原子数量占比推断Fe是唯一主因。

原生全开发集方向余弦汇总为0.534076，不能拆分元素/阶段或恢复反向比例。接近零力时的具体方向诊断仍需逐原子向量。

没有逐原子预测时，无法恢复向量RMSE、最大误差、最大ML/DFT残余力、“ML小力但DFT大力”的构型、严格子集结果、逐组成/阶段结果或训练误差。没有从原生loss、能量阈值指标或平均余弦臆造这些量。

## 4. 权重口径与待验证解释

训练536帧全部采用均匀可动原子权重；开发78帧保留角色加权。按帧平均，可动Fe在训练损失中的权重为84.458%，在开发评价权重中为43.544%。这是既定均匀小试和原开发口径的差异，本轮没有修改权重。

- 原生按帧/原角色权重开发向量MAE：0.061994 eV/Å。
- 将5个互斥角色的绝对向量误差总和除以2485个可动原子观测：0.036850 eV/Å。
- 原生力分量MAE：0.018158 eV/Å。

三者权重、平均单位或范数不同，不能直接当成同一指标的改善/退化。

待验证解释：角色和优化阶段权重可能影响C/O、近邻Fe与其他Fe之间的误差分配；现有C₃低力训练数据仍集中于单一来源。仅凭缓存均值不能认定训练不足、过拟合、可动Fe主导交接失配或新增数据一定有效。需要冻结模型在同坐标训练/开发标签上的逐帧向量才能区分这些解释。

## 5. 新单点决定与后续诊断口径

**本轮新增单点选择为0；上一轮20个高力/分离组分几何备选全部保持待定。**缓存角色平均误差无法给未标注候选赋予ΔF，也不能证明某个候选值得优先计算。C₄真实坐标、完整C₃独立近稳定验收的来源缺口仍保留。

后续只在结构SHA和原子序一致时比较：
`vector_RMSE = sqrt(mean_i ||F_ML,i-F_DFT,i||²)`；
`vector_MAE = mean_i ||F_ML,i-F_DFT,i||`；
分量MAE另列。方向余弦沿用已有非零力阈值1e-8，报告有效原子数。固定原子不参与可动力统计。

预测接收器会拒绝模型SHA错误、坐标SHA错误、缺帧/重复/额外样本、受保护分区以及形状或非有限值问题。按训练/开发、严格/原force-only范围、组成、DFT最大力区间及C/O/H/Fe角色分别统计。任何小ML力/大DFT力个案仍只是固定结构诊断，不是实际ML优化终态或VASP加速证据。

## 6. 输出、检查与继续条件

目录：`C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/force_diagnosis536_20261114_v1/`。

- [qualified_reference_labels.json](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/force_diagnosis536_20261114_v1/qualified_reference_labels.json)：614帧原标签、资格分层、角色与DFT力区间。
- [prediction_scope.json](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/force_diagnosis536_20261114_v1/prediction_scope.json)：614个固定坐标输入、冻结checkpoint与待完成的GPU绑定；未启动。
- [cached_development_role_metrics.json](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/force_diagnosis536_20261114_v1/cached_development_role_metrics.json)：本轮核实的原开发缓存及口径。
- [new_DFT_selection_status.json](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/force_diagnosis536_20261114_v1/new_DFT_selection_status.json)：20个备选逐项待定，无新增DFT授权或提交。
- [final_state.json](C:/Users/86177/Desktop/work/calculations/fe110_reico_pilot300_20261022/force_diagnosis536_20261114_v1/final_state.json)：科学任务未完成与只读完整性状态分开报告。

已执行614帧源标签校验、冻结checkpoint哈希与元数据核对、分析器9个数值/来源守卫测试、限定Ruff和语法/导入检查。图像已实际打开复核，使用中文、向量MAE单位、原子观测数及“缓存/未新预测”标识；报告按`report-quality-gate`复核语言、单位、数字、链接和证据边界。

512/536包、78/53/16分区、checkpoint、注册库、后端配置、方法协议与原任务指针保持不变。没有创建完整逐帧诊断结果文件来冒充完成。

RSI按约定仅调用一次，启动1个内部模型回合后因`unexpected notification or turn mismatch`阻塞，资料工具执行0、采用经验0；未重试或修改其配置。[看板](C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html)。本报告结论来自直接文件和checkpoint缓存。

**下一步：GPU入口恢复后沿用本次授权，先查兼容逐帧缓存，无缓存则完成614帧固定坐标预测，再确定新单点；无需重启训练，也不沿用旧53测试集的推理授权。**
