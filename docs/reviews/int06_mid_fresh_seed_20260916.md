# INT06 → MID 独立端点初始路径（2026-09-16）

状态：本地结构与 GPU 请求草案已准备，待用户结构审核；未部署、未提交或运行模型。

## 用户决定及范围

用户要求放弃当前失败结构路径，重新构造用于 GPU 优化的路径；若本轮仍不行，转 VASP ordinary 粗 NEB。
停止继续围绕旧 GPU1517 峰值做 SCF 修补，不删除历史数据，不否定已接受的端点与 MID→FS O–H TS。
本次只处理当前 INT06→MID 的 H 表面迁移段；IS-A→INT06 仍另待处理。

## 新初始路径

- 起点 INT06：9748648 的登记最终 CONTCAR；终点 MID：9737143 的登记最终 CONTCAR。来源哈希和端点登记校验通过。
- 从两个端点独立进行全原子 IDPP；不使用旧 GPU1357 waypoint、GPU1517 内部图像、Dimer 中心或电子重启文件。
- 00–08 共 9 张图，7 个内部图像；50 原子顺序、晶胞与底部 18 Fe 固定掩码保持。
- H50 净位移 1.576991 Å，其他原子端点最大位移 0.189894 Å。
- 相邻最大原子位移 0.197171 Å；最短原子距离 1.099076 Å，属于分子内 C–H。
- H50 最近 Fe 距离最低 1.579591 Å；这是待 GPU 松弛的接触几何，不是已确认稳定构型。
- H50–Fe39 从 3.288013 到 1.821733 Å；H50–Fe40 从 1.784730 到 3.214591 Å。
- H50 高于顶层平均平面 0.9506–0.9637 Å，C₂HO 内部连接不变，未转为 O–H 成键。
- ASE 精确 xy MIC 验证无周期跳跃；固定层漂移为零。8 次 dist.pl 和 nebmovie.pl 0 返回 0，9 帧 XYZ 与原结构匹配。
- 顶视/侧视图已由 Codex 检查。用户审核状态仍为 needs_review，不冒充用户批准。

## 限制与下一步

这不是新机理或 MEP。新中间图 04 与旧失败中心的 H50 差约 0.113126 Å、可动原子 RMSD 0.066995 Å，仍处于同一迁移通道。
不能因重新生成或加密图像就保证消除旧 SCF 故障，GPU 也可能优化回相似几何。

请求草案：MatRIS 原冻结模型主优化、AQCat25 同构复核；普通 ML-NEB 上限 400 步、fmax 0.10 eV/Å；无临时键长约束、无 CI、无 Sella、无训练、无自动重试。
拟用 1 GPU、4 CPU、40 GB、6 小时上限。模型标识沿用已有迁移请求，远端哈希、运行器部署及当前环境仍须重新预检。

本轮 GPU 若仍不给出可用路径，转为准备几何合格的完整 INT06→MID VASP 粗 ordinary NEB，不再无限循环 GPU/旧峰值 SCF，不强制增加 pilot。
不得直接把碰撞/不连续的失败 GPU 图像交给 VASP；该分支仍保留电子收敛和实际输入审核。具体核数、图像数、输入哈希及提交授权在交接时绑定。

## 失败保留

9757725 在 2026-09-16 05:36:30 启动，05:38:33 EXIT。A 固定电荷阶段完成 2 次 DAV 记录，第 2 次约 -2.9512e13 eV，TOTEN 溢出；随后 EDDDAV/ZHEGV 失败。B/C 未启动，重启文件为空。
NCORE=8 与 NBANDS=320 未解决问题；这不是结构根因已经确诊。
初次本地规划使用通用 segmented_idpp 默认而没有 waypoint，生成器正常拒绝；拒绝记录保留在 plan/。随后明确选择允许的 endpoint-only IDPP，在独立 endpoint_idpp_plan/ 生成，没有修改通用门禁。

## 文件

计算包：calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_mid_fresh_seed_20260916/

- endpoint_idpp_plan/path_candidate/00–08/POSCAR
- endpoint_idpp_plan/path_candidate/exact_mic_geometry.json
- endpoint_idpp_plan/path_candidate/path_review.draft.json
- endpoint_idpp_plan/path_candidate/movie.xyz
- path_review.png
- gpu_request/request.draft.json（运行器和用户审核绑定尚未完成，不能直接执行）
- local_preflight.json

下一步：用户审核该新初始结构，再完成绑定及 MZ73 无模型预检，申请这个具体 GPU 包的提交。
