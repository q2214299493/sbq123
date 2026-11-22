# Stage B.2.3.1 验收

通用网络现在可以映射到已有原生执行证据覆盖的 CATKINAS 双库存闭合模型。已验证范围内的重命名、不同材料和位点类别由项目提供。新入口逐步报告能识别的方程，并检查这些方程能否组成同一套经验证的分子、库存和空位连接关系。[能力矩阵](capabilities.md) · [字段映射与调用示例](mapping.md)

## Ni/Cu 兼容性

从已审核网络和参数集重新生成四步模型，原生输入 SHA-256 为 `b793e6f37f2262e4a006f912d18950c17581ccc014aa9779008741a4e31890f8`，与历史输入逐字节相等。两份独立 MAT 均重放至各自已封存的 B.1 V2 输出。H#1 和 H#2 的分子身份、所在库存及各自贡献得以保留。按每一参考位点对计，400 K、1.6 bar 下已有的周转为 81.5127701616477 events/s，HNO 净生成量为 163.0255403232954 molecules/s。这些数值属于原合成模型。[输入、条件、旧输出与各自哈希](validation.json)

## 阻断与独立研究进度

氧化物 acid-A 与 oxygen-B 上的单个 CO₂、多库存界面产物和第三相产物保留其通用反应定义。详细报告定位到物种、反应或库存，并另列动力学或可逆性信息缺口。历史 Fe(110) 两个网络版本的 MKM 均为 blocked；与现有参数集匹配的版本也缺确认的电荷、位点及兼容自由能和速率。原始网络和历史记录可继续用于证据接收或其他合格分析。[逐样例审查结果](validation.json)

已有数据集级原生语法检查、单点入口与执行门均保留；多库存/跨相单点增加整网拓扑检查。映射、输入回读和归档重放均在本地离线完成。本轮没有发起新的原生或 DFT 计算，没有生产 SQLite 写入和新的科学资格决定。

## 测试与状态

开发树和独立发布树各有 896 项专项通过、9 项原生运行测试排除，两树的 32 个历史文件逐字节匹配正式基线。完整实验核对及命令见[回归报告](regression.md)。待审事件和两树各自的实际同步结果见[状态交接](handoff.md)。

## 本次发布文件

- `modules/baseline_mkm/README.md`
- `modules/state_handoff/events/history-stage-b2-3-1-catkinas-network-mapping-20261122.json`
- `reports/multiphase/stage_b2_3_1/capabilities.md`
- `reports/multiphase/stage_b2_3_1/completion.md`
- `reports/multiphase/stage_b2_3_1/handoff.md`
- `reports/multiphase/stage_b2_3_1/mapping.md`
- `reports/multiphase/stage_b2_3_1/regression.md`
- `reports/multiphase/stage_b2_3_1/validation.json`
- `scripts/baseline_mkm/mapping_scope.py`
- `scripts/baseline_mkm/native.py`
- `scripts/baseline_mkm/network_mapping.py`
- `scripts/baseline_mkm/single_point.py`
- `scripts/native_model.py`
- `scripts/native_validation.py`
- `tests/test_catkinas_network_mapping.py`

下一步是针对一个具体的新拓扑审阅原生语法、独立的守恒预期和验证预算，再决定是否批准单独原生验证。
