# Phase 2C：待独立审核的历史候选

**AWAITING_INDEPENDENT_REFERENCE_REVIEW**。7个事件线索、5个分组，构建6题 incomplete 草稿；1个事件暂缓。所有参考为null，已批准参考与可评分案例均为0。A/B及评分未运行，没有泛化结果或晋级结论。

## 交付

- [准备报告](report.md)
- [待审核队列](REVIEW_QUEUE.md)
- [完整字节保真归档](deliverables.zip)：39个原文件，含intake、原始/派生来源、指针/行号及哈希、pending审核请求、草稿manifest/bundle、构建日志、长路径失败记录、执行约定与最终核验。
- [发布清单和逐文件身份](publication_manifest.json)
- [本次只读发布审计](publication_repository_audit.json)及[命令与退出码](publication_audit_execution.json)

报告中的intake、reviewer_packet及control相对链接用于解压完整ZIP后查看。ZIP保留原字节，避免Git换行规范化破坏来源绑定。目录名private表示材料用途，在Git仓库中发布不构成访问隔离；未批准的草稿及审核材料不能整体提供给未来A/B答题过程。

## 冻结和实际缺口

开发基线697153133a4d430120543b02f6cd5abe1d481c73、Phase2B候选eccfaa274b7ac73e266420fa7a05be917a5b18c9及diagnostic_certainty_v1保持不变。Harness SHA-256为e45bbff5866ec94794be22fb36854b91a9ba5e78dbbb72f8b6259cde948630cc；原五题公开身份仍为500d33ac92a838371e1f76e096e6bc0db95ec8d864c0993495a2467a191d9ba2。

新草稿公开身份c22ea216a59b715411c8a2760694826c4b7432b9ea5821d91f9892533315c8b4仅标识本次草稿，题面尚未最终冻结，不能用于正式held-out成绩。

独立审核者尚未指定；confirmed/hypothesis/unknown覆盖及至少两个正确confirmed反例尚未建立。部分事件只有历史摘要，原始故障文件未定位；g004与开发反应家族重叠，h007谱系仍须确认。GPU1793有后续TMPDIR归因，保留完整本地来源供审核，暂不纳入公开草稿；没有删除材料来凑unknown。

构建阶段cases-build退出码0，现有loader通过6题草稿核验。本次发布重新核对37个清单文件、39个ZIP成员及48份不可变来源/开发材料；没有重新构建、答题或评分。只读仓库审计返回1，既有docs/06_MODULE_MAP.md模块投影漂移已记录，未修复或sync。新提交CI及跨机器草稿重建尚未验证。

此前运行记录中的不commit/push描述候选准备阶段；本次发布依据随后明确的“推送”授权。发布不批准任何参考，不修改Harness、原五题、科学标准、生产源码、数据库或计算状态。下一步为独立审核来源、范围、分组及参考；审核后在新版本冻结reviewed_bundle和公开三文件，才执行同环境A/B各一次。

## 跨机器重建草稿

原包保留准备环境的绝对路径；解压本归档到新目录后，需按照清单确认原字节，再使用同一代码基线的现有cases-build和解压snapshots/manifest.json重建到新包目录。manifest内来源仍需按实际解压位置重新绑定；不能声称直接克隆即可加载，更不能将pending改成approved跳过审核。本次未验证可移植重建。
