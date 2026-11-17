# 冻结536模型：614帧固定结构力预测

2026-11-17提交BUCT3的Slurm作业436，分区`compute`，节点
`ubuntu-R5350-G6`，单张RTX 4090。作业已返回原生`COMPLETED`，
预测进程退出0，生成614/614帧；进程耗时50.357秒。固定结构预测
不构成模型精度、DFT加速或科学准入验收。

- 输入：536训练帧＋78开发帧。53测试和16隔离帧不参与。
- 冻结checkpoint SHA256：`2aaed376a1d5ad66999710f7d252aff79c45569f2a6a95510d4bff9bbc70acc0`。
- 原生Fairchem定制接口和Film模块保持来源绑定；本任务将`extra/vendor`
  放在普通site-packages之前，不修改共享运行环境。
- 分配内检查GPU UUID、空闲显存、CUDA算子、模型CUDA参数和首帧，再逐帧预测。
  每帧保留坐标SHA、原子序和固定掩码，力为native patched_calc物理输出，
  不重复反归一化。没有优化、梯度更新、DFT提交或checkpoint晋升。
- 预测进程限500秒，外部watchdog520秒、强制退出余量10秒；Slurm限540秒，
  加退出余量及前次失败2秒的累计预算上界572秒，小于单卡600秒。

首次作业434因提交目录检查错误，在2秒后退出、预测0帧。失败输入、日志和
回执原样保留。校正包使用实际工作目录`PWD`检查，提交进程同时设置正确cwd；
另建v4目录并复用已上传输入，没有修改434或其冻结执行包。仅提交一次校正作业436。

执行目录：`/home/sbq/sbq/force_diagnosis536_gpu_20261117_v4/`。
结果位于`output/job_436/`，包括`predictions614.json`、逐帧文件、
`GPU_binding.json`、`first_frame_check.json`和`producer_exit.json`。
进程退出记录与Slurm终态证据分开保存。

本地证据目录：
`calculations/fe110_reico_pilot300_20261022/force_diagnosis536_gpu_20261117_v4/`。
输出已回收至其`returned/`；`return_verification.json`记录ID、同坐标SHA、
力数组有限性及冻结包完整性校验。本轮按用户要求结束于作业提交/输出回收，
未开展新的ML–DFT误差统计或DFT选点。

检查：Python语法、限定Ruff、3项范围守卫测试、真实614帧输入哈希校验、
远端`bash -n`、native环境导入和分配内CUDA检查。原512/536包和78/53/16分区保留。
此目录是该次已授权执行的源码记录，不授予自动重提、重训或使用其他分区的权限。
