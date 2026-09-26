# INT06 → MID：CI-NEB 局部 TS Grade A（2026-09-26）

- 正式登记：`fe110_int06_mid_ci9796856_vfa9798421_grade_a`，数据库 `data/project_registry.sqlite3`，读回确认为 Grade A、source_method=`ci_neb`。
- 来源：CI-NEB `9796856`，连续且收敛的 00–06 路径，唯一峰 image04；LSF DONE 已补齐历史证据。
- 局部 Hessian：`9798421`，Fe37–40/H49（零基索引），15 个模式，唯一虚频 mode15 `386.611701 cm^-1`；目标 H49 迁移模式已审核。
- 用户取消 CI-NEB 下坡连通性强制要求；本案**未做**该测试，数据库 `connects_to_is`/`connects_to_fs` 均为 NULL，不伪造 PASS。普通 NEB 规则不变。
- 实际 CI 收敛、路径/端点/晶胞/固定层/几何绑定仍被当前解析器与执行门核查；默认数值虚频分类阈值未设，采用明确的单一目标模式审核，而不是补造阈值。
- 接受门 state SHA256：`e23163f86264dfee2421861dd7e6702e425d35a39b1277fcba91149e9e0de437`，允许 `APPROVE_TS_CANDIDATE`，没有提交新计算。
- 登记回执 SHA256：`754d2ddc0eb5b0df2d8aed365f29f71c95ef61af09ec2784930ad129612690da`；VFA 分析 SHA256：`68497e7eba59e5af01959fdfef64366a7d39d440fae7420a9b59ccbc92c6e9f4`。
- CI 与 VFA calculation workflow 均从旧状态投影为 `accepted`；原诊断记录与 PEND 调度历史保留。
- 科学边界：仅 INT06→MID 表面 H 迁移段、局部 partial Hessian；不覆盖 MID→FS 的 O–H 成键段，不证明全局最低路径、不提供完整热力学校正。尚未完成本段正式兼容电子能垒登记。

GPU1788 的 VASP 路径种子测试：8 步 ordinary ML-NEB 收敛，fmax `0.096222 eV/Å`，最大活动原子偏移 `0.0452 Å`，最终峰仍为04。仅支持当前 checkpoint 在已知 VASP 路径邻域的局部稳定性，不证明 GPU 独立搜索鞍点的能力，未触发微调。

登记资料位于 `calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/vfa_ci9796856_image04_local_h_fe_20260925/` 的 `vfa_review.json`、`vfa_analysis.json`、`ts_acceptance_gate_decision_20260926.json`、`formal_ts_registration_receipt_20260926.json` 及相应 append-only registry 计划/批准/回执。
