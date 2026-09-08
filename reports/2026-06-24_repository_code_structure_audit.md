# 仓库去重与代码结构审计

## 范围

审计当前 Git 跟踪树、根目录、`scripts/`、`skills/`、`configs/`、`tests/`、模块文档、计算快照和迁移证据。计算结构、输入参数、历史报告和导入包只做权威性分类，不修改科学内容。

## 主要发现

- 审计开始时有 339 个跟踪文件；大量重复来自 NEB 计算快照、端点副本和 memory-migration 证据，属于来源证明，不能机械删除。
- 根目录混有 8 个 Python 脚本、网页快照、3.3 MB 微信抓取页、无关网页 JavaScript 和历史 XYZ。
- Python 没有统一项目配置或测试目录；两个收敛脚本含未使用导入，三个收敛脚本复制了 TOTEN 解析器。
- `configs/neb_agent/literature_prior_schema.json` 在旧适配器删除后仍残留。
- `diagnose_path_geometry.py` 使用过滤后的结构列表配原始目录列表；当中间 image 文件缺失时，报告 image 名可能错位。

## 结构优化

- 四个仍可复用的收敛脚本移动到 `scripts/convergence/`。
- 四个一次性 endpoint-derived 路径脚本移动到 `archive/legacy_neb_scripts/endpoint_derived_20260623/`，保留来源但不再作为当前命令。
- 官方页面/文章文本移入 `archive/web_sources/`；历史 XYZ 移入 `archive/legacy_neb_artifacts/`。
- 删除当前树中的 3.3 MB 抓取页和无关 JavaScript；它们仍存在于 Git 历史，不再污染当前上下文。
- 删除两个重复 requirements 文件，由 `pyproject.toml` 统一基础、NEB、retrieval 和 dev 依赖，并统一 Ruff/pytest 配置。
- 新增 `scripts/README.md`，只定义布局，不复制模块命令。
- 将三个重复 TOTEN 提取函数合并为 `scripts/convergence/common.py`。
- 将旧 literature schema 替换为当前 `retrieval_prior_schema.json`。
- 拆分 NEB 几何测量/报告和路径生成选择/写出逻辑，修复非连续 image 目录名错配。
- 新增 `tests/`，用布局测试阻止根目录重新堆入 `.py/.js/.html/.xyz`，并阻止旧 literature 接口返回。
- 扩展 `.gitignore`，阻止模型权重、LMDB、原始/缓存数据和 Python build 产物进入 Git。

## 验证

- `ruff check .`：通过。
- `ruff format --check scripts skills modules/fe_convergence_baseline tests`：通过。
- `python -m pytest`：9 项通过。
- 当前 `scripts/skills/configs/tests` 字节级重复：0。
- 当前 Python 重复函数体：0。
- 敏感/大文件检查：未引入 POTCAR、OUTCAR、WAVECAR、CHGCAR、模型权重或凭据。

## 保留的重复

以下重复属于科学可追踪性，不做删除：不同 NEB 尝试中的 POSCAR/INCAR/KPOINTS/LSF，端点与 `POSCARis/POSCARfs`，导入用户包，以及 memory-migration 中与原始 evidence 对应的副本。它们均由 `docs/05_FILE_INDEX.md` 的权威分类约束，不能作为当前默认命令。

## 后续约束

- 新线程优先读取仓库，不从聊天或 `.codex` memory 重建状态。
- 当前代码只能进入 `scripts/`、repository-backed skill 或相应模块；一次性脚本和下载快照进入 `archive/`。
- 实时提交、全部收敛 CLI 分支和 custodian 全模式测试仍未覆盖，已进入 backlog；在覆盖完成前继续人工审核。
