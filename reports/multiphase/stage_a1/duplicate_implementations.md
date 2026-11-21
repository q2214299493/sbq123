# 重复实现与相似职责

| 核查对象 | 观察 | 判断及处理 |
|---|---|---|
| OUTCAR 解析入口 | tests/test_code_structure.py 的单一所有者检查命中 scripts/thermochemistry/frequencies.py 的 parse_outcar。热化学从频率行构建带符号频率和身份记录，已调用 scripts/ts_validation/analyze_vfa.py 的 frequency_header。scripts/neb_agent/utils_vasp.py 的同名入口用于 NEB 电子/力信息。旧吸附入口另有历史例外。 | 接口名称和职责边界存在冲突。整文件共用同一宽解析器会增加回归面。P5 |
| Registry 校验 | scripts/baseline_mkm/analysis.py 和 registration.py 从 CLI 引用批校验。校验实现已在 scripts/registry_mutations.py。 | 引用路径重复，无需复制实现或新建服务。P1 |
| SHA-256 字符串验证 | 逐个比较两树维护范围内顶层函数体 AST，仅统计整函数至少 45 个 AST 节点；发现一对完全相同体，分别为 scripts/ts_strategy_engine/dimer_gate_common.py 和 ml_neb_path.py 的 _sha256。 | 两者均检查输入类型、64 位长度和十六进制字符。scripts/artifact_io.py 的 sha256_file 则读取文件内容。保持语义区别，P12 可选。扫描不覆盖短函数、方法和语义等价实现。 |
| 校验层 | Schema 校验类型，领域层校验能量和守恒，适配器再校验原生表达能力，执行门复核审批与哈希。 | 各层有不同失败条件。保持分层校验，只抽取有相同输入和错误语义的原语。P2、P6 |
| Registry、状态投影、工单 | 登记科学记录、派生当前进度、协调外部问题分别由 Registry、State Handoff 和 H7/SPC 承担。准备度 JSON/Markdown 与当前权威状态有漂移。 | 三者不合库。投影只读生成，工单回传引用不可变证据。P4、P10 |
| 入口和包装层 | 模块 README 与轻量 CLI 保留稳定入口；native_model 从参数 CLI 读取工具，另有领域代码引用私有解析帮助函数。 | 仅在有实际逆向依赖或不稳定接口时调整；保留现有调用者。P1、P2 |

这些结果是有边界的扫描和人工复核。不能据此宣称全库仅有一处重复。
