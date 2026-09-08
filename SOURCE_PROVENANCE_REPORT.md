# Source Provenance Report

## 审查口径

既有 E 类为 23 项。用户正文的分组清单有 22 项；本报告补回
`REFACTOR_CHANGESET.md` 已列出的 `AGENT_RULE_TS_ENDPOINT.md`。

共同证据：

- 23 项均为 `??`，`git log --all -- <path>` 均为 0 条提交；
- 23 项当前 SHA-256 均与 `UNTRACKED_FILE_INVENTORY.md` 冻结值一致；
- 因无 Git 历史，不能从仓库证明具体作者或创建命令；
- “创建目的”根据实现、正式调用方、文档、历史 artifact 和测试推定；
- 未以“没有 import”作为无用结论。

## 逐文件结论

| 文件 | Git | 归属 | 功能/创建目的 | 调用方与引用 | 测试 | 主要依赖 | 科学逻辑 | 副作用 | 重叠 | 缺失影响 | 建议动作 | 风险与证据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `AGENT_RULE_TS_ENDPOINT.md` | ?? | HUMAN_REVIEW | 定义 stable product 复用、独立 endpoint 和选择优先级 | `modules/transition_state_search/README.md` 明确称其为 rule authority | endpoint 测试间接实现这些规则 | 无代码依赖 | 是，治理规则 | 无 | 与 README/validator/generator 语义一致 | 运行代码不因文件缺失而 import 失败，但正式规则依据缺失 | 保留并由所有者确认正式文档地位 | 无 Git 历史；分类枚举没有 FORMAL_DOCUMENT |
| `configs/neb_path_quality_control_v2.yaml` | ?? | FORMAL_CONFIG | path-quality persistence、geometry、energy、CI readiness 阈值 | unified `cli.py`→`workflow.py`；standalone CLI；README；历史 `neb_path_quality.json` source binding | 5 个 evaluator 测试及 TS workflow 测试 | YAML consumer、default thresholds | 是 | 无 | 两个入口重复加载 | unified analyze 默认入口失败 | 纳入正式配置，锁定值 | 已有真实历史 artifact 绝对路径/hash 引用；改值会改变判定 |
| `configs/structure_purpose_routing.yaml` | ?? | FORMAL_CONFIG | structure purpose 开关与 endpoint validation threshold policy | manager 和 validator 默认读取 | 16 个 purpose/endpoint 测试 | `load_yaml` | 是 | 无 | 同一文件承载 routing 与 threshold 两个 section | endpoint manager/validator 默认实例失败 | 纳入正式配置；后续可审查拆分但本轮不改 | 仅由未跟踪正式候选使用，尚无 unified CLI caller |
| `configs/ts_connectivity_gate.yaml` | ?? | FORMAL_CONFIG | 双向 downhill endpoint 归类阈值和 unresolved policy | tracked `scripts/ts_validation/connectivity.py`；验证协议和 TS README | tracked `test_ts_validation.py` | YAML、POSCAR geometry | 是 | 无 | 无第二配置 | connectivity analyzer 默认入口失败 | 纳入正式配置 | 直接影响 Grade-A 前的 connectivity 证据，不得擅改 |
| `modules/calculation_registry/migrations/001_ts_endpoint_records.sql` | ?? | FORMAL_MIGRATION | 创建 endpoint table/index/version key | `ts_endpoint_database.apply_ts_endpoint_migration()` | purpose-manager 测试覆盖双执行 | registry v5 的 calculations/files/schema_metadata | 否 | 写 Schema | 主 schema 不包含该表；独立扩展版本 | migration 测试和 endpoint save fixture 失败；主 registry 其余功能不受影响 | 纳入版本审查，禁止执行直到修订 | `IF NOT EXISTS` 不验证同名表真实结构；见 migration 报告 |
| `modules/calculation_registry/migrations/001_ts_endpoint_records_rollback.sql` | ?? | FORMAL_MIGRATION | 删除 endpoint index/table/version key | 同一 migration API 的 `rollback=True` | 测试证明旧 calculations 行保留 | forward migration | 否 | 破坏性删除 endpoint 数据 | 与 forward Schema 对称 | rollback 测试失败；生产主流程不 import SQL | 纳入版本审查，不得对非空表执行 | 数据不可逆；无备份/非空保护 |
| `modules/structure_purpose_manager.py` | ?? | FORMAL_SOURCE | stable adsorption、TS endpoint、legacy 三路显式 routing；TS 路径保存记录 | 专用测试；当前无 unified CLI/生产 import | 16 个专用测试覆盖 routing、确认、legacy、save | config、generator、database、artifact hash | 是，工作流选择 | TS 分支写数据库 | 无 tracked 等价 manager；legacy 为兼容委托 | 专用测试失败；现有统一 CLI 当前不 import | 纳入正式源码；在 migration 条件关闭前不得接入生产 DB | 完整实现但正式入口尚未接线 |
| `modules/ts_endpoint_database.py` | ?? | FORMAL_SOURCE | endpoint Schema adapter、record 模型、idempotent save/query、migration wrapper | manager 和测试 | save/idempotency/migration/rollback | tracked registry.py、两个 SQL | 否 | 读写 SQLite、可改 Schema | 复用统一 registry connection；表为独有 | manager import/endpoint 测试失败 | 纳入正式源码；执行功能受 migration 条件约束 | 直接 DB 副作用集中于此；当前真实 DB 无该表 |
| `modules/ts_endpoint_generator.py` | ?? | FORMAL_SOURCE | 对既有 candidate 做验证、reuse eligibility 和确定性选择 | TS README、manager、测试 | global-minimum/path-compatible/extra-event 场景 | endpoint validator | 是 | 无写入 | 与 tracked endpoint/path check 有输入校验重叠但选择职责独有 | manager import 和 endpoint 测试失败 | 纳入正式源码 | 能量排在几何/事件门后，符合规则文档 |
| `modules/ts_endpoint_validator.py` | ?? | FORMAL_SOURCE | atom/periodic mapping、键变化、site coordination、位移和多事件判定 | generator 和测试 | 几何、键变化、mapping、warning 场景 | numpy、ASE、tracked structure/relaxed helpers、purpose config | 是 | 只读结构 | 与 tracked connectivity analyzer 都处理键/几何，但一个验证 endpoint purity、一个验证 downhill 归属 | generator/manager import 失败 | 纳入正式源码，科学规则保持锁定 | 阈值版本化；未发现 TODO/stub |
| `scripts/neb_agent/magnetic_continuity.py` | ?? | FORMAL_SOURCE | 邻接 image 总磁矩跳变的 non-blocking soft warning | pilot validation；analyze backend；历史 artifacts | pilot 磁矩 warning 测试 | 纯 dict | 是，物理 warning | 无 | 无第二 evaluator | pilot/submission import 失败 | 纳入正式源码 | 明确不停止、不证明磁态切换 |
| `scripts/neb_agent/path_quality_cli.py` | ?? | DUPLICATE_CANDIDATE | standalone path-quality evidence CLI | 无 import、文档命令、subprocess 或历史模块路径；`python -m ... --help` 成功 | 无直接测试 | path-quality core、两份 YAML、artifact_io | 不直接定义判定 | 写 `neb_path_quality.json` | 与 unified workflow 重复 config merge、collect/evaluate/write | 当前测试和正式 unified workflow不失败 | 保留；2B 变薄兼容层，不删除 | 完整可运行，不能仅凭无 caller 判废弃 |
| `scripts/neb_agent/path_quality_control.py` | ?? | FORMAL_SOURCE | 收集 NEB 文件证据并判断 underresolution/electronic/CI readiness evidence | tracked workflow、standalone CLI、execution evidence producer contract、README、历史 artifacts | 5 个 evaluator 测试；workflow 间接覆盖 | numpy、ASE、tracked VASP/structure parsers | 是 | 读取 VASP/path 文件，不直接写 | orchestration 被两个入口重复，核心算法唯一 | tracked workflow import 失败，统一 CLI不可用 | 纳入正式源码；2B 只整理职责，不改 evaluator | collect_evidence/入口等价覆盖不足 |
| `scripts/neb_agent/pilot_validation.py` | ?? | FORMAL_SOURCE | 从 LSF DONE 和每 image VASP 文件重建并验证短 pilot evidence | submission.py 正式 import；TS README；`python -m` 可用 | 2 个 build/validate 测试 | scheduler evidence、VASP parsers、magnetic continuity、artifact_io | 是 | 只读查询 scheduler；写 scheduler/pilot JSON | 无等价实现 | submission 模块 import 失败，pilot gate失效 | 纳入正式源码 | 测试 mock scheduler；真实远端未执行 |
| `scripts/ts_strategy_engine/active_learning_calibration.py` | ?? | FORMAL_SOURCE | 注册 TS-domain calibration、决定 calibration reuse | tracked active_learning.py→active_learning_cli→统一 CLI；README | tracked active-learning 测试覆盖 registration/reuse | schema loader、state/policy、artifact hash | 是，ML/VASP force gate | 原子写 state JSON | 状态字符串跨模块重复，职责独有 | active-learning facade import 失败 | 纳入正式源码 | 不得把 calibration 当最终 TS；实现明确保持 false claim |
| `scripts/ts_strategy_engine/execution_evidence.py` | ?? | FORMAL_SOURCE | file-bound evidence、source manifest、scheduler 和 Grade-A/连通性前提 | execution_gate.py 和 execution_gate_cli.py | gate 测试广泛覆盖 | artifact_io、scheduler_evidence、YAML | 是，授权前提 | 只读 evidence | 状态/producer 契约与 gate 紧耦合但无第二权威 | execution_gate import 失败 | 纳入正式源码 | 影响 STOP/submit/TS allowed actions，风险高但测试充分 |
| `scripts/ts_strategy_engine/execution_gate_cli.py` | ?? | FORMAL_SOURCE | 从 request 文件加载绑定证据并生成 authoritative gate decision | 专用 gate 测试；`python -m ... --help` 成功；无统一 CLI 子命令/文档命令 | 16 个 file-bound gate 测试中的 build_decision | execution evidence、execution gate、artifact_io | 不定义规则，只编排 | 写 decision JSON | 与 unified workflow 的 search decision 表面相近，但此入口强制 file binding | gate 测试失败；核心 gate仍可直接 import | 纳入正式源码并补文档入口 | 不是第二 authority；是 authority 的文件绑定适配器 |
| `tests/test_neb_execution_gate.py` | ?? | FORMAL_TEST | 锁定 gate 优先级、stop/submission/CI/DIMER、tamper 防护 | pytest discovery | 本文件 16 项 | gate、gate CLI、YAML/JSON fixtures | 仅编码预期 | 只写 tmp_path | 无重复测试文件 | 失去旧 file-bound 兼容和安全回归 | 纳入正式测试 | 不执行真实 scheduler |
| `tests/test_neb_path_quality_control.py` | ?? | FORMAL_TEST | 锁定 underresolved、smooth、CI readiness、family 去重、unverified flags | pytest discovery | 本文件 5 项 | `evaluate_quality` | 仅编码科学预期 | 无持久副作用 | 未覆盖 collector/CLI | 核心 evaluator 失去回归保护 | 纳入正式测试；2B 增加入口等价测试 | fixture 为内存 evidence |
| `tests/test_neb_pilot_validation.py` | ?? | FORMAL_TEST | 锁定 pilot build/validate/tamper 和磁矩 soft warning | pytest discovery | 本文件 2 项 | pilot module、tmp VASP-like files | 仅编码预期 | 只写 tmp_path；scheduler 被 mock | 无 | pilot/submission 安全回归缺失 | 纳入正式测试 | 不证明真实 LSF 行为 |
| `tests/test_structure_purpose_manager.py` | ?? | FORMAL_TEST | 锁定 endpoint 四模块、routing、科学事件、DB idempotency/migration | pytest discovery | 本文件 16 项 | numpy、SQLite tmp DB、四个 endpoint 模块、registry schema | 仅编码预期 | 只修改 tmp DB/files | 无 | endpoint 正式候选缺少主要证据 | 纳入正式测试 | rollback 测试未覆盖 endpoint 业务数据丢失 |
| `tests/test_vasp_inputs.py` | ?? | FORMAL_TEST | 锁定 NEB profile、MPI divisibility、basis override 和 magnetic branch | pytest discovery | 本文件 3 项 | tracked `scripts.vasp_inputs` | 仅编码计算输入契约 | 只写 tmp_path | 无 | VASP input 非回归保护降低 | 纳入正式测试 | 不运行 VASP |
| `tests/test_vasp_result_gate.py` | ?? | FORMAL_TEST | 锁定 OUTCAR EDIFF termination 优先于截断 OSZICAR delta | pytest discovery | 本文件 1 项 | tracked `vasp_result_gate` | 仅编码收敛规则 | 只写 tmp_path | 无 | 结果 gate 边界回归保护降低 | 纳入正式测试 | 不读取真实计算目录 |

## 状态汇总

| 归属 | 数量 |
|---|---:|
| FORMAL_SOURCE | 10 |
| FORMAL_TEST | 6 |
| FORMAL_CONFIG | 3 |
| FORMAL_MIGRATION | 2 |
| DUPLICATE_CANDIDATE | 1 |
| HUMAN_REVIEW | 1 |
| EXPERIMENTAL | 0 |
| LEGACY_CANDIDATE | 0 |
| INCOMPLETE | 0 |
| GENERATED_OR_RUNTIME | 0 |
