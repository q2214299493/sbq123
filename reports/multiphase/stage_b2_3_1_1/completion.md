# B.2.3.1.1 交付状态：离线审查完成，原生验收待证据

厂商手册 §4.3 明确支持多位点物种和覆盖度的命名。候选反应 `CO2 + #1 + #2 <-> CO2#1#2` 在产物侧只有一个分子。对应分子变量为 `Q1x2_CO2`。本机样例以及两份已验收的 Ni/Cu 原生输出未覆盖此种分子。[厂商手册](https://www.catkinas.com/category/manual/) · [原生能力审查](capability_assessment.md)

**检查点验收仍未达到。** 现有适配器会拒绝跨库存的桥式分子；公开说明没有确定该构建中桥式变量在不等容量库存间的归一化。氧化物 fixture 也缺两侧速率系数或等效能量、可用工况及独立平衡常数。本轮将可追溯的计量式和变量名写成了非可执行样稿。样稿 SHA-256 为 `e9cdbfc608fc674d2f8cc2473fd7514fd8a8c33cfa5a5cdaecbb018fb421942b`。完整原生输入、执行计划及其哈希和批准均为空。[原生方程样稿](oxide_CO2.m.in) · [执行准备与验收标准](execution_review.md)

| 本例阶段 | 实际结果 |
| --- | --- |
| 通用计量与候选语法静态核对 | 一个气相分子变成一个桥式分子，每侧库存各消耗一个空位；反向各释放一个 |
| 完整原生输入生成 | 阻断，样稿有五处显式待填参数 |
| 原生解析接受 / 数值收敛 | 均未运行 |
| 独立数值一致性 | 库存计数、计量残差已核对；速率、数值详细平衡和 MAT 对照待数据 |
| 真实催化机理接受 | 未评估 |

有限样例中的 2 个桥式分子占 2/4 酸位与 2/3 氧位；每库“占用加空位”残差为零。气相、吸附态及空位的源项系数可独立导出。初态净速率未知，平衡时的零净通量是未来的对照目标。将 1/2 和 2/3 中任意一个数直接当作两库共用的分子覆盖度都会在另一库存产生计数错误。[数值参考及符号速率式](numerical_reference.md) · [机器可读数据](independent_reference.json)

本次只增加审查资料和回归测试，并在 MKM 模块文档登记厂商语法证据。执行入口、原有科学资格、生产 SQLite 和历史原始数据都保留。后续首先需要该构建的多位点分母说明或可重放示例；补齐合成参数后，才能计算数值参考并申请唯一一次哈希绑定的原生运行。[回归报告](regression.md) · [待审 State Handoff](handoff.md)

## 本次文件

- `modules/baseline_mkm/README.md`
- `modules/state_handoff/events/history-stage-b2-3-1-1-catkinas-multidentate-audit-20261122.json`
- `reports/multiphase/stage_b2_3_1_1/capability_assessment.md`
- `reports/multiphase/stage_b2_3_1_1/completion.md`
- `reports/multiphase/stage_b2_3_1_1/evidence.json`
- `reports/multiphase/stage_b2_3_1_1/execution_readiness.json`
- `reports/multiphase/stage_b2_3_1_1/execution_review.md`
- `reports/multiphase/stage_b2_3_1_1/handoff.md`
- `reports/multiphase/stage_b2_3_1_1/independent_reference.json`
- `reports/multiphase/stage_b2_3_1_1/numerical_reference.md`
- `reports/multiphase/stage_b2_3_1_1/oxide_CO2.m.in`
- `reports/multiphase/stage_b2_3_1_1/regression.md`
- `tests/test_catkinas_oxide_multidentate_audit.py`
