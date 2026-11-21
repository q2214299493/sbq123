# Stage A.2.4 · 科学状态与能力报告治理

本轮以独立发布基线 `b3d0dd77e5ca84e6e6d42e88584bbbbe26595c79` 和含本地修改的开发树 `233d5a6c589560094a0e942b6d48708b1fd5a847` 分别取证。两树生成各自的能力报告。发布分支上的 reports/capability_readiness 两份文件仅代表发布树输入。

## 权威来源及边界

| 维度 | 来源和语义 |
|---|---|
| 模块生命周期 | 两树均由 docs/DOCUMENT_GOVERNANCE.md 的 owners.module_status 指向 docs/06_MODULE_MAP.md，同时核对 configs/state_handoff.yaml 的 managed_views.module_map。报告展示本树工作副本的行值。 |
| 受管投影 | data/state_handoff/projection_manifest.json 的 module_row 记录绑定事件 ID、事件摘要和预期行摘要。按 State Handoff 的行提取规则核对现场文本，差异标为 review_required。无行绑定只说明缺少对应记录。 |
| 软件实现与测试 | 模块图中的 capability-evidence 注释及可定位的代码、测试或审核报告。开发树没有正面的软件成熟度声明，发布树有五个模块带 partial 实现及测试证据。无证据时保持 unknown。 |
| 科学验证 | 由项目及具体科学模块核验结构、方法、数据来源和评审；本报告的科学注释继续只接受 unknown、unvalidated、not_applicable。 |
| 项目计算资格 | 报告明确记为 not_assessed；项目的已绑定网络、参数集、科学证据和执行门才决定能否运行。测试让模块呈 Active、软件呈 Completed，并以缺证数据调用真正的单点 qualify，验证它仍因缺证拒绝。 |
| 生产部署 | 读取明确的生产成熟度注释；缺省为 unverified，显式 unknown 亦可保留。支持的代码 schema 版本为 9，保留生产 schema 的 NOT_VERIFIED_IN_B6 口径。未查询生产库。 |
| 文档历史 | source_documents 保留治理文件与模块图各自声明的分支、版本、日期、角色、范围。input_sha256 标记本次实际输入文本与相关行绑定。治理文档的日期不代表新的调度、部署或科学观测。 |

## 历史与当前结果

原生成器对同一组输入已能重复输出；原测试失败源于已签入视图落后于模块图、历史状态期望固定，以及从 Blocked 生命周期推导生产状态。新视图显示行绑定并分离部署和项目执行资格。无关工单的清单项不计入能力视图的输入身份。

| 工作树 | B6 视图中的 kinetic_data / thermochemistry | 现场模块图 | 受管行核对 |
|---|---|---|---|
| 开发 | Planned / Blocked | Active / Active | 4 行匹配 |
| 发布 | Planned / Blocked | Planned / Active | 2 行匹配；transition_state_search 的整行摘要待审 |

两树的 baseline_mkm 生命周期均为 Blocked。原来按旧默认显示 blocked 的七个部署字段现在均为 unverified。没有新增任何科学认可或部署结论。开发与发布历史报告各保留 JSON 和 Markdown 原始字节。原发布日期、分支、源版本、证据清单和相应模块图指纹均留在 [开发快照](history/development/capability_readiness.json) 与 [发布快照](history/publication/capability_readiness.json)。用于检验历史调度观察与原始时序档重建的固定 fixture 来自提交 `93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a` 的 docs/02_CURRENT_STATE.md。

## 验证及复现

| 检查 | 开发树 | 发布树 |
|---|---:|---:|
| 修改前 B6 + State Manager | 60 通过、7 失败 | 65 通过、2 失败 |
| 修改后 B6 + State Manager | 70 通过、0 失败 | 70 通过、0 失败 |
| 另验 P1–P3 与实际 MKM 缺证执行门 | 14 通过 | 14 通过 |
| py_compile、Ruff | 两个变更 Python 文件通过 | 同左 |

发布树的旧失败为生成报告匹配和固定生命周期断言。开发树还复现五项发布范围假设，涉及 README 中的生产 schema 声明、B6 调度快照、未跟踪草案分类、历史时序拼接及仅发布树具有的 PUBLIC_RELEASE.md。测试现在分别检查治理所有者、版本化或显式保留的文档、固定 B6 来源和本树实际链接。两个源树均保留失败断言对未授权科学验证声明的拒绝测试。新增输入冲突测试检查行摘要变化和绑定清单的不可变性。State Manager 原有 41 个用例前后均通过。

各自复制全部已声明的来源和绑定清单到临时目录，连续两次生成，与本树提交或保留的生成文件逐字节比对。核对受控输入全部原样保留，输出仅有指定的两个报告。确定性针对同一组输入。

| 工作树 | 输入集合 SHA-256 | JSON SHA-256 | Markdown SHA-256 |
|---|---|---|---|
| 开发 | `cd75982b6ac89f047f3d5b705b59e161fa2ef935070c8371421339fcfb781c7b` | `9b7a778bd55cf8bda439e23768ea76da3146270b83c10a7c83520669c44a290d` | `bf9ecf6b00b17f450518fe180fe00942ebd3518e4302874fd74b4c72b655c769` |
| 发布 | `c8080cbe986e58194b0b4abfd22c06c71c27185f68790ce253d4ebc29475f968` | `e356bbb9559443fd1b3059476e31993026ac2272275dcbeed584e774007a9680` | `1c432087e24012a74161661b3909e8ad2d48ae1fa2f81f94a0a14c74f57d2eab` |

P1–P3 核对范围包括 Registry CLI 边界、适配器回边、公开导入、原生模型输入字节重放、DRC 批次计划及完整维护代码静态无环测试。全仓测试和原生科学计算均未运行。

## 待审现场差异

[冲突清单](state_conflicts.json)逐项列出源路径、预期与现场 SHA-256、受影响投影、既有决定和研究者可选的处理方式，包括待审模块事件的过期或缺失输入。null 表示该来源在本树无现场文件。待审前置条件与已经阻断全局同步的原因分别记录。

- 开发树当前同步首先遇到 Scientific Intake schema 的旧证据哈希。已有批准绑定旧来源。需恢复并核验原始证据，或按当前来源提出后继事件。
- 发布树同步首先遇到历史压缩事件的 docs/02_CURRENT_STATE.md 来源变化。需复核原段落、压缩边界及归档，决定是否替换或退役旧压缩。
- 发布树另有 transition_state_search 整行漂移。行的生命周期仍为 Active，报告明确标记待审。研究者可依据现有计算证据提出后继事件，或通过正式流程恢复原绑定行；不能将一次报告再生成视为接受该行。

本轮未更新模块图、历史事件哈希或受管投影。两树实际的同步结果和本轮提案列在 [State Handoff 回执](handoff.md)。

## 实际变更文件

- `docs/DOCUMENT_GOVERNANCE.md`
- `scripts/generate_capability_readiness.py`
- `reports/capability_readiness.json`
- `reports/capability_readiness.md`
- `tests/test_b6_governance.py`
- `tests/fixtures/document_governance/b6_publication_current_state.md`
- `reports/multiphase/stage_a2_4/history/development/capability_readiness.json`
- `reports/multiphase/stage_a2_4/history/development/capability_readiness.md`
- `reports/multiphase/stage_a2_4/history/publication/capability_readiness.json`
- `reports/multiphase/stage_a2_4/history/publication/capability_readiness.md`
- `reports/multiphase/stage_a2_4/state_conflicts.json`
- `reports/multiphase/stage_a2_4/completion.md`
- `reports/multiphase/stage_a2_4/handoff.md`
- `modules/state_handoff/events/history-stage-a2-4-readiness-governance-20261121.json`

开发树的治理文件保留本地约定，其生成视图保留本树来源。发布树只提交本任务的独立版本。下一步是研究者复核上述历史来源冲突。P5 未启动。
