# Phase 2C 新参考审核队列

状态：AWAITING_INDEPENDENT_REFERENCE_REVIEW。7个线索、6个可构建草稿、0个已批准参考。题面未冻结，A/B未运行。组织者没有填写 proposed_reference，也没有把 Harness 交给参考审核过程。

| ID | 分组/事件 | 来源及范围 | 具体审核问题 | 状态 |
|---|---|---|---|---|
| h001 | g001 / VASP9655434 | CO* -> C*+O*；见 intake.json 中逐来源哈希/指针/行号 | Only mutable historical summary locally located; original9655434 stdout not located. Confirm any bounded label against this provenance before inclusion.；请独立给出四字段 expected 或排除。 | pending |
| h002 | g002 / VFA9710404_diagnostic_classification_20260816 | CH*+H* -> CH2*；见 intake.json 中逐来源哈希/指针/行号 | Snapshot itself is a prior derived diagnostic analysis. Later accepted TS state is preserved in private provenance for scope checks, not exported into this earlier snapshot.；请独立给出四字段 expected 或排除。 | pending |
| h003 | g003 / GPU1190_path_resolution_review | C*+H* -> CH*；见 intake.json 中逐来源哈希/指针/行号 | Important interval comes from historical review resolution_reason text; neutral question quotes only interval, not later resolution diagnosis. Verify sufficient context and whether this bounded question fits existing failure schema.；请独立给出四字段 expected 或排除。 | pending |
| h004 | g004 / GPU1793_wrapper_startup | C2HO*+H* -> C2H2O*; IS-A -> INT06 migration；见 intake.json 中逐来源哈希/指针/行号 | Excluded from draft public package: later attribution exists, original causal stderr not locally located. Whole local evidence requires independent adjudication; cannot fabricate an unknown or confirmed cause.；请独立给出四字段 expected 或排除。 | pending |
| h005 | g004 / DIMER9781734 | C2HO*+H* -> C2H2O*; INT06 -> MID migration；见 intake.json 中逐来源哈希/指针/行号 | Original checkpoint/OUTCAR residuals not locally located; summary reports nonconverged force evaluations but not a complete causal mechanism. Related to development reaction family, not reaction-held-out.；请独立给出四字段 expected 或排除。 | pending |
| h006 | g005 / VASP9606916 | CHO_formyl_Oend_top adsorption；见 intake.json 中逐来源哈希/指针/行号 | Original OUTCAR/force history not locally located; raw available status folder lacks this job. Preserve secondary-source limitation and do not confirm H-transfer mechanism from distances alone.；请独立给出四字段 expected 或排除。 | pending |
| h007 | g004 / SCF9753825_dispatch | C2HO*+H* -> C2H2O*; migration electronic recovery; exact segment requires confirmation；见 intake.json 中逐来源哈希/指针/行号 | Original scheduler query and MPI probe files not locally located; exact lineage/segment needs reviewer confirmation. If same calculation as another selected case, merge or exclude before freeze.；请独立给出四字段 expected 或排除。 | pending |

h004不在草稿包。g004关联原开发反应，且h007谱系未确认，不能将其计为独立反应泛化证据。至少两个confirmed、三类参考状态覆盖及所有科学断言均等待独立审核，当前不能宣称达标。
