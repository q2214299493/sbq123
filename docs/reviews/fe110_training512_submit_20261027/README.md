# 512帧试训：已授权、已部署，GPU资源阻止启动 — 2026-10-27

**1994个文件已部署到MZ73，原生CPU/CLI/checkpoint/命名空间预检通过；GPU1未通过启动资源检查，训练尚未启动。没有训练PID或调度器作业号。用户授权已生效，无需重复确认同一预算。**

|阶段|实际结果|
|---|---|
|用户确认|“提交／再来／提交”，解释为同一份试训，不创建多份作业|
|输入绑定|原512帧训练请求不变；新增一次性直接执行授权|
|部署|新目录独占创建，1994文件上传成功；原生逐项哈希核对通过|
|服务器预检|659标签源、590训练/开发数据库行、原生CLI、包内trainer、基底架构和哈希通过|
|GPU启动检查|未通过：`insufficient free GPU memory; no model started`|
|实际训练|没有创建启动标记、生产者输出或训练PID；CUDA未初始化|

训练请求SHA：`fbc1fb2d7b8753e5429db2253559cff5a68669a0f620eebe515f01ad6c1c84e7`。

本次直接执行请求SHA：`6167f4f87a1383f492fcd22f9bd0f133d6b7c46938f4644c6b02e4b69bb3bfca`。

远端根：`/home/sbq/sbq/fe110_force_training512_20261027_v1`；run ID：`direct-fe110-force512-20261027-v1`。这是有边界的直接生产者执行，不伪造LSF/Slurm作业号。

## 授权范围与不变量

原始AQCat25基底、512train/78development/53reserved，2epoch、batch1、lr1e-5、seed42，最多1024训练迭代，GPU1单卡最多30分钟、4CPU、32GiB。实际更新次数与训练迭代分开核对；失败或超时不自动重试。用户没有授权停止已有计算、变更GPU、后续DFT优化、保留集推理或模型推广。完整人类授权见`user_authorization.md`。

原数据、分区、磁性等级及manifest SHA `ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee`未变。开发集仍独占模型选择，53保留帧含46个历史评估帧的事实保留。没有新模型准确度或加速结果。

根`configs/execution_backends.yaml`仅新增`fe110_force_training512_20261027`例外，精确绑定一臂、请求哈希、设备和预算，其余已存在设置经独立差异核对保持一致。原准备收据引用的配置路径哈希随这次已授权变更变化：已在变更前验证原收据并保存配置原字节快照，以新提交绑定衔接；没有改写旧收据或科学标签。

## 资源阻塞

GPU1 UUID为`GPU-450609b3-d1fd-ac33-d03a-79891be402da`。提交前资源快照中可用显存19,656MiB，另有PID102031占用约4,404MiB；原生门禁要求至少20,000MiB空闲且没有该卡上的既有计算进程。部署后的精确请求检查仍返回显存不足。没有降低门槛、共享已有进程的设备或停止其他任务。

已调用原生`direct_training_arm preflight`完成只使用CPU的检查；这不代替GPU资源门禁。实际启动必须经现有`direct_force_training launch`再次检查GPU、唯一启动标记及已绑定的CPU预检回执。尚未调用launch或创建本地launch reservation。

没有创建等待后台、定时监控或自动启动服务。下一次可检查GPU1；满足条件后使用本次已有授权启动一次，保持相同请求及预算，无需重传或重复确认。

## 验证与证据

- 主工作区、发布副本各50项相关测试通过，覆盖历史双臂/新单臂范围、损失与采样、分区及重复绑定/重复上传保护；语法及限定Ruff通过。
- 原生服务器预检回执`PASS_NATIVE_PACKAGE_CPU`，原生CLI回执`PASS_NATIVE_CLI_NO_MODEL`，trainer来源为当前包的`control/runtime`，没有模型构建或CUDA初始化。
- 独立提交复核`AUTHORIZED_DEPLOYED_CPU_PASS_WAITING_GPU`：本地/远端请求、CPU预检和授权一致，原训练请求及manifest不变，上传数量1994，生产者为空、GPU检查失败。

本地证据：`calculations/fe110_reico_pilot300_20261022/training512_submit_20261027_v1/`，含原策略快照、变更前审核、授权绑定、上传/CPU预检回执、部署后状态及独立复核。部署包仍在`training512_20261027_v1/package/`。复用已完成阶段；不要重复运行bind/upload或绕过原生资源门禁。
