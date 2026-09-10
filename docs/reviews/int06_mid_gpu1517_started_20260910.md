# INT06→MID GPU1517 已启动（2026-09-10）

用户指令“提交gpu0”。作业 1517 于北京时间 16:29:07 提交。

- 2026-09-10T08:29:16.018654+00:00：Slurm RUNNING；GPU0 UUID=GPU-483c224e-cc19-13e2-24ad-c83efd14fa75，调度分配与实际 CUDA 卡一致。
- scontrol listpids 和 nvidia-smi 的 PID 交集 ['2591707'] 证明本作业模型进程在 GPU0，非仅队列接收。
- ordinary_ml_neb.log 已有 FIRE 第 0、1 步；fmax 从 0.361267 到 0.296261 eV/A。尚未证明达到请求中的 0.1 eV/A 收敛条件；这些都是 ML 预测，不是 VASP 势垒或 TS 验证。
- 启动时 GPU0 空闲 12169 MiB，通过 12000 MiB 门槛。1 GPU、4 CPU、40 GB、6 小时、400 步上限不变。
- 请求 SHA256 ff5e8516df91b2b4a977c06a4f8a49d3ce17664ec49f857f39e6bebfb6ed754c；复用修正后的解释器符号链接处理和任务内 TMPDIR。此次没有运行时错误、重提、GPU 分配覆盖或 VASP 提交。
- 本地 Python/Ruff/shell 语法与 GPU0 正常、错误分配、低显存三项保护检查通过；远端环境检查与 23 文件输入、模型文件、几何预检通过。未重复运行已经通过且未变化的模型测试。

下一步：检查该作业输出，完成后将完整预测路径带回 work 进行路径、几何和后续 VASP 路线审查。此文是上述时刻的启动快照。
