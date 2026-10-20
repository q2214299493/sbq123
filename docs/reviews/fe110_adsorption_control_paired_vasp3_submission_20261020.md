# 三组配对 VASP 松弛正式提交

2026-10-20。用户在输入审核后明确授权“提交吧”；六任务已由规范执行器实际提交。
这里 supersede 的只是“尚未授权/提交”状态，不修改历史准备清单或六包输入。

## 作业清单

下表是截至2026-10-20 15:13:59 CST保存的逐作业实时LSF快照。
RUN表示调度运行状态，不代表电子/离子收敛；本次未解析实时能量/力。

|构型|原始 AQCat25 起点|冻结微调 control 起点|
|---|---|---|
|06_C|9910781 / RUN|9910783 / RUN|
|09_C|9910785 / PEND|9910787 / PEND|
|10_A|9910789 / PEND|9910791 / PEND|

后端 `sunboquan-codex`（10.68.0.103，nsgkn_chengdj3），队列 `Gkn_normal`。
每任务32核、每节点32核，NSW=300。保持已审核PBE/400eV/Gamma5×5×1、
SIGMA=0.20eV、ALGO=Fast、EDIFFG=-0.02eV/Å、磁性初始化和固定层设置。
没有增加pilot、重新运行GPU、微调或晋级模型，也未停止任何旧任务。
提交前账号已有两个32核旧任务，128核运行配额不变；六新任务合计请求192核，正常排队而非同时占用。

远端根目录：`~/sbq/Fe110/adsorption/control_paired3_20261020_v1/`，
下为 `{06_C,09_C,10_A}/{baseline,candidate}`。
本地根目录：`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/`。

## 实际验证与执行证据

- 六包精确输入哈希仍匹配准备回执；三组方法/资源文件配对一致。
- 提交前六个远端目标及 `.submission-reservation` 均不存在，远端登录账号与backend配置一致。
- Fe-C-O-H、Fe-C-H POTCAR全文SHA、PAW-PBE家族、TITEL物种顺序与已审核绑定一致。
  正文未下载、未写入Git；执行器复制后再次核验全部远端输入哈希。
- 六个独立规范执行门均明确允许 `SUBMIT_VASP`；不是手工修改允许动作字段。
- 六个本地/远端reservation与六份成功 `submission_record.json`，无重复提交或未知提交状态。
- `submission_summary.json`、每任务 `scheduler_after_submission.json` 保留原始bjobs输出及哈希。
- 已完成数据库追加批次：6 calculations、6 jobs、6 job_status_history、78 files，共96行。
  **这些是作业/输入来源记录，不是96个吸附结果**；没有results、科学接受review或吸附能写入。
  保存的plan经检查只含上述四表的96个INSERT、零UPDATE，随后按本次提交授权审核并应用。

注册plan SHA：`ae66073e8b7b50c54d685a37968ecd4d51443d89178fcb04519664bdcf602c64`。
回执：`submission_registry_receipt.json`，inserted=96，updated=0，already_applied=false。

## 状态记录器修正与测试

首次读取调度状态时，原有TS活动学习schema未列出已由执行器支持的普通
`adsorption_relaxation` stage，因此拒绝记录；**提交本身已成功**。
只补入该stage并增加PEND/RUN只读查询回归，不把吸附任务伪称为TS force label，
没有重投六个作业、改变命令权限或改动VASP输入。修正后六份状态证据全部成功保存。

- Python语法与定向Ruff通过。
- 提交适配器/规范执行器测试：28通过。
- schema、状态证据、执行后端、主动学习和提交相关回归：122通过，零失败/跳过。
- 六个SUBMIT_VASP门、远端输入核验、成功回执与数据库事务均已实际执行核验。

## 未验证与后续

尚未验证电子收敛、离子收敛、最终盆地、耗时或加速收益。
保留06_C位点差异/暂态C–O伸长以及09_C改善不明确的警告。
只有两臂到达相容且相同的经审核稳定态后，才比较离子步、SCF总工作量、
VASP耗时、CPU核时与GPU/共享训练成本；旧131/101/114步不充当本次精确配对对照。
后续检查以当前六作业为准，不自动重投、改参数、换起点、训练或晋级模型。
