# INT06 → MID：局部普通 NEB 输入审查（2026-09-10）

状态：本地准备完成；未提交 VASP。此前 INT06 结果及 MID→FS O–H TS 的用户批准不变。

## 输入与范围

- 起点：9748648 最终 CONTCAR（INT06）；终点：9737143 最终 CONTCAR（MID）。两个登记结构均以字节副本保留在新包 IS.vasp、FS.vasp。
- 原 GPU1357 image07 只提供几何参考点；3 个中间图像由分段 IDPP 初始化。登记查询未找到 GPU06/07/08 的完整同构 VASP 峰值三图像证据，不能直接用于 Dimer。
- 保留 50 原子顺序、H50 身份及底部 18 个 Fe 固定；独立检查使用 ASE 精确 MIC、仅 xy 周期边界。

## 已执行检查

- 端点、路径绑定、C₂HO 连通性、固定层、碰撞和周期连续性检查通过。
- 四次 dist.pl 和 nebmovie.pl 0 均 exit 0；生成的 5 帧 XYZ 与输入结构逐帧匹配；已查看 path_review.png 顶视图和侧视图。
- 相邻图像最大原子位移 0.465841、0.465841、0.330580、0.330580 Å；固定层漂移为 0。
- H50–Fe39 距离由 3.288013 单调降至 1.821733 Å，H50–Fe40 由 1.784730 单调增至 3.214591 Å；C₂HO 内部连通性保持。
- 仓库 VASP builder 生成输入；INCAR custodian：PASS，无错误或警告；submission preflight：PASS。
- 使用分析完成后的 geometry 文件刷新输入包绑定；canonical execution gate 自校验通过。

## 待批准计算

- 后端：sunboquan-codex；普通 NEB，3 个中间图像，96 核（每图像 32 核），NSW=300，LCLIMB=False。
- 锁定参数：PBE、ENCUT=400 eV、Gamma 5×5×1、SIGMA=0.20 eV、EDIFFG=-0.05 eV/Å、ISPIN=2、Fe MAGMOM=2.2、NPAR=4。
- 输入包：`calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_to_mid_path_20260910/plan/path_candidate`。
- bundle SHA256：`1e34b1df2a0b4ee304cc2d5040e4fed365e0ead2421e049bba873cb232631735`。
- 执行门：`READY_FOR_ORDINARY_NEB_SUBMISSION`；scientific_readiness 允许候选动作 SUBMIT_VASP，但 `ALLOWED_ACTIONS=[]`、`SUBMISSION_ALLOWED=false`，因为没有本包的提交授权。

## 未验证与下一步

本路径没有 VASP 能量或力剖面，不能报告迁移势垒或 TS；IS-A→INT06 及其 image02 分支仍未解决。POTCAR 目前仅有规格文件，正式提交前须核验后端势文件与完整输入包。

下一步：用户批准上述确切输入包后，在 sunboquan-codex 核验 POTCAR、绑定授权并重评执行门，通过后提交这一项普通 NEB。
