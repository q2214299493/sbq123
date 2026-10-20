# 六任务正式提交授权

2026-10-20，用户在本批审核结果之后明确回复：“提交吧”。

授权范围：已审核 `adsorption_control_paired_vasp3_20261020_v1` 内的
06_C、09_C、10_A，各 baseline/candidate 两臂，共六个普通 VASP 吸附松弛任务。
每任务32 MPI核、每节点32核、NSW=300，其他生产参数、POSCAR、模型来源保持不变。
仅提交到当前 `configs/execution_backends.yaml` 指定的 `sunboquan-codex`，由现有调度配额正常排队。
不得绕过128核账户限制、停止其他作业、增加pilot、修改参数、改变结构、训练或晋级模型。

先复核准备回执、精确六包哈希、远端POTCAR和目标目录未提交状态，再生成逐任务
`SUBMIT_VASP` 规范执行门，使用共享 executor 提交。单次提交异常时保留reservation/receipt，
不自动重投；如已部分成功，只报告实际已提交作业。

这是计算提交授权，不是结果接受、吸附能接受或实测加速收益的认定。
