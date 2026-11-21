# 这十份归档可以比较什么

两份 CATKINAS 闭环彼此可以比较。它们共享参数版本、网络、条件、参考位点对和稳态观测定义，各自绑定不同 MAT。下表对照其中任一份与每个 Zacros 时间窗。分类以具体观测量为单位。

| 对照项 | 适用归档 | 分类 | 证据或仍缺的条件 |
| --- | --- | --- | --- |
| 合成催化剂身份 | 全部 | comparable | 项目 demo，FCC Ni(111) 与 Cu(111)，Ni-top、Cu-bridge 和两面间的 junction。身份一致仅限于此合成配置。 |
| 温度及单独的 H₂ 分压 | 全部 | comparable | 均为 400 K 和 1 bar H₂。 |
| 原生气压的不同单位 | 全部 | comparable_after_explicit_conversion | 1 bar = 100000 Pa。仅核对相同分量。 |
| 完整操作条件 | 全部 | not_comparable | CATKINAS 总压 1.6 bar，另有 NO 0.5 bar、HNO 0.1 bar。Zacros 归档为纯 H₂，总压 1 bar。 |
| 全反应网络 | 全部 | not_comparable | CATKINAS 为四步闭环。各 KMC 网络仅含吸附步骤，普通、双齿和显式单向模型分别绑定网络版本。 |
| 吸附分子和空位计量 | mono、full、interacting、continuous、split、resume | comparable | H₂ 消耗两类空位，各出现一个单齿表面片段，含逆向步骤。相同计量可以逐列对照。 |
| 双齿足迹 | dent | not_comparable | 同样消耗一个 Ni 空位和一个 Cu 空位，但产生一个跨两库存的分子。该产物与 CATKINAS 两个单齿片段的分子源项不同。 |
| 单向吸附 | attractive | comparable（正向计量） / not_comparable（逆向、完整净速率） | 正向产生两个片段。此归档排除了逆反应，CATKINAS 的逆向有实际通量。 |
| 晶格及初态 | 全部 | not_comparable | CATKINAS 使用平均场覆盖率，KMC 使用 9 Ni + 9 Cu 的周期邻接图和离散初态。full、interacting、attractive 有各自的原生占用或相互作用设定。 |
| 同一 KMC 窗口在自身晶格上的位点平均 | 全部 | comparable_after_explicit_conversion | 明确定义“全晶格 18 个物理位点的平均”才可将该窗口的整片晶格速率除以 18。18 个几何匹配和 9 份各含一个 Ni、一个 Cu 的库存单位代表不同计数。原生输出仍保存每完整晶格的观测。 |
| 物理面积、质量、体积或跨模型参照容量 | 全部 | insufficient_evidence | 尚缺项目对应的可用位点密度、质量或反应器体积，以及周期晶格到所选物理参照的映射。两个模型的位点名称相同不能提供该换算。 |
| 采样时长和稳态资格 | 全部 | insufficient_evidence | KMC 给出了有限窗口事件数和物理秒数。短轨迹没有平稳性或独立重复证据，终止标记不能提供误差区间。split 和 resume 属于同一条轨迹。 |
| 整体周转、HNO 分子源项 | 全部 | not_comparable | CATKINAS 定义了稳态整体周转和 HNO 生产。KMC 网络没有 HNO，也没有对应的循环。HNO 观测在这些 KMC 模型中不可用。 |
| 实际吸附净进度的数值对照 | 全部 | not_comparable | 即使某步计量相同，仍缺共同反应环境、可对照的时间及空间取样和同一定义的分母。符号与大小差异本身不能诊断实现错误。 |

KMC 连续轨迹与分段重启的过程表、物种表可作逐字节复现对照。它们没有提供第二个独立随机样本。若未来研究目标需要比较平均场与空间效应，需先声明共同反应、气相边界、位点足迹、观测窗和分母映射，并分别说明每个引擎的适用范围。[精确的网络版本、原生输入与输出绑定](independent_replay.json)
