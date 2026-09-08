# 从粗路径局部峰提前进入标准 Sella

这是独立的可选候选入口：直接复用已经保存的 MatRIS 完整粗路径和 checkpoint，
不再执行 NEB。父路径可以未收敛、整体多峰；原有“收敛、几何合格、全路径单峰”
自动细化入口保持原规则。新入口没有任何 VASP、训练或 TS 接受权限。

## 输入与审查

入口：`python -m scripts.matris_sella_local_peak`。
输入是现有 `dual_model_ml_neb_request`、对应完整候选 manifest、所有绑定的结构文件，
以及 work 出具的 `sella_local_peak_work_review`。不接受正在写入的 VASP 输出或
缺少路径/模型来源的孤立构型。文件必须先保存为不可变的审查快照。

每次只选一个局部区段，索引从零开始。`start_image < peak_image < end_image`，
在这一区段内重新从有限的 MatRIS 预测能量判断，必须只有所选的一个严格局部峰。
允许区段以外还有峰。平台峰、端点最高或同一区段包含多个峰时，返回明确错误，
不自动猜测初猜。多步骤路径需分别审查、准备独立请求和预算；数值单峰不能证明
单一反应事件，`reaction_event` 和 `single_event_review_passed` 必须来自实际审查。

保留父路径的原子顺序、晶胞、PBC、固定掩码/坐标、端点及现有几何规则；不降低
碰撞、相邻位移、周期映射、保留键和受监测反应键的限制。搜索中仍重新检查完整
父路径，把候选临时放回所选峰位以检查与两侧的连续性；不要求全路径收敛或单峰。
只有全原子固定约束受支持，部分 Cartesian 固定掩码会被拒绝。

work 审查 JSON 的字段如下；下列尖括号是待真实证据替换的说明，不是可执行样例：

```json
{
  "document_kind": "sella_local_peak_work_review",
  "reviewer": "<实际审查者>",
  "decision": "accepted_for_bounded_local_search",
  "single_event_review_passed": true,
  "reaction_event": "<该区段的目标成断键事件与审查依据>",
  "source_request_sha256": "<原始请求文件SHA256>",
  "parent_manifest_sha256": "<粗路径manifest文件SHA256>",
  "segment": {"start_image": 0, "peak_image": 2, "end_image": 4},
  "settings": {"fmax_eV_per_A": 0.05, "max_steps": 20, "delta0_A": 0.02},
  "limits": {"maximum_evaluations": 100, "maximum_wall_seconds": 120, "maximum_displacement_A": 0.15}
}
```

其中索引和数值仅用于说明字段，不是当前 Fe 任务的已批准初猜、预算或物理阈值。
步数、调用次数、时间、总位移必须逐次审查，不设自动追加预算。

## 准备与运行

以实际文件路径替换下面命令中的示例名称。准备不加载模型、不计算、不授权执行：

```powershell
python -m scripts.matris_sella_local_peak --prepare --source-request source-request.json --parent-manifest path-manifest.json --review local-review.json --request local-search.json
python -m scripts.matris_sella_local_peak --request local-search.json --preflight
```

准备会生成 `local-search.json` 和 `local-search_inputs/`，按原始字节复制审查所需
请求、完整路径、初始结构和审查记录，采用相对路径引用；checkpoint 不复制。
两者应一起传输。目标已存在则拒绝覆盖。准备的 `execution_authorized=false`，
只有取得这次具体计算授权后才能改为 true，再绑定最终请求哈希。

生产环境需要安装本仓库及 Sella 依赖，并使用现有 MatRIS 环境和模型源码。
此入口使用包导入，不属于旧的平铺单文件部署方式。仅在 MZ73 已分配的单 GPU
Slurm 作业内执行；新目录必须位于 `/home/sbq/sbq/`。下列是作业内命令形式，
不是提交命令：

```bash
JAX_PLATFORMS=cpu python -m scripts.matris_sella_local_peak --request local-search.json --checkpoint /home/sbq/sbq/REVIEWED_CHECKPOINT --output /home/sbq/sbq/NEW_OUTPUT_DIRECTORY
```

模型在 CUDA 上预测能量和力。Sella 步数和模型 E/F 调用数是不同预算；每次模型
调用前，包括有限差分试探构型，都检查几何和预算，调用后检查有限值与时间。
时间限制是协作式检查，不能中断卡住的单次模型调用；作业包装器/Slurm 必须另设
已审查的硬超时。加载模型的时间计入协作式预算。CPU 解析势注入仅用于离线测试。

## 结果、失败与后续

- `run_record.json`：状态、模型调用数、耗时、失败定位。
- `sella/candidate_manifest.json`：原始种子来源、局部区段、Sella 设置、每个已接受
  构型和最后有效构型。几何错误记 `failed`；耗尽调用/时间预算记 `budget_exhausted`；
  达到步数上限但未收敛记 `optimizer_not_converged`。不把这些失败直接归为模型错误。
- `dual_model_gpu_ml_neb_path_manifest.candidate.json`：保留完整父路径和其真实的
  收敛状态，另附 Sella 结果。Sella 收敛不改写父路径收敛，不替换其图像和能量。

返回时把请求、输入包、结果一起带回 work。用打包后的 `source/request.json`
作为原始请求参数，给新候选出具 `accepted_for_force_diagnosis_only` 审查后，沿用
`scripts.prepare_ml_candidate_active_learning --method ml_neb_sella`。它重新校验
局部审查/模型/构型/位移绑定，保留完整路径采样，要求 Sella 最后构型获得精确
VASP 力标签。此标注入口仍要求完整父路径至少五幅图像；三幅图像只支持候选搜索。

只有最后有效构型存在时，预算耗尽的结果才可进入上述诊断。几何失败的轨迹保留，
不能按成功候选提交；恢复应重新审查保存构型、更新输入绑定并使用新目录，不能
直接重复同一失败请求。当前入口不恢复 Sella 的 Hessian/优化器内部状态。

新模型通过现有误差、保留集和留出集门槛后，重跑准备保留完整路径及局部搜索偏好，
但标记 `requires_new_path_and_segment_review`。模型变了，峰位可能改变，旧区段
审查不能自动授权再搜。最终 TS 仍按原有 VASP/振动/连接性协议验证。

## 验证范围

离线测试实际调用 CPU Sella，在合成多峰势能面上验证局部搜索、固定原子和父路径
保留、异常/预算停止、审查过期拒绝，以及现有双模型标注与重跑接口。
这些是软件行为测试；本入口尚未在 MZ73 的真实 Fe 反应上执行，也未证明节省 DFT
成本或提高 TS 成功率。当前 VASP job 9742743 继续原任务，本次代码修改不启动搜索。
