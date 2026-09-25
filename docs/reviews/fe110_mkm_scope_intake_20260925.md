# Fe(110) 微观动力学第一步：范围与 CATKINAS 输入盘点

状态：`DRAFT_FOR_USER_SELECTION`。本文件不是已批准的反应网络、自由能表或可执行的 Fe(110) CATKINAS 输入。

## 已确认的本地条件

- 项目指定 CATKINAS 为基线平均场 MKM 工具，配置见 `configs/postprocessing_software.yaml`；`modules/baseline_mkm/README.md` 要求先有守恒的网络、自由能及工况。
- 本机存在 `D:/BaiduNetdiskDownload/bin/matlab.exe`、`C:/Users/86177/Desktop/app/CATKINAS/CATKINAS.p`、`ReadMe.m` 和 `quickstart/INPUT_single.m`。历史 `quickstart/result_single` 有 2026-06-26 的输出；本轮未重新运行，也未验证 Fe(110) 输入。
- 官方示例的运行形式是在 MATLAB 中将 CATKINAS 目录加入路径，再调用 `CATKINAS('INPUT_single')`；项目专用输入应放入独立目录并由受审数据生成，不修改官方 quickstart。
- 截至本次只读查询，`data/project_registry.sqlite3` 有 4 组 `accepted` TS 电子能垒：Fe(110) CO 解离、C*+H*→CH*、CH*+H*→CH₂*、C₂HO*+H*→C₂H₂O*。它们不是完整闭合机理，也不是同一温度下的自由能垒。INT06→MID 的局部频率仍在计算/验证链中，不列为已接受动力学步骤。

## 待用户确定的模型边界

| 选择 | 需要明确的内容 | 当前状态 |
|---|---|---|
| 目标 | 只研究 C₂H₂O 路线、C₁ 氢化，或更完整的 Fe(110) 产物网络；目标输出是 TOF、选择性还是路径贡献 | 未确定；C₂H₂O 仅作待审候选 |
| 工况 | 温度或范围；CO、H₂及主要产物分压；固定分压还是进料/流动模型 | 未提供，不填示例数值 |
| 表面位点 | 单类 Fe 位点是否足够；桥位、长桥位及多位占据物种如何计数；位点密度的定义 | 待逐个吸附结构核对 |
| 模型边界 | 哪些气相吸附/脱附、H 供给、O 清除、C–C 形成与表面迁移步骤进入首版 | 待反应网络缺口审核 |
| 能量与速率 | 统一温度/标准态的 ΔG、ΔG‡、吸附动力学约定；是否由输入自由能直接给 CATKINAS，避免重复校正 | 尚未具备正式输入 |

## CATKINAS 最小用法与输入要求

1. 在 MATLAB 中切换到独立工作目录，并加入 CATKINAS 程序目录：`addpath('C:/Users/86177/Desktop/app/CATKINAS')`。
2. 如需运行官方测试，应先把 `quickstart` 复制到独立测试目录，再在副本中运行 `run_single`；它调用 `CATKINAS('INPUT_single')`。这只验证软件，不验证 Fe(110) 科学模型，也不会覆盖原目录的历史示例结果。
3. 项目输入需要：基元反应与 `#`/`#1` 等位点记号、每步正向自由能垒与反应自由能、温度、气相分压/流动边界、初始覆盖度、热力学校正和吸附处理模式。CATKINAS 的 `INPUT` 使用 MATLAB 风格赋值及 `<->` 反应行。
4. 项目已自行计算并输入自由能时，不得同时启用会重复加上 ZPE/熵的 CATKINAS 校正模式。官方示例的数值、`ThermoMode`、`BarrierMode` 和位点约定都不能直接复用；尤其本地 quickstart 对 `BarrierMode=1` 的注释与本地 `ReadMe.m` 的模式说明不一致，项目输入必须单独审核该设置。
5. 正式运行前应检查元素守恒、位点守恒、每步 ΔG‡(正)−ΔG‡(逆)=ΔG(反应)、单位/标准态、输入来源和缺失步骤；运行后检查稳态残差、覆盖度范围、TOF 定义及结果对工况的敏感性。

## 本阶段输出与边界

本阶段的交付是以上范围草案、软件入口核对及缺失输入清单。未建立项目 `INPUT`，未运行 Fe(110) CATKINAS，也未产生 TOF/选择性。下一步需用户选定目标路线和工况，随后从登记数据生成原子/位点守恒的网络缺口表。
