# 本轮权限

用户请求：`备受限训练对照包供审核，再单独授权 GPU 执行。`

本轮仅准备本地对照包、代码与无模型检查。未授权 GPU 训练/推理、实际结构或标签
上传、VASP 提交、既有作业变更、模型晋级或科学结果登记。
MZ73 只读源检查与 RAM-only 命令行/registry 检查不加载模型 checkpoint，不写远程文件。

两组实际训练必须分别绑定审核过的 `training_request.json` SHA256，使用现有
`RUN_GPU_ADSORPTION_SMALL_FINETUNE` 显式授权检查；没有生成授权文件。
两组顺序运行、最多同时一张 GPU、总墙时上限 60 GPU 分钟是待审核预算，
不是本轮的执行授权。Slurm 不可用时不得挪用旧 direct-execution 例外。
