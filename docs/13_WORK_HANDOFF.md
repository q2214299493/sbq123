# Fe(110) 工作交接（薄路由）

更新时间：2026-08-10（Asia/Shanghai）

## 作用

本文件只说明接手顺序、权威来源和边界，不复制实时作业状态、历史流水或科学结论。当前任务、唯一下一步和审核要求由 `repo-state` 与受控投影视图提供。

## 接手顺序

1. 运行 `repo-state status`，只围绕其“唯一下一步”工作。
2. 读取 `tasks/current_task.md`。
3. 只读取 `docs/02_CURRENT_STATE.md` 中与当前任务相关的小节。
4. 读取 `modules/README.md` 和当前任务所属模块的 README。
5. 需要历史时运行 `repo-state history --entity ENTITY_ID`；不要从聊天记录重建项目状态。
6. 涉及实时计算时，再按需读取调度器摘要、计算文件和 Registry 记录。

## 权威顺序

- 调度器只对排队与运行状态负责。
- OUTCAR、OSZICAR、CONTCAR 等计算文件对电子、离子、力和最终结构负责。
- 所属科学模块的验证协议对科学有效性负责。
- `data/project_registry.sqlite3` 记录作业、结果、文件、审核和推广回执。
- `tasks/current_task.md`、CURRENT_STATE、module map 等是事件账本的可审阅投影，不覆盖实时计算证据。
- 聊天记录和普通记忆不是项目状态权威。

## 执行边界

- 后端角色以 `configs/execution_backends.yaml` 为唯一权威。
- VASP/VTST 提交、停止、重启、CI-NEB、DIMER、频率和结果推广必须经过所属模块的当前门槛。
- TS 动作必须满足 `scripts/ts_strategy_engine/execution_gate.py` 生成的当前哈希绑定决定。
- 未经用户明确授权，不删除、覆盖、提交高成本计算、推送 Git 或发布结果。

## 状态记录

- 任务、门槛、错误、决策和完成验收写入不可变事件账本。
- 任务开始运行 `repo-state audit --phase start`。
- 任务结束运行 `repo-state sync --safe-only` 和 `repo-state audit --phase end`。
- 只有确定性受控投影可以自动更新；冲突、科学接受、文件归档或删除仍需审核。
- 本文件不记录单个作业号、能量、路径或临时阻塞，防止再次成为过期状态副本。

## 历史与文件

- durable decisions：`docs/03_DECISIONS_LOG.md`
- unresolved failures：`docs/04_ERROR_LOG.md`
- important file classes：`docs/05_FILE_INDEX.md`
- module status：`docs/06_MODULE_MAP.md`
- historical results：`docs/08_HISTORICAL_RESULTS.md`
- immutable task history：`modules/state_handoff/events/` 与 `modules/state_handoff/history/`
