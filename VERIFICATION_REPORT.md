# 独立回归验收与变更审查

审查日期：2026-07-27

分支：`codex/ts-workflow-cleanup-20260722`

结论：**PASS WITH CONDITIONS**

## 1. 结论摘要

本轮重构的核心行为通过独立接口扫描、完整回归、真实本地子进程超时、
多进程文件写入和 mock 提交验收。没有发现科学、物理、化学、配置 Schema、
数据库或历史结果语义被改变。

独立审查发现并修复两个本轮相关问题：

1. 远端 `bsub` 在本地超时或连接中断时，结果可能不确定，原实现允许重试，
   存在重复提交风险。现增加 `submission_attempt.json` 未决标记和已有
   `submission_record.json` 拦截。
2. `execution_gate.py` 拆分后意外暴露 `make_decision` 和
   `decision_from_quality` 两个实现符号。现改为私有导入别名，旧公开面保持
   不变。

进入下一阶段前有三个条件：

- 将本报告列出的已验证文件隔离为可审查的变更集；当前工作树仍混有大量
  审计前改动。
- 真实任务目录若出现 `submission_attempt.json`，必须先查询同一 LSF 任务
  和远端目录，不能直接删除标记或重试。
- `scripts/convergence/setup_alpha_fe_bulk_smearing.py` 的旧提交入口在增加
  相同的超时/未决提交保护前不得用于新提交。

## 2. Git 差异范围与审查限制

### 2.1 完整工作树差异

实际执行：

```text
git diff --name-status
git diff --numstat
git diff --unified=0 --no-ext-diff
git diff --check
git ls-files --others --exclude-standard
```

结果：

- 63 个已跟踪文件发生修改；
- 已跟踪差异为 3254 行增加、1073 行删除；
- patch 为 251149 bytes、4984 行、405 个 hunk；
- 510 个未跟踪文件；
- 没有 Git 删除或重命名；
- `git diff --check` 退出码 0；
- 六个已有 YAML 文件存在 Git 的 LF/CRLF 提示，但没有空白错误。

63 个已跟踪文件中包含当前任务开始前已经存在的 TS、配置、状态和计算
差异。它们不能归因于本次重构。本轮与重构/验收重叠的已跟踪文件只有：

- `docs/14_CODE_ARCHITECTURE_GUIDE.md`
- `modules/transition_state_search/README.md`
- `scripts/README.md`
- `scripts/artifact_io.py`
- `scripts/neb_agent/remote_monitor.py`
- `tests/test_neb_remote_monitor.py`

`execution_gate.py`、`submission.py`、`scheduler_evidence.py` 和多项测试在首次
重构前已经是未跟踪文件，因此普通 `git diff` 没有它们的基线。对这些文件
采用了完整源码检查、导入扫描、签名契约测试和行为矩阵测试，不能声称已从
Git 证明逐字节等价。

### 2.2 本次实际审查的文件

| 文件 | 实际修改或作用 | 修改原因 |
|---|---|---|
| `README.md` | 新增安装、CLI、配置、工作流、测试和安全说明 | 补齐项目入口 |
| `PROJECT_AUDIT.md` | 记录原基线和审计发现 | 审计交付 |
| `REFACTOR_PLAN.md` | 记录范围、阶段和暂缓项 | 控制重构边界 |
| `ARCHITECTURE.md` | 记录目录、调用、数据流和外部后端 | 架构交付 |
| `DEPRECATED_CODE.md` | 记录待退役兼容层，不删除 | 防止无证据删除 |
| `REFACTOR_REPORT.md` | 记录第一轮实施结果 | 重构交付 |
| `VERIFICATION_REPORT.md` | 本独立验收报告 | 验收交付 |
| `scripts/ts_strategy_engine/execution_decision.py` | 纯决策文档构造 | 从执行门分离序列化职责 |
| `scripts/ts_strategy_engine/execution_gate.py` | 调用纯构造器；旧常量和函数仍从旧路径导出 | 保留唯一授权入口 |
| `scripts/artifact_io.py` | 唯一同目录临时文件、flush、fsync、原子 replace、失败清理 | 避免固定 `.tmp` 冲突 |
| `scripts/neb_agent/remote_monitor.py` | 60 秒 SSH 超时和 CLI 错误退出 | 防止无限等待 |
| `scripts/scheduler_evidence.py` | 60 秒 LSF 查询超时 | 防止把无响应解释为状态 |
| `scripts/neb_agent/submission.py` | 300 秒外部命令超时；未决/成功提交保护 | 防止挂起和重复提交 |
| `scripts/README.md` | 说明执行门、构造器和提交器边界 | 文档同步 |
| `modules/transition_state_search/README.md` | 说明执行门和构造器职责 | 文档同步 |
| `docs/14_CODE_ARCHITECTURE_GUIDE.md` | 更新真实测试快照，删除未验证 wheel 声明 | 消除过期结论 |
| `tests/test_artifact_io.py` | 格式、失败回滚、唯一临时文件、多进程完整性 | 文件写入回归 |
| `tests/test_external_command_boundaries.py` | LSF 状态、超时、直接子进程终止 | 外部命令回归 |
| `tests/test_neb_remote_monitor.py` | 参数、超时、SSH 非零状态 | 监控回归 |
| `tests/test_execution_gate_compatibility.py` | 旧导入、签名和反向依赖 | 拆分兼容回归 |
| `tests/test_neb_submission.py` | 失败、未决、已完成和成功提交记录 | 幂等与重复提交回归 |
| `tests/test_config_boundaries.py` | 示例配置和非法根类型 | 配置边界验收 |

## 3. 十二项变更影响核对

### 3.1 公共 API

- `execution_gate.decide_execution`
- `execution_gate.require_action`
- `execution_gate.validate_decision`
- `execution_gate.ACTIONS`
- `execution_gate.GATE_NAME`
- `execution_gate.INITIAL_SUBMISSIONS`

以上旧符号仍可从原路径导入。参数顺序、关键字专用参数和默认值由兼容测试
锁定。`artifact_io` 和 `remote_monitor` 相对 `HEAD` 的原有公共函数签名
没有变化。

`execution_decision.py` 新增纯构造接口，不替代旧入口。验收时发现并消除了
其构造函数通过 `execution_gate` 意外公开的问题。

结论：没有破坏性公共 API 变化；存在一个已修复的意外 API 扩张。

### 3.2 Import 路径

旧路径仍有效：

```text
scripts.ts_strategy_engine.execution_gate
scripts.artifact_io
scripts.neb_agent.remote_monitor
scripts.scheduler_evidence
scripts.neb_agent.submission
```

仓库中有八处 Python import 继续从旧 `execution_gate` 路径调用：

- `scripts/neb_agent/generate_path.py`
- `scripts/neb_agent/submission.py`
- `scripts/ts_strategy_engine/evidence.py`
- `scripts/ts_strategy_engine/execution_gate_cli.py`
- `scripts/ts_strategy_engine/handoff.py`
- `scripts/ts_strategy_engine/strategy.py`
- `tests/test_neb_execution_gate.py`
- `tests/test_ts_handoff.py`

没有私有 `_decision` 或 `_from_quality` 的外部导入。

结论：旧 import 路径未改变。

### 3.3 CLI

参数和子命令未修改。`remote_monitor` 新增的行为是：SSH 超时时打印错误并
退出 1；非超时 SSH 失败仍返回 SSH 的非零退出码。`submission` 的
`submit` 子命令现在拒绝已有成功记录或未决尝试。

结论：CLI 语法兼容；失败和重复提交保护增强，属于已记录行为变化。

### 3.4 配置 Schema

本次没有修改 `configs/`、JSON Schema、YAML 字段或默认值。25 个 YAML 和
4 个 JSON 配置可解析。

结论：无影响。

### 3.5 序列化和输出文件

`artifact_io` 对相同 payload 的 JSON 文本与旧
`json.dumps(..., indent=2) + "\n"` 格式逐字节一致。

新增一个安全状态文件：

- `submission_attempt.json`：写在执行远端 `bsub` 前；若结果不确定则保留。

成功后仍写原有 `submission_record.json`，然后删除未决标记。

结论：JSON 既有格式不变；新增一个明确记录的提交安全文件。

### 3.6 数据库

没有修改 SQLite 文件、Schema、迁移、SQL 或注册表写入逻辑。

结论：无影响。

### 3.7 任务目录和历史结果

验收只在 pytest 临时目录中写入测试文件。没有修改、删除、提交、停止或
重启任何已有计算。生产代码新增的未决标记只在未来实际调用 `submit()` 时
产生。

结论：现有任务目录和历史结果未受本次验收操作影响。

### 3.8 科学、物理和化学判定

没有修改几何、吸附、连通性、SCF、NEB 路径、TS、频率、能量、阈值、
候选筛选或兼容性公式。

`execution_gate` 的证据优先级仍是：

```text
显式用户停止
  -> 阻断项
  -> 正常推进判定
```

纯构造器只接收已经选定的 decision/reasons/allowed，不选择科学状态。

结论：无改变。

### 3.9 未记录行为变化

审查前发现两项，均已在本报告记录并补测试：

- 构造器符号意外从旧模块公开；
- 提交超时后的重复提交风险。

未发现其他未记录行为变化。

## 4. `execution_gate` 拆分专项审查

### 4.1 循环依赖

当前依赖方向：

```text
execution_gate
  -> execution_decision
  -> artifact_io
```

`execution_decision.py` 不导入 `execution_gate.py`。完整项目 Python 导入图
扫描未发现强连通分量大于 1 的循环。

结论：无循环依赖。

### 4.2 公共导入兼容

兼容测试使用原模块路径实际导入旧常量和函数，并确认：

- `execution_gate.ACTIONS is execution_decision.ACTIONS`
- `GATE_NAME` 相同；
- `decide_execution`、`require_action`、`validate_decision` 仍由旧模块提供；
- 新纯构造函数不从旧模块公开。

结论：旧调用继续有效。

### 4.3 参数、返回值、异常和副作用

- `decide_execution` 的 11 个参数、关键字专用位置和六个 `None` 默认值不变；
- `require_action` 三个参数不变；
- `validate_decision` 一个参数不变；
- 返回值仍为包含 Schema-v2 字段的字典；
- 未知动作仍为 `ValueError`；
- 未授权动作仍为 `PermissionError`；
- 过期或篡改决策仍为 `ValueError`；
- `decide_execution` 仍无文件、网络或数据库副作用；
- 时间戳和状态哈希仍在决策文档构造时产生。

结论：旧接口行为保持。

### 4.4 重复定义和执行顺序

- 当前 Python 静态扫描没有顶层重复函数或类定义；
- `ACTIONS` 和 `GATE_NAME` 的唯一实际定义在 `execution_decision.py`，
  `execution_gate.py` 只重导出；
- 原 `_decision` 逻辑移动为 `make_decision`；
- 原 `_from_quality` 逻辑移动为 `decision_from_quality`；
- 授权分支顺序没有移动。

16 个原执行门测试覆盖用户停止、电子失败、路径欠分辨、缺少路径绑定、
当前调度状态、CI-NEB、DIMER、已验证 TS、决策篡改和过期哈希。新增 3 个
测试直接保护旧导入、签名和无反向依赖。

结论：没有证据表明拆分改变执行顺序。

### 4.5 Git 证据限制

`execution_gate.py` 在首次重构前未被 Git 跟踪，无法通过
`git diff HEAD -- execution_gate.py` 生成拆分前后 patch。因此等价结论来自
原测试未改动、公共签名清单、调用扫描和 19 项执行门专项测试，而不是
Git 的逐行历史。

## 5. 初始失败项调查

原失败测试：

```text
tests/test_code_structure.py::test_ts_engine_layers_do_not_recombine
```

失败证据：

```text
assert max(lines for scripts/ts_strategy_engine/*.py) <= 320
实际最大值：370
文件：execution_gate.py
```

调查结论：

1. 原测试检查 TS engine 不重新合并为大文件。
2. 失败来自执行门同时包含授权分支和决策文档构造。
3. 修复的是实际职责膨胀：纯构造逻辑被移到无 I/O 模块。
4. `tests/test_code_structure.py` 没有修改，`git diff` 为 0 bytes。
5. 320 行约束没有降低、删除或跳过。
6. 当前 `execution_gate.py` 为 310 行，结构测试通过。

因此不是通过修改测试或降低约束制造通过结果。

### 5.1 从 197 到 202 的五项新增测试

| 测试 | 保护行为 |
|---|---|
| atomic JSON 成功替换 | 新内容可读且不残留临时文件 |
| atomic JSON 序列化失败 | 旧目标保留且临时文件清理 |
| NEB monitor timeout | 超时抛出明确错误，不返回成功 |
| scheduler finite timeout 参数 | LSF 查询实际传入 60 秒超时 |
| submission timeout cause | 300 秒超时保留 `TimeoutExpired` 原因链 |

独立审查发现这五项仍未覆盖未知 LSF 状态、真实直接子进程终止、多进程写入、
旧执行门 API 和提交重试，因此又补充了对应测试。当前完整测试总数为 217。

## 6. 公共引用和动态入口扫描

扫描范围包括 `scripts/`、`modules/`、`tests/`、配置、文档、计算记录和
未归档脚本。

结果：

- `artifact_io`：44 个 Python import 调用方；
- `execution_gate`：8 个 Python import 调用方，24 个代码/文档/历史记录匹配；
- `execution_decision`：只有 `execution_gate` 直接依赖，没有外部调用方；
- `scheduler_evidence`：6 个 Python import 调用方；
- `remote_monitor`：测试直接导入，文档和输出构建脚本有字符串引用；
- `neb_agent.submission`：测试直接导入，协议和文档记录其模块路径；
- 没有针对这些模块的 `importlib`、`__import__` 或 entry-point 动态导入；
- `pyproject.toml` 没有插件注册表或 CLI entry-point 映射；
- 历史 JSON 中记录的
  `scripts.ts_strategy_engine.execution_gate.decide_execution` 路径仍有效；
- 配置 Schema 中的 scheduler evidence 是文档类型，不是 Python 模块导入。

结论：文件拆分没有使仓库内旧调用失效。

## 7. 轻量级真实验收

没有连接真实远端、提交 VASP/NEB 或调用 `bsub/bkill`。

### 7.1 CLI

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `python -m scripts.ts_strategy_engine.cli --help` | 0 | 显示统一 TS 子命令 |
| `python -m scripts.adsmind_lite.plan_adsorption_candidates --help` | 0 | 显示必填 species 和配置参数 |
| `python -m scripts.neb_agent.submission --help` | 0 | 显示 preflight/submit/stop |
| `python -m scripts.neb_agent.remote_monitor --help` | 0 | 显示 host/job_dir/detail |

### 7.2 行为验收

执行 18 项轻量验收，退出码 0：

```text
python -m pytest -q
  tests/test_config_boundaries.py
  monitor timeout/connection-failure tests
  scheduler timeout/unknown-state tests
  submission timeout/direct-child tests
  submission failure/retry/success-record tests
  tests/test_artifact_io.py
  active-learning dry-run test
  TS handoff dry-run test
```

逐项结果：

| 要求 | 实际结果 |
|---|---|
| 示例配置读取 | `analysis_rules.yaml` 成功读取为 mapping |
| 非法配置错误 | list 根节点产生 `YAML root must be a mapping` |
| NEB monitor 超时 | `RuntimeError`，不是成功状态 |
| SSH 连接失败 | 返回 255，CLI 不会解释为成功 |
| LSF 查询超时 | `RuntimeError`，没有 scheduler evidence |
| LSF 提交失败 | 不生成 `submission_record.json` |
| artifact 并发写 | 4 个 spawn 进程均退出 0；最终 JSON 完整 |
| 临时文件清理 | 成功和异常后均无 `.target.*.tmp` |
| 已完成任务重提 | 有 `submission_record.json` 时在网络调用前拒绝 |
| 未决任务重提 | 有 `submission_attempt.json` 时在网络调用前拒绝 |
| 未知 LSF 状态 | `ValueError`，不解释为成功 |
| dry-run | active-learning 和 TS handoff 不产生目标写入或提交 |

## 8. 超时设计审查

| 模块 | 超时 | 超时结果 | 命令失败 | 状态影响 |
|---|---:|---|---|---|
| `remote_monitor.py` | 60 s | `RuntimeError`；CLI 退出 1 | 保留 SSH 非零码 | 只读，不写任务状态 |
| `scheduler_evidence.py` | 60 s | `RuntimeError`，保留原因链 | 错误含 stderr 或 stdout | 不生成调度证据 |
| `submission.py` | 300 s | `RuntimeError`，保留原因链 | 错误含返回码和 stderr | 保留未决标记，禁止自动重试 |

结论：

- 超时为模块级常量，不是集中配置；数值存在硬编码，但用途和测试明确。
- timeout、非零返回码和未知调度状态使用不同异常路径。
- `subprocess.run(..., timeout=...)` 会终止并等待直接子进程；本地真实子进程
  测试确认超时后不会继续写 sentinel。
- 不能证明远端进程一定在 SSH 断开时终止。对 `bsub` 使用未决标记处理该
  不确定性。
- 没有无限重试或自动重试。
- 一次网络抖动会中止当前操作，但不会写成功状态或自动重复提交。
- timeout 异常的部分 stdout/stderr 保留在 `TimeoutExpired` 原因对象中，
  但用户可见错误文本没有展开部分输出。

仍有一个审计前生产调用没有超时：

```text
scripts/convergence/setup_alpha_fe_bulk_smearing.py:121
```

它调用 `bsub` 后才写 `submitted.jobid`，在中断窗口存在不确定/重复提交风险。
本轮没有选择新的超时数值或修改该旧工作流。

## 9. `artifact_io` 并发与文件系统审查

已验证：

- `tempfile.mkstemp` 为每次写入返回唯一文件名；
- 临时文件 `dir=path.parent`，与目标位于同一目录和文件系统；
- 成功路径使用 `os.replace`；
- JSON 写入后 flush 和 `os.fsync` 文件描述符；
- 序列化失败保留旧目标；
- `BaseException` 清理临时文件后立即 re-raise；
- 多进程同时写同一目标时，最终文件是某一个 writer 的完整文档；
- 两次写入实际使用不同临时文件名；
- Windows 和 Linux 均支持 `mkstemp`、关闭文件后的 `os.replace`。

行为边界：

- 多写者语义是 **last-writer-wins**；
- 不提供锁、版本比较、字段合并或 compare-and-swap；
- 因此可声称“不会产生半写 JSON 或共享固定临时文件”，不能声称“不会丢失
  并发业务更新”；
- 当前只 fsync 文件，没有 fsync 父目录；断电后的目录项持久性未验证；
- 不能用单机测试证明网络文件系统的 rename 语义。

## 10. 代码质量检查

实际结果：

```text
python -m ruff check scripts modules tests
exit 0: All checks passed

python -m pytest -q -ra
217 collected, 217 passed, exit 0
```

没有 skip 或 xfail。

AST/文本扫描：

- 141 个 Python 文件，无解析错误；
- 顶层重复函数/类定义：0；
- 循环依赖：0；
- 裸 `except`：0；
- 静默 broad-except：0；
- 无限制 `while True`：0；
- `Path.cwd()`/`os.getcwd()` 依赖：0；
- 固定 `.tmp` 写入：0；
- 生产 `subprocess.run` 共 5 处，其中 1 处缺少 timeout；
- broad exception 共 2 处：
  - `artifact_io.py`：清理后 re-raise；
  - `registry.py`：rollback 后 re-raise。

项目未配置 mypy、pyright 或 flake8，本轮未新增工具。

## 11. 后续问题分级

### P0

#### 旧 alpha-Fe smearing 提交缺少未决保护

- 文件：`scripts/convergence/setup_alpha_fe_bulk_smearing.py:121-126`
- 证据：`subprocess.run(["bsub", ...])` 无 timeout；job marker 在返回后写入。
- 收益：避免挂起和返回不确定时重复提交。
- 风险：修改旧收敛工作流可能影响历史用法。
- 所需测试：timeout、非零返回、已提交 marker、未决 marker、成功解析。
- 立即处理：仅在再次使用该提交入口前处理；当前不得运行它。

当前重构引入的 P0 已通过 `submission_attempt.json` 修复，没有开放 P0。

### P1

#### 多写者状态更新仍是 last-writer-wins

- 文件：`scripts/artifact_io.py` 及 active-learning state 写入调用方。
- 证据：原子 replace 保证完整文件，但没有版本检查或锁。
- 收益：若未来存在并行 controller，可避免业务更新丢失。
- 风险：引入锁或 CAS 会改变状态写入协议。
- 所需测试：两写者读取同一旧版本、冲突检测、崩溃恢复、Windows/Linux。
- 立即处理：否；先确认是否允许多 controller 并行写同一 state。

#### 超时和错误上下文分散

- 文件：`remote_monitor.py`、`scheduler_evidence.py`、`submission.py`
- 证据：60/60/300 为局部常量；timeout 文本不显示部分 stdout/stderr。
- 收益：运维配置和诊断更统一。
- 风险：建立通用外部命令框架可能过度设计并改变异常。
- 所需测试：三类失败、兼容错误文本、配置缺失。
- 立即处理：否；当前常量明确且测试覆盖。

#### 当前工作树不可作为单一重构 patch

- 文件：63 个跟踪差异、510 个未跟踪文件。
- 证据：完整 Git 统计和首次审计基线。
- 收益：使后续 review、回滚和归因可靠。
- 风险：错误暂存可能混入计算产物或凭据。
- 所需测试：任务文件清单、diff check、完整回归。
- 立即处理：是；在用户授权提交前先隔离，但本轮不暂存或提交。

### P2

#### 执行门未声明显式 `__all__`

- 文件：`scripts/ts_strategy_engine/execution_gate.py`
- 证据：公共面靠命名惯例；本轮已用私有别名避免扩张。
- 收益：更明确的公开契约。
- 风险：可能改变现有 `import *` 行为。
- 所需测试：旧符号和 wildcard import 快照。
- 立即处理：否。

#### 文档测试数量会随测试增加而过期

- 文件：`docs/14_CODE_ARCHITECTURE_GUIDE.md`、`REFACTOR_REPORT.md`
- 证据：已从 81、202 更新到本报告的 217。
- 收益：避免静态数字失真。
- 风险：低。
- 所需测试：无需代码测试。
- 立即处理：否；后续文档优先写命令和日期，少写长期固定数量。

### 不建议修改

- `build_fe110_adsorption.py`：稳定的 Fe(110) 几何权威，按行数拆分收益低、
  科学风险高。
- SQLite 事务中的 `except Exception`：rollback 后立即 re-raise，行为正确。
- 将所有 YAML loader 合并为通用配置框架：当前领域 Schema 不同，容易制造
  条件分支和错误兼容。
- 为了消除硬编码而立即引入大型外部命令框架：当前规模不支持该复杂度。

## 12. 最终判定

**PASS WITH CONDITIONS**

支持证据：

- 完整 Git 差异元数据和 4984 行 patch 扫描；
- 旧执行门测试未修改，原 320 行约束未降低；
- 19 项执行门专项测试通过；
- 18 项轻量验收通过；
- 217/217 完整测试通过；
- Ruff、配置解析、CLI 和 diff check 通过；
- 无循环依赖、重复定义、skip/xfail、静默异常或无限循环；
- 本轮发现的重复提交风险和 API 泄漏已修复并有回归测试。

限制条件是版本控制可审计性和真实远端状态不确定性，不是当前单元/本地行为
失败。满足第 1 节三个条件后，可以进入第二阶段；本报告不授权新的大规模
重构或任何真实计算提交。
