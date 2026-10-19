# 本次明确执行授权与预检边界

用户在已提供两组设计、预算和完整请求哈希后回复：`运行`。

授权绑定：comparison `f5db5cb7b1e98d6153bba8bbc41a0d0697fd29c79162a4ef0298a91969660987`，
control `dbad960b964805277333d21bce0a1669e38085c9ab742f5ed53a88a9a5b2d026`，
treatment `8b740e698d2bac32bb9f918012372a1aaf4e410d9bfef61397bb55ce95ab69ca`。

允许审核包的部署/预检与顺序受限训练；各2轮/496步/30分钟、总60GPU分钟，
同时最多一张GPU。不授权新VASP、模型晋级、自动重试、服务重启、占用他人GPU或
借用此前其他任务的direct-execution例外。冻结请求本身未改，授权作为独立记录保存。

2026-10-19 22:32 CST 的只读预检确认：Slurm服务failed/controller不可连接；
冻结环境助手不接受当前 `/home/sbq/sbq` → `/home/ubuntu/hdd/sbq/sbq` 目录别名。
因此没有上传数据、调用sbatch或运行模型。下一步需要用户选择新的执行方案；
不能将本授权静默扩大成未调度直跑。
