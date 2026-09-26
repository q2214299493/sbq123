# IS-A → INT06：剩余 H 表面迁移路径（2026-09-26）

状态：候选路径已构造，待用户结构审核；未运行 GPU 模型、未提交 GPU/VASP 作业。不是 TS 或电子能垒。

## 范围与构造

- IS：已登记 VASP 吸附态 IS-A，9725473 最终 CONTCAR；FS：已接受中间态 INT06，9748648 最终 CONTCAR。原文件字节副本与登记哈希一致。
- 本段不包含已接受的 INT06→MID，也不包含 MID→FS 的 O–H 成键。
- 50 原子 Fe45 C2 O H2，原子映射恒等；H50（一基；零基49）迁移，底 Fe0–17 固定；保持现有五层 Fe(110)、SIGMA=0.20 eV 兼容分支。
- 旧 GPU1357 的九张结构哈希全部核对，仅提取02/03/04中 H50 的表面走廊位置作三个候选 waypoint。其余原子根据当前精确 IS/FS 平滑插值，再由 canonical planner 分段 IDPP 构造。
- 总计11张结构：00和10为端点、01–09为九张内部图像。H 大致从 Fe44/37/43 邻域，经 Fe43/Fe41 之间，到 Fe41/40/38 邻域；这里的 Fe 标签均为一基，邻域描述不代替位点对称性/势能面判定。
- 无额外 H、O–H、C–C restraint；waypoint仅用于初始化，不是后续 GPU/VASP 优化中的固定约束。

## 已验证

- 端点登记证据 PASS；端点几何无错误，仅 H50 总位移3.277097 Å 触发 REVIEW 提醒，保留该提醒，不伪造 PASS。
- 全路径 canonical geometry PASS，无错误；相邻最大单原子跨步0.404713 Å，可动原子最大相邻 RMSD 0.071756 Å。
- ASE 真正二维 MIC 独立核查：raw位移与MIC差异最大1.42×10^-15 Å，无隐藏周期跳转；底层相对原始精度的最大差1.11×10^-11 Å，仅序列化舍入。
- C–C 1.410850–1.416146 Å；C–O 1.288203–1.291424 Å；原 C–H 1.099076–1.099861 Å；O–H保持3.079728–4.062300 Å，不是O加氢路径。
- 十段 dist.pl、nebmovie.pl 0 均退出0；输出movie的11帧与11张POSCAR元素顺序一致，坐标最大序列化误差4.63×10^-14 Å。
- 已检查H走廊顶视/高度图；没有跳跃、穿层或脱附。程序检查与视觉审核支持候选初始化，不证明最低路径。
- 初次本地VTST运行因Windows模块路径/CRLF工具调用失败，记录保留；使用后端原始LF工具与明确Git工具PATH恢复检查，未重建或覆盖图像。
- 准备脚本通过语法与Ruff检查；重复构造会拒绝已有目标目录。没有运行新模型或第一性原理计算。

## 文件与待定事项

包：`calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_is_a_int06_path_20260926/`。
结构：`plan/path_candidate/00–10/POSCAR`；表：`geometry_table.csv`；图：`path_review.png`；动画数据：`plan/path_candidate/neb_path.xyz`与VTST `movie`。
`plan/path_candidate/path_review.json`为哈希绑定的 **needs_review** 草稿，未填写用户批准。

旧1357 image02的预测低点仍未被VASP独立证明，因此本包定义的是一个待搜索的路径区间，不预先宣称单一基元步骤或唯一鞍点。若后续产生稳定中间态/多个峰，应据新证据分段。

下一步：用户确认迁移方向后，准备冻结 MatRIS epoch6 主模型的无额外约束 ordinary ML-NEB，并让 AQCat25 仅复核最终同构路径；完整结果返回work审核后，再准备VASP普通粗NEB。GPU图像数不自动照搬为VASP图像数。新提交仍需当前包的执行授权与门。

复现脚本：`archive/is_int06_path_20260926/prepare.py`；需要ASE/Matplotlib、Git Perl及归档的原始LF VTST工具。`--review-existing`只恢复已生成结构的检查/导出，不重新生成图像。
