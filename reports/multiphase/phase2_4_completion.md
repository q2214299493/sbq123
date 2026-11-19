# Phase 2.4 多相动力学参数引擎

基线为独立发布分支上的 `249d92dc08bd43df500a6184bbc595ec50e01328`。新增入口 `python -m scripts.kinetic_parameters` 读取不可变网络版本，可输出内部参数集、缺项报告、CATKINAS 参数表和 Zacros 事件系数表。参数生成与引擎运行授权分开记录。

## 实现范围

| 文件 | 作用 |
|---|---|
| `scripts/kinetic_parameters/__init__.py`、`__main__.py` | 包、CLI、证据文件校验和防覆盖输出。 |
| `scripts/kinetic_parameters/laws.py` | TST、气体碰撞、给定前因子、参考压力换算、覆盖度修正、对数速率不确定度和单步质量作用速率求值。 |
| `scripts/kinetic_parameters/engine.py` | 复用 Phase 1 参数 Schema、网络评审、位点计量、热化学 Gibbs 值和来源；检查适用范围、证据绑定及详细平衡。 |
| `scripts/kinetic_parameters/export.py` | CATKINAS 的逐参考位点系数和定温表观 Ea/G0；Zacros 的逐匹配事件系数及初末态、邻接关系、气体分压幂。 |
| `tests/test_kinetic_parameters.py`、`tests/fixtures/multiphase/kinetic_*.json` | 35 项新用例和三份可复用合成资料（十进制参考值、双位点界面网络、已绑定的速率模型）。 |
| `modules/kinetic_data/README.md`、`modules/kinetic_data/kinetic_parameters.md` | 模块入口、模型字段、物理假设、审核规则和复现命令。 |
| `reports/multiphase/phase2_4/*.json` | 五份机器产物。真实 Fe 案例两份、完整合成界面案例三份。 |

## 条件与基准

表面质量作用采用分数活度，理想气体采用各组分分压除以其标准压力。TST 使用指定温度、共同标准态下的活化自由能。路径简并度和透射系数单独应用。碰撞吸附须提供气体质量、面积、粘附依据和活化约定。正逆独立系数在无量纲活度下核对详细平衡。已知可逆时也可显式选择从正向系数与平衡常数推导逆向系数。

独立的 42 位十进制参考计算，在 400 K、0.4 eV、简并度及透射系数均为 1 时给出 **76,051,723.2663 s⁻¹**。在该温度下，标准反应自由能 −0.1 eV 对应 **K° = 18.19468522**。另一温度使用该温度自己的活化自由能。覆盖度测试分别检查共享过渡态的线性位移、适用区间和避免重复修正。不确定度测试检查给定能垒标准差传播到 ln k。

合成解离吸附案例横跨两种表面位点，每个参考位点有两个匹配事件。在 400 K、标准压力 1 bar 时，CATKINAS 正向系数为 **1062.50433 bar⁻¹ s⁻¹**，Zacros 每个匹配事件为 **531.25217 bar⁻¹ s⁻¹**。测试还覆盖合成 Fe(110) 与非 Fe 氧化物，催化剂标识及位点类型均来自输入。合成参数标有 `synthetic_benchmark` 用途。[参数集](phase2_4/synthetic_interface_dataset.json) · [CATKINAS 表](phase2_4/synthetic_interface_catkinas.json) · [Zacros 表](phase2_4/synthetic_interface_zacros.json)

## 真实 Fe(110)

CH* + CO* → CHCO* 保留正、逆电子能垒 **0.97360174、0.31429371 eV**，电子反应能 **+0.65930803 eV** 和 TS 局部 ZPE **0.51405165 eV**。IS、FS 热校正、目标温度与标准态、已确认占位和空位、正式催化相及电荷记录、动力学可逆性、速率模型及参数评审仍有缺项。正逆活化自由能、反应 Gibbs 自由能和两个方向的速率均为 null。网络为 DRAFT，两种引擎导出均被阻止。[真实参数集](phase2_4/fe110_parameters.json) · [缺项报告](phase2_4/fe110_missing.json)

## 验证与下一步

开发目录及独立发布工作树各通过 **400 项相关测试，0 项失败**，其中 365 项为原有回归。两处均通过编译、导入和定向 Ruff。隔离安装的 wheel 分别重放真实和合成案例，与五份归档 JSON 逐份一致。原 VASP、NEB、DIMER 入口、生产数据库和执行门均未修改。本轮没有启动 CATKINAS、Zacros 或新计算。

下阶段建议用已发布的合成双位点模型，把参数表装配到两种引擎各自的原生模型输入，并逐字段核对物种顺序、位点编号、分压和匹配重数。当前验证覆盖参数表、公式和转换；原生求解器读取与数值运行仍待单独验证。
