# 催化计算统一数据检索前置门

## 目标

将吸附、共吸附、收敛、NEB/CI-NEB、DIMER、频率、反应网络和动力学之前的外部结构/路径检索统一到一个模块，取消各科学模块自行调用通用文献搜索的重复行为。

## 白名单

唯一可用于外部催化结构、吸附态、端点、轨迹和反应路径数据的来源为：

- [Catalysis-Hub GraphQL](https://api.catalysis-hub.org/graphql) 与 CatApp
- [Open Catalyst Project](https://opencatalystproject.org/) OC20/OC22 与 OC20NEB/CatTSunami
- [Materials Project Catalysis Explorer](https://next-gen.materialsproject.org/catalysis)
- [Materials Cloud Archive](https://archive.materialscloud.org/)
- [ioChem-BD](https://www.iochem-bd.org/)
- [NOMAD API](https://nomad-lab.eu/prod/v1/api/v1/extensions/docs) 的催化记录

精确域名和路径前缀位于 `skills/catalysis-data-retrieval/references/sources.yaml`。通用网页/文献检索不作为失败回退；无合格记录时输出 `NO_WHITELIST_MATCH`。

## 实现

- `validate_records.py`：校验必填来源字段和逐记录访问核验标记，并拒绝越界来源 URL 和下载 URL。
- `hybrid_search.py`：自实现 BM25，结合 MiniLM 句向量余弦排名，以加权 reciprocal-rank fusion 合并；输出最多五条。
- 图像查询：先记录可直接观察的结构特征，再单独记录带置信度的解释，形成文本查询。禁止依据显示颜色直接断定元素。
- `retrieval_prior_adapter.py`：NEB 仅消费通过白名单、语义后端和 Top-5 门禁的结构化结果，不再自行检索文献。
- 各科学模块仍负责模型匹配、几何、收敛、端点、路径和 TS 科学审查。

## 验证

- 技能格式：通过 `quick_validate.py`。
- 安全扫描：`is_safe=true`，最高仅 INFO，原因是未虚构许可证字段。
- 白名单：合规 Catalysis-Hub URL 通过，`example.com` 被拒绝。
- 混合检索：预计算语义向量与真实 `sentence-transformers/all-MiniLM-L6-v2` 两种测试均将 Fe(110)-CO 解离记录排第一。
- 语义环境：`sentence-transformers 5.6.0`；模型输出 384 维向量，权重存于 Git 外本地缓存。
- NEB 适配器：仅在 `whitelist_valid=true`、`production_ready=true`、`source_access_verified=true` 且匹配置信度为 high/medium 时生成路径候选约束。
- 重复扫描：活动代码中不存在旧 `literature_prior_adapter.py`、`utils_literature.py`、`--literature-file` 或 `use_literature_prior`。

## 接入判断

当前不需要 MCP。Catalysis-Hub、ioChem-BD、NOMAD、Materials Cloud 和 Materials Project 更适合直接官方 API/下载适配器；Materials Project 可能需要 `MP_API_KEY`。只有未来需要统一凭据管理或对外暴露标准工具接口时，才值得增加自定义 MCP。

CatApp 当前连接关闭；OC20NEB/CatTSunami 的现行机器端点和许可证、Materials Cloud API 行为、NOMAD 催化字段仍为 **Needs confirmation**。这些缺口已经进入 backlog，不以推测数据填补。
