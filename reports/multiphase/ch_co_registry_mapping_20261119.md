# Fe(110) 上 CH* + CO* → CHCO* 的 Phase 1 字段映射

2026-11-19 从开发工作区的 `data/project_registry.sqlite3` 以 SQLite `mode=ro`、`query_only=ON` 读取 schema 9。主记录为 `ts_barriers.barrier_set_id = fe110_ch_co_sigma0p20_review_20261118`。电子能差可追溯，动力学交付状态为 `blocked`。[机器可读字段映射](ch_co_registry_mapping_20261119.json)

| Phase 1 字段 | 本次可映射的值及证据范围 |
|---|---|
| 物种、组成与反应 | 端点契约记录 CH* + CO* → CHCO*，形成零基编号 C45–C46 键。IS 中 CH* 对应 C45/H48，CO* 对应 C46/O47，两者共用同一个共吸附 CONTCAR。FS 为一个 C₂HO 片段。三个 species_id 是本映射的局部标识。反应的通用类别为 association，源契约的反应族为 co_insertion。 |
| 表面和位点 | 兼容性记录为五层 Fe45、3×3 Fe(110)。IS 两个 C 的最近投影均为 long_bridge。FS 两个 C 投影为 hollow，O 投影接近 top 且偏离高对称位，审查记录的 Fe–O 距离为 2.039 Å。接触与最近投影可记入几何描述。具体位点 ID、占用数、空位消耗/释放及各片段电荷尚无经审查的映射，均保留 null。 |
| IS、TS、FS 结构与能量来源 | JSON 的 source_states 逐态给出 calculation_id、result_id、OUTCAR 和 CONTCAR 的 file_id、工作区相对路径与 SHA-256。IS/FS 结构取端点契约，TS 取注册表的 ts_structure。IS 使用对实际 CH* + CO* 终态的复核，保留原完整分子目标被拒绝的历史。 |
| 能量单位与参考 | 三态均为 eV，采用 `fe110_converged_toten_sigma0p20_v1` 的最终 TOTEN。三条 calculation_compatibility 具有同一指纹，作为本映射的 energy_reference_id。JSON 把派生量绑定到能垒登记回执，并保留三个原始能量来源。 |
| 审查与资格 | 注册表接受了三项 final_toten 和电子能垒组。TS 的 Dimer 振动审查为 Grade A，具有 318.644011 cm⁻¹ 虚频，模态对应 C–C 开合。保留源 ts_validations.kinetic_eligible=1 的 TS 记录含义。新物种和反应的 Phase 1 审查仍为 unreviewed；整套动力学输入缺少自由能和速率参数。 |

| 量 | IS | TS | FS |
|---|---:|---:|---:|
| 原作业 | 9839757 | 9998592 | 9842136 |
| 最终 TOTEN / eV | −385.14767079 | −384.17406905 | −384.48836276 |

按 TS−IS、TS−FS、FS−IS 重算，得到正向电子能垒 **0.97360174 eV**、逆向电子能垒 **0.31429371 eV**、电子反应能 **+0.65930803 eV**。三值与生产记录及登记回执一致。逐项复核了三个 OUTCAR 的最终 TOTEN，以及 OUTCAR、结构、端点审查和 TS 频率文件的源哈希。

**缺项与后续用途。** 作业 2260 的 TS 局部 Hessian 覆盖 C45/C46/O47/H48。该案例未绑定采用一致活动原子的 IS/FS 频率、成套 IS/TS/FS 热校正、标准态或速率律。温度、压力、自由能、正逆速率参数均为 null。字段映射保留这些空值供后续补证；带强制字段空值的记录不能作为完整可运行 bundle 导入。电子能、结构复核和缺项追踪可以独立使用。

**进入 Phase 2 的第一步**是按这两个端点的结构哈希及零基原子编号 45–48，核对已有 IS/FS 频率证据的活动集与 TS 作业 2260 是否一致，并记录每个端点的匹配结论。

## 只读复核入口

在本地库执行下列查询可重建三态来源链，再按返回的源文件及 JSON 中的 SHA-256 复核原始输出。TS 审查通过同一条 ts_barriers 记录的 ts_validation_id 关联。

```sql
WITH states AS (
    SELECT initial_result_id AS is_id, ts_result_id AS ts_id, final_result_id AS fs_id
    FROM ts_barriers WHERE barrier_set_id = 'fe110_ch_co_sigma0p20_review_20261118'
), ids AS (
    SELECT 'IS' AS state, is_id AS result_id FROM states
    UNION ALL SELECT 'TS', ts_id FROM states
    UNION ALL SELECT 'FS', fs_id FROM states
)
SELECT ids.state, r.result_id, r.calculation_id, r.numeric_value, r.unit,
       r.reference_convention, r.validation_status, cc.compatibility_fingerprint,
       f.file_id, f.local_path, f.sha256
FROM ids JOIN results AS r USING (result_id)
JOIN files AS f ON f.file_id = r.source_file_id
JOIN calculation_compatibility AS cc ON cc.calculation_id = r.calculation_id;
```
