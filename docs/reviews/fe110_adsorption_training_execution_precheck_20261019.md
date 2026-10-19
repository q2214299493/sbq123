# 受限训练执行预检：尚未启动

用户已回复“运行”，已形成绑定两组原请求的独立授权记录，冻结训练包没有改动。
完成本地全部artifact哈希复核与MZ73只读预检；**没有上传实际数据或提交/启动GPU训练**。

## 2026-10-19 22:32 CST 实测

| 检查 | 结果 |
| --- | --- |
| SSH与主机 | 连接成功，MZ73 |
| 原始checkpoint | SHA256与审核包一致：`e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50` |
| slurmctld / slurmd | 均failed |
| sinfo | exit1，无法连接Slurm controller |
| squeue | 12秒超时，状态未知；不能据此断言没有任务 |
| GPU1 | RTX4090，24066MiB空闲、0%利用率；这是瞬时查询，不是资源预留 |
| 目标包目录 | 尚不存在，没有重复运行证据 |
| 目录边界 | `/home/sbq/sbq`实际解析到`/home/ubuntu/hdd/sbq/sbq`；冻结助手要求前者解析后仍等于自身，检查不兼容 |

当前wrapper明确要求真实SLURM_JOB_ID，不能伪造ID直接运行。即便控制器恢复，目录边界
检查仍需在新的执行包中正确支持已验证别名，并重新绑定修改后的运行时哈希。
这两个问题是执行环境/包装问题，不是训练数据、模型精度或科学参数错误。

## 授权与结果

- comparison哈希：`f5db5cb7b1e98d6153bba8bbc41a0d0697fd29c79162a4ef0298a91969660987`。
- 两组独立授权均绑定原请求；单GPU顺序、每组2轮/496步/30分钟、总60GPU分钟，
  不自动重试，不改默认模型或既有VASP任务。
- 新execute工具只提供本地授权记录和只读probe，没有提交、训练、重启服务或直跑分支。
- 首次读取中文授权遇到Windows默认GBK解码错误，发生在SSH前；修正为显式UTF-8后
  才进行了唯一一次远程probe。授权未重复写入，冻结训练包未修改。
- GPU完整前后向、AMP/优化器、开发集曲线、留出验证与实际加速均未执行。
- 新授权/只读预检工具通过编译、Ruff及相关回归：**143 passed，0 failed/error/skipped**。
  覆盖中文授权、篡改拒绝、禁止重复授权及无提交/服务变更的probe边界。

证据目录：`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_execution_20261019_v1/`，
包含`comparison_authorization.json`、两组`*_authorization.json`、`live_preflight.json`及receipt。

## 下一步需要选择

建议为本次两组**单独授权新的GPU1直跑执行包**：固定GPU UUID、复核即时资源，
正确处理目录别名，强制CUDA及GPU张量检查，顺序执行、进程组超时和独立退出记录；
数据、训练配置和总预算不变。必须重新绑定修改后的运行时并完成预检，不能原样重投。
另一选择是等待管理员恢复Slurm，再修复/审核目录边界运行包。
