# 全局 skill 与仓库规则对齐（2026-11-14）

已更新四个全局 skill 及各自的 UI 元数据，共八个文件；安装文件与仓库版本逐字节一致。三个原本只有全局副本的路由 skill 已纳入仓库版本管理。

| Skill | 对齐内容 |
|---|---|
| `catalysis-data-retrieval` | 使用已核验项目的模块、白名单和资源。白名单有可用匹配即停止；仅吸附位点任务在 `NO_WHITELIST_MATCH` 后允许受控权威期刊回退。文献能量不能进入本地结果。 |
| `imaginary-freq-correction` | 补齐 DIMER/收敛 CI-NEB 的显式审核单虚频分支。阈值均未设置时仍需完整来源、模式及几何审核；CI-NEB 还需 `single_imaginary_mode_assessment=accepted_target_mode`。部分/无效阈值仍是配置错误。 |
| `neb-analysis-workflow` | 能垒使用兼容最终能量及注册门，不再隐含要求额外 matched-static。 |
| `neb-transition-state` | 按来源区分连通性：DIMER、CI-NEB 为可选诊断，普通 NEB 保留既有要求；最终能量服从当前方法协议。 |

活跃 Fe(110) 表面态沿用 `fe110_converged_toten_sigma0p20_v1`：兼容、收敛的 `ISMEAR=1`、`SIGMA=0.20 eV` 最终 `OUTCAR` `TOTEN`，不额外强制单点。分子参考和旧静态计算仍须按协议保持兼容，不能混用。三个初始模式覆盖要求、Grade A、哈希绑定执行门和作业授权均未放宽。

检索命令改为已存在的仓库入口 `python -m scripts.catalysis_retrieval.validate_cli` 和 `python -m scripts.catalysis_retrieval.cli`。所有仓库路径从当前已核验项目根目录解析，不再从全局 skill 目录取旧脚本或白名单。可选的铁基 FTS 文献方法参考仅在项目实际提供时读取。

验证：

- 四个 skill 在当前工作区、发布分支及全局安装中均通过 `skill-creator` 的 `quick_validate.py`，共 12 次验证。
- 八个安装文件与仓库来源逐字节一致；UI 的自动调用策略及依赖字段保持不变；其余六个既有辅助文件哈希未变。
- YAML 元数据、默认提示中的 skill 名称、必要规则路径和两个检索 CLI 的 `--help` 已验证。
- 发布分支现有检索、证据治理、CI-NEB 验收和验证流水线回归：73 项通过。
- 没有新建镜像测试或另建规则系统，也没有执行资料检索、模型推理、科学计算、结果注册或历史重算。

全局文件覆盖前已备份，并保存安装前后 SHA256 回执；不会用这些备份覆盖用户后续修改。

发布分支基于上次已验证的 `e3edc780`，以保留现行 CI-NEB 协议与实现。此更改只对齐 skill 指令和其来源，不表示此前审计中的多锚定生成、完整 GPU-path DIMER 发布或 DIMER 旧输出字段问题已解决。

未验证：Codex 对未来自然语言请求的实际选 skill 行为，以及模型是否逐项遵循新指令；上述格式和门禁回归不等同于该行为评测。
