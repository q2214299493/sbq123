# Session Continuity Summary

更新时间：2026-06-11 21:25 CST

## 2026-06-28 Authoritative Durable Update

This block supersedes older continuation instructions below. The source of truth is `C:\Users\86177\Desktop\work`, not chat history or ordinary `.codex` memory.

- New threads read `AGENTS.md`, `tasks/current_task.md`, the relevant part of `docs/02_CURRENT_STATE.md`, and the owning module README.
- Use only `sunboquan-codex`; the active calculation root is `~/sbq/agent/jobs`. The old `~/sbq/Fe_agent_demo` root is obsolete.
- Before externally seeded calculations, use the `catalysis_data_retrieval` whitelist with BM25 plus semantic Top-5 ranking. General literature tools are only for explicitly requested scholarly deliverables.
- The historical 45-Fe five-layer structure labeled Fe(110) is Fe(211)-like and is quarantined. It must not seed corrected true Fe(110) work.
- Corrected true Fe(110) 3x3 slabs contain nine Fe atoms per layer, use 15 A vacuum, and fix the bottom two layers. The clean 4-8-layer campaign is complete.
- Final production thickness is not yet selected. Compare matched 5-vs-7-layer CO initial and C+O final observables; choose five layers only when relevant differences are at most 0.03 eV, otherwise choose seven. Never mix thicknesses in one reportable dataset.
- Default monitoring is a compact parsed summary. Raw SCF, force, scheduler, and geometry histories are shown only when explicitly requested or needed for a bounded diagnosis.
- Store only durable decisions, scientific boundaries, and stable preferences in memory. Do not add failed-task logs, transient scheduler states, per-step force/energy histories, or full chats unless a reusable lesson is explicitly promoted.

## Current Goal
- 搭建并持续使用一个基于 Codex 的 VASP 计算催化智能体，服务课题一的批量计算。
- 当前主要能力包括：吸附能工作流、NEB/CI-NEB 工作流、VTST DIMER 工作流、任务跟踪、结构审核、结果汇报。
- 以后继续本项目时，优先读取本记忆文件和 `$vasp-catalysis-workflow` skill；skill 中已有的通用流程不要在记忆里重复展开。

## Latest User Instructions
- 已要求把 VASP 催化工作流固化成 skill，每次使用时调用。
- 已特别要求：生成结构和参数前要参考已有文献/可靠资料，不能只机械套用历史模板。
- 最新第一要义：后续所有吸附能、NEB、DIMER、过渡态和催化工作流，不能每次凭空新建结构。必须把“文献调研 + 已跑通结构/参数 + 上次失败经验”结合起来，优先在已验证结构基础上做最小、化学合理的修改；每次失败都要总结成下一次的禁止重复项，再提交前说明修改内容和原因。
- 已要求修正 skill/记忆中的乱码，并把最新上下文再存一次；skill 已有内容不用重复存。
- 最新补充：以后凡是吸附能、NEB、DIMER、过渡态路径或新催化体系任务，必须先调用/参考合适的文献类 skills。可选 skill 包括：`nature-academic-search`、`nature-reader`、`academic-research-suite`、`literature-reviewer-skill`、`chem-literature-workflow`。默认先用 `nature-academic-search` 找权威来源；拿到关键 DOI/PDF/HTML 后用 `nature-reader` 精读；再用 `chem-literature-workflow` 或 `academic-research-suite` 转成计算结构与参数方案。检索多篇权威文献或可靠 VTST/VASP 资料，先弄清结构演化、过渡态形貌、吸附位点、键长范围和 INCAR/VTST 参数依据，再生成结构、给用户审核、最后提交。

## Stable User Preferences
- 后续只使用新服务器 `sunboquan-codex`，不要再查看旧服务器，除非用户明确要求。
- 远程命令必须稳定：使用 `cd ~/sbq/Fe_agent_demo`，不要让本机 PowerShell 展开远程 `$HOME`。
- 避免复杂远程 heredoc、复杂 `sed` 引号、超长一行命令；优先本地生成脚本/文件，`scp` 上传，再执行短远程命令。
- 不要在本机 PowerShell 里直接嵌套复杂远程 `awk`/`sed` 脚本来解析 VASP 输出；容易被 PowerShell 引号/反斜杠破坏，输出不可信。需要解析力、几何、OSZICAR 趋势时，优先把小文件 `scp` 到本地临时目录后用 Python 脚本解析，或上传独立脚本到远程再短命令执行。
- 本机 PowerShell 兼容性注意：不要假设 `New-Item -LiteralPath` 可用；创建本地目录用 `New-Item -ItemType Directory -Force -Path ...` 或 .NET `Directory.CreateDirectory(...)`。
- 吸附能、共吸附、普通吸附态端点优化（包括 Fe(110) 上 B-like molecular CO 这类 NEB 端点 relax）默认使用用户给定的 `INCAR-basic` 模板：`PREC=A`, `ENCUT=400 eV`, `NELMIN=5`, `LREAL=AUTO`, `ALGO=Fast`, `EDIFF=1E-5`, `ISMEAR=0`, `SIGMA=0.5`, `ISPIN=2`, 按元素计数生成 `MAGMOM`, `ICHARG=2`, `EDIFFG=-0.02`, `NSW=300`, `IBRION=2`, `POTIM=0.2`, `ISIF=2`, `PSTRESS=0`, `LCHARG=.FALSE.`, `LWAVE=F`。除非先说明理由并得到用户确认，不要私自换成其他 INCAR。
- `MAGMOM` 必须根据当前 `POSCAR` 的元素顺序和原子数动态生成，不能写死。Fe 默认 `2.2`，C/O/H 等吸附原子默认 `0.0`；展开后的磁矩数量必须等于总原子数，且必须按元素顺序逐段写，不能因为相邻元素磁矩同为 `0.0` 就合并。例如 Fe C O = 45 1 1 必须写 `45*2.2 1*0.0 1*0.0`，不能写成 `45*2.2 2*0.0`。
- 审核结构、报告、总结优先留在本地：
  - 结构审核：`C:\Users\86177\Desktop\结构`
  - 报告：`C:\Users\86177\Desktop\agent\reports`
- 提交前要汇报结构与参数依据；用户审核通过后再提交。

## Decisions Made
- 新 skill 已创建并验证通过：
  - 主 skill：`C:\Users\86177\.codex\skills\vasp-catalysis-workflow`
  - 项目备份：`C:\Users\86177\Desktop\agent\skills\vasp-catalysis-workflow`
  - 验证命令结果：`Skill is valid!`
- skill 内包含：
  - `SKILL.md`
  - `references/adsorption.md`
  - `references/neb.md`
  - `references/dimer.md`
  - `references/diagnostics.md`
- 以后做吸附能、NEB、DIMER、VASP 任务状态、结构审核时，先读该 skill 的相关 reference。
- skill 已记录“Literature-First Gate”：新结构、新路径、新参数需要先查文献/VTST/VASP 资料，并按任务选择 `nature-academic-search`、`nature-reader`、`academic-research-suite`、`literature-reviewer-skill`、`chem-literature-workflow`，再结合本地成功案例落地。

## Files And Artifacts
- 当前工作区：`C:\Users\86177\Desktop\agent`
- 当前记忆文件：`C:\Users\86177\.codex\memory\sessions\active-session.md`
- 服务器：
  - SSH alias: `sunboquan-codex`
  - Host: `10.68.0.102`
  - User: `nsgkn_chengdj3`
  - Remote root: `~/sbq/Fe_agent_demo`
- 提交脚本：
  - 普通吸附/结构优化：`~/vasp541std.lsf`
  - NEB/DIMER/VTST：`~/vasp541vtst.lsf`
- 当前 DIMER 运行目录：
  - `~/sbq/Fe_agent_demo/review_jobs/dimer/fe110_co_dissociation_dimer_from_lying170_direct_stable_001`

## Completed Work
- 吸附能工作流已跑通过 CO/Fe110 和 C+O 共吸附。
- 已知结果：
  - Clean Fe110 TOTEN = `-342.34097090 eV`
  - Gas CO TOTEN = `-14.79786411 eV`
  - CO bridge TOTEN = `-358.88223466 eV`, Eads = `-1.743400 eV`
  - CO hollow TOTEN = `-358.87804601 eV`, Eads = `-1.739211 eV`
  - CO top TOTEN = `-358.87781430 eV`, Eads = `-1.738979 eV`
  - C+O coads TOTEN = `-357.55295560 eV`
- NEB 路径已有分段跑通：
  - D1 job `9428372`: `DONE`, reached required accuracy
  - D2 job `9428373`: `DONE`, reached required accuracy
- Jmol/结构查看：
  - NEB 路径 movie 已生成并打开过：`C:\Users\86177\Desktop\结构\neb_path_movie.xyz`
  - DIMER 初始结构/模式文件曾导出到本地结构目录。

## Current Running Jobs
- 当前仍在跑的任务：
  - DIMER job `9430763`
  - 状态最近一次查询：`RUN`
  - 目录：`~/sbq/Fe_agent_demo/review_jobs/dimer/fe110_co_dissociation_dimer_from_lying170_direct_stable_001`
- 最近查询状态：
  - 当前只有 DIMER `9430763` 在队列中运行。
  - `DIMCAR` 仍只有表头，说明尚未进入有效 DIMER step。
  - `OSZICAR` 已写到 `CGA: 30` 左右，能量逐步回到约 `-354.45 eV`，但还未完成第一轮电子自洽。
- 新提交并正在运行的 NEB 加密任务：
  - NEB job `9430987`
  - 状态最近一次查询：`RUN`
  - 目录：`~/sbq/Fe_agent_demo/review_jobs/neb/fe110_co_dissociation_literature_path_review_001/segment_D_retry_split_001/segment_D1_refined_4img_001`
  - 目的：重新加密 `lying170 -> half245` 段，避免原 D1 单 image 优化后 C-O 跑过头。
  - 01-04 中间 images 已开始写 `OSZICAR/OUTCAR`，说明并行启动正常。

## DIMER Recent Attempts
- 旧 DIMER `9429911`：
  - 已停止，状态 `EXIT`
  - 问题：`ALGO=Fast`、电子步 RMM 大幅波动，`DIMCAR` 只走到第 1 步。
  - 归档：`failed_attempt_9429911_fast_rmm_unstable_20260611`
- 稳定版 DIMER `9430275`：
  - 已停止，状态 `EXIT`
  - 问题：`ALGO=Normal` 后仍然长时间停在电子步，未进入有效 DIMER step。
  - 归档：`failed_attempt_9430275_normal_dav_no_dimer_step_20260611`
- D1_01 文献引导 DIMER `9430611`：
  - 已停止，状态 `EXIT`
  - 问题：使用 `C-O≈2.07 A` 的 D1_01 构型，电子/偶极不稳定。
  - 归档：`failed_attempt_9430611_litguided_direct_dimer_scf_unstable_20260611`
- D1_01 预收敛 `9430627`：
  - 已停止，状态 `EXIT`
  - 问题：出现巨大 dipole/added-field 项，电子步不稳定。
  - 归档：`failed_attempt_9430627_prescf_D1_01_electronic_dipole_unstable_20260611`
- lying170 预收敛 `9430644`：
  - 已停止，状态 `EXIT`
  - 问题：电子步停滞，未形成有效 WAVECAR/CHGCAR。
  - 归档：`failed_attempt_9430644_lying170_prescf_stalled_20260611`
- 当前 DIMER `9430763`：
  - 结构：lying170, `C-O=1.700 A`, `C-Fe=1.495 A`, `O-Fe=1.937 A`
  - 参数：参考成功 NEB 电子参数，直接 DIMER：
    - `ALGO=All`
    - `EDIFF=1E-5`
    - `ISMEAR=1`
    - `SIGMA=0.20`
    - 小 mixing
    - `LDIPOL=.FALSE.`
    - 保留 `ICHAIN=2`, `IBRION=3`, `POTIM=0`, `IOPT=2`

## Open Tasks
- 继续跟踪 DIMER job `9430763` 是否能进入 `DIMCAR` 第一个有效 DIMER step。
- 跟踪 NEB job `9430977` 是否开始 RUN；重点检查 01/02/03 三个中间 image 的 C-O 是否仍按 1.70 -> 2.457 A 连续变化，不再跑到 C-O 大于终点。
- 注意：NEB job `9430977` 是 3 inserted images 版本，已 `DONE` 但实际失败，原因不是结构，而是 VASP 并行：`M_divide: can not subdivide 32 nodes by 3`。已归档为 `failed_attempt_9430977_D1_refined_3img_parallel_mdivide_20260611`。
- 后续跟踪 NEB job `9430987`：这是 4 inserted images 版本，`IMAGES=4` 可被 32 核整除。重点检查 01/02/03/04 的 C-O 是否保持连续。
- 若 `9430763` 仍卡电子步：
  - 先查文献/VTST/VASP 资料再调整参数；
  - 优先考虑是否需要更合适的 TS-like 初猜或改 `MODECAR`；
  - 不要盲目继续提交参数变体。
- 后续若用户要求 NEB 下一步：
  - 已发现原 D1 单 image 结果有问题：D1_01 relaxed C-O = `3.030 A`，超过 D1 终点 half245 的 `2.457 A`，说明原 D1 中间 image 跑过头。
  - 已创建并提交 D1 refined 4-image 路径：
    - 00 C-O=`1.700 A`
    - 01 C-O=`1.848 A`
    - 02 C-O=`1.999 A`
    - 03 C-O=`2.150 A`
    - 04 C-O=`2.303 A`
    - 05 C-O=`2.457 A`
  - 本地审核文件：
    - `C:\Users\86177\Desktop\结构\neb_D1_refined_4img_001\neb_D1_refined_4img_001.xyz`
    - `C:\Users\86177\Desktop\结构\neb_D1_refined_4img_001\review_geometry.txt`

## 2026-06-15 B 态按模板重跑
- 用户纠正：吸附能、共吸附、普通吸附态端点优化必须使用用户给定的 `INCAR-basic` 模板，`MAGMOM` 必须按 `POSCAR` 元素顺序和原子数逐段生成，不能合并相邻 `0.0` 元素段。
- 旧 B 态优化 `9435171`：
  - 调度状态 `DONE`，但未出现 `reached required accuracy`。
  - `vasp.out` 末尾为 `ZBRENT: fatal error in bracketing`，不能作为正式 B 态。
  - 最终 `CONTCAR` 几何可作为续跑起点：C-O 约 `1.213 A`，C-Fe 约 `1.813 A`，O-Fe 约 `2.314 A`，无明显撞 Fe/脱附。
- 新建并提交 B 态模板重跑：
  - 目录：`~/sbq/Fe_agent_demo/review_jobs/neb/fe110_co_dissociation_literature_ABCD_001/B_state_relax_002_templateK_from_D_001`
  - job id：`9435904`
  - 提交状态：`PEND`
  - `POSCAR`：来自 `B_state_relax_001/CONTCAR`
  - `INCAR` 和 `KPOINTS`：直接复制已收敛末态 `review_jobs/adsorption/fe110_c_o_coads_sunboquan_001`
  - KPOINTS：Gamma `5 3 1`
  - `MAGMOM = 45*2.2 1*0.0 1*0.0`
  - 目的：用与 D 末态一致的 K 点和 INCAR 模板把 B-like molecular CO 端点真正优化收敛后，再进入 B->D NEB。
- 用户确认后续使用当前真实存在目录：`~/sbq/agent/jobs`，不要再使用不存在的 `~/sbq/Fe_agent_demo` 作为本次任务根目录。
- `9435904` 后续检查：
  - LSF 状态 `DONE`，但未收敛；`OUTCAR` 无 `reached required accuracy`。
  - `vasp.out` 末尾为 `forrtl: error (69): process interrupted (SIGINT)`。
  - 已走到第 60 个离子步，力约降到 `0.498 eV/A`，但离 `EDIFFG=-0.02` 仍远。
  - 最终几何：C-O 约 `1.189 A`，C-Fe 约 `1.821 A`，O-Fe 约 `2.802 A`，O-Fe 偏远但无短接触。
- 已创建并提交续跑：
  - 目录：`~/sbq/agent/jobs/neb/fe110_co_dissociation_literature_ABCD_001/B_state_relax_003_continue_from_002`
  - job id：`9436878`
  - 提交状态：`PEND`
  - `POSCAR`：来自 `B_state_relax_002_templateK_from_D_001/CONTCAR`
  - 沿用 `INCAR-basic`、KPOINTS Gamma `5 3 1`、`MAGMOM = 45*2.2 1*0.0 1*0.0`。
  - 后续重点：看 O-Fe 是否从约 `2.80 A` 回到更合理吸附范围，并继续检查电子步/力趋势。
- `9436878` 结果：
  - LSF 状态 `DONE`，但 `OUTCAR` 无 `reached required accuracy`。
  - `vasp.out` 末尾为 `ZBRENT: fatal error in bracketing`。
  - 已到第 268 个离子步，力平台约 `0.538 eV/A`，未向 `EDIFFG=-0.02` 接近。
  - 最终几何：C-O 约 `1.178 A`，C-Fe 约 `2.622 A`，O-Fe 约 `3.355 A`，说明 CO 分子态仍在但已经明显远离表面/弱吸附。
  - 不要使用 `B_state_relax_003_continue_from_002/CONTCAR` 作为 NEB 初态；也不要继续沿这个已脱附趋势直接续跑。
- 用户要求：初态结构可直接用已有/网上合理结构，重点是贴近 NEB 初态和末态、能用于过渡态路径，不要一直从失败脱附结构续跑。
- 新建并提交贴近 NEB 初态的 B 态预优化：
  - 目录：`~/sbq/agent/jobs/neb/fe110_co_dissociation_literature_ABCD_001/B_state_relax_004_neb_initial_like_001`
  - job id：`9438732`
  - 提交后状态：`RUN` on `32*gknew054`
  - `POSCAR` 来源：`~/sbq/agent/jobs/neb/fe110_co_dissociation_B_localmin_to_TS_4img_001/00/POSCAR`
  - 初始几何：C-O `1.425 A`，C-Fe `1.853 A`，O-Fe `1.924 A`，贴表面且接近旧 NEB B->C 初态。
  - `INCAR/KPOINTS/POTCAR`：复制 D 末态 `~/sbq/agent/jobs/adsorption/fe110_c_o_coads_sunboquan_001`，KPOINTS Gamma `5 3 1`，`MAGMOM = 45*2.2 1*0.0 1*0.0`。
  - 后续检查重点：不要让 CO 回到脱附/弱吸附；若收敛后 C-Fe/O-Fe 仍合理，再作为 B->D NEB 初态候选。

## 2026-06-16 稳定 molecular CO 初态端点重建
- 用户澄清：当前只是需要一个能作为完整 CO 解离 NEB 反应物端点的初态结构，不需要把文献中间态强行普通优化成局部极小。
- 诊断结论：
  - `B_state_relax_004_neb_initial_like_001` job `9438732` 未收敛，无 `reached required accuracy`，末尾 `ZBRENT: fatal error in bracketing`。
  - 几何从 C-O `1.425 A`, C-Fe `1.853 A`, O-Fe `1.924 A` 回缩为 C-O `1.179 A`, C-Fe `1.787 A`, O-Fe `2.965 A`。
  - 因此，倾斜/拉伸 CO 只作为 NEB 中间 image，不作为全优化初态端点。
- 新策略：
  - 采用已验证稳定 molecular CO/Fe(110) 吸附态作为初态端点。
  - 当前目录 `~/sbq/agent/jobs/afe110` 下 `Fe110_CO_bridge`, `Fe110_CO_hollow`, `Fe110_CO_top` 均有已收敛旧结果；其中 bridge 旧 TOTEN 最低，为 `-358.88223466 eV`。
  - 旧 CO 计算 KPOINTS 为 `3 3 1` 且 `MAGMOM` 不符合当前规则，因此重新用 D 末态的 INCAR/KPOINTS/POTCAR 优化。
- 已提交：
  - job id：`9440573`
  - 目录：`~/sbq/agent/jobs/neb/fe110_co_dissociation_literature_ABCD_001/A_state_CO_bridge_initial_relax_001`
  - POSCAR：`~/sbq/agent/jobs/afe110/Fe110_CO_bridge/CONTCAR`
  - INCAR/KPOINTS/POTCAR：复制自 `~/sbq/agent/jobs/adsorption/fe110_c_o_coads_sunboquan_001`
  - KPOINTS：Gamma `5 3 1`
  - MAGMOM：`45*2.2 1*0.0 1*0.0`
  - 初始几何：C-O `1.184 A`, C-Fe `1.800 A`, O-Fe `2.977 A`
  - 本地审核目录：`C:\Users\86177\Desktop\结构\A_state_CO_bridge_initial_relax_001_job9440573`
- 后续：
  - 跟踪 `9440573` 是否收敛、力是否下降、电子步是否正常、最终结构是否仍为合理分子 CO 吸附。
  - 收敛后用该 `CONTCAR` 做完整 NEB 初态；末态继续用已收敛 C+O coads。
  - NEB 提交前必须执行并汇报 `dist.pl POSCARis POSCARfs`、生成非纯线性 ABCD 几何表、运行 `nebmovie.pl 0` 并保存本地 movie/xyz 给用户审核。
- `9440573` 已完成：
  - LSF：`DONE successfully`
  - VASP：`OUTCAR` 有 `reached required accuracy`
  - 离子步：18
  - 最终 TOTEN：`-358.72301094 eV`
  - 最终几何：C-O `1.1840 A`，C-Fe `1.8020 A`，O-Fe `2.9793 A`
  - 力：全原子最大力 `0.5473 eV/A` 在固定 Fe26；可动原子最大力 `0.0169 eV/A`，C `0.0149 eV/A`，O `0.0146 eV/A`
  - 电子步：后期基本 5 个电子步完成，无 `BRMIX/ZBRENT/forrtl/fatal`
  - 本地最终结构：`C:\Users\86177\Desktop\结构\A_state_CO_bridge_initial_relax_001_job9440573\CONTCAR_converged_A_initial`
  - 判断：该结构可作为完整 CO 解离 NEB 初态端点，下一步进入 NEB 预提交检查流程。

## 2026-06-16 完整 Abridge -> D 文献路径 NEB 已提交
- 用户要求：用已收敛初态和已有末态提交 NEB，中间态按文献自己拟合合理结构，不走直接插值。
- NEB 目录：
  - `~/sbq/agent/jobs/neb/fe110_co_dissociation_literature_ABCD_001/neb_Abridge_to_D_literature_ABCD_16img_001`
- job：
  - `9441773`
  - 提交后状态：`PEND`
- 端点：
  - 初态：job `9440573` 收敛的 molecular CO bridge 初态 `A_state_CO_bridge_initial_relax_001/CONTCAR`
  - 末态：已收敛 C+O coads `~/sbq/agent/jobs/adsorption/fe110_c_o_coads_sunboquan_001/CONTCAR`
- 路径：
  - 使用 `IMAGES=16`，目录 `00-17`，32 核可整除 16。
  - 非直接初末态插值；C/O 按 A/B/C/D 化学 waypoints 走：
    - molecular CO
    - reoriented/tilted CO
    - lying CO, C-O `1.45-1.70 A`
    - TS-like C, C-O `~2.12 A`
    - post-TS half dissociated
    - C*+O* coads
  - 预检查几何表显示所有 image 最小非 C-O 接触均大于约 `1.5 A`，无 <1 A 撞原子。
- 强制预检查已做：
  - `dist.pl POSCARis POSCARfs` 输出：`3.6655995342661`
  - `nebmovie.pl 0` 成功，生成远程 `movie`
  - 本地审核目录：`C:\Users\86177\Desktop\结构\neb_Abridge_to_D_literature_ABCD_16img_001_precheck`
  - 本地文件：`nebmovie0_movie`、`initial_path_manual_standard.xyz`、`geometry_table.txt`、`dist_POSCARis_POSCARfs.txt`、`INCAR`、`KPOINTS`
- INCAR：
  - `IMAGES=16`, `LCLIMB=.FALSE.`, `IBRION=3`, `POTIM=0`, `ICHAIN=0`, `IOPT=7`, `SPRING=-5`
  - `EDIFF=1E-5`, `EDIFFG=-0.05`
  - `ALGO=All`, `ISMEAR=1`, `SIGMA=0.20`, `LREAL=.FALSE.`, `ISYM=0`, `LASPH=.TRUE.`
  - `KPAR=1`, `NPAR=2`, `MAGMOM=45*2.2 1*0.0 1*0.0`
  - KPOINTS Gamma `5 3 1`
- 后续：
  - 当前如果用户问进展，先查 `bjobs -a 9441773`。
  - RUN 后看是否有并行划分错误、输入错误、电子步不收敛；重点跟踪每个 image 的 `OSZICAR`、力趋势、C-O/C-Fe/O-Fe。
  - 完成后必须 `nebmovie.pl 1`，保存本地 movie/xyz，再分析能量曲线、最高 image，并决定 CI-NEB/DIMER。

## Constraints And Safety
- 不要再用旧服务器。
- 不要用 `bsub < script.lsf`；此集群使用 `bsub script.lsf`。
- 不要把审核材料长期放远程；远程放计算输入/输出，本地放结构审核与报告。
- 提交前确认 `POSCAR/INCAR/KPOINTS/POTCAR/LSF` 和元素顺序、`MAGMOM` 一致。
- 对新体系/新参数必须调用文献，不凭空猜；尤其 NEB/DIMER 不能只插值或只调 INCAR，要先判断文献中相似反应的断键/成键顺序、TS-like 结构、合理键长与表面吸附距离。

## Uncertainties
- DIMER `9430763` 是否会成功进入 DIMER step 尚未确定。
- 当前 DIMER 的 `MODECAR` 方向是否足够好，仍需等 `DIMCAR` 或 `dimmode` 检查确认。
- 如果 DIMER 继续失败，可能需要从 NEB 最高能附近重新设计 TS-like 结构，而不是只调 INCAR。

## Next Best Step
- 用户问任务状态时：读取本记忆和 `$vasp-catalysis-workflow` 的 diagnostics，再查 `bjobs -a 9430763`、`OSZICAR`、`DIMCAR`、`OUTCAR`。
- 用户要求继续 DIMER 时：先查文献/资料，再基于 `9430763` 的最新失败或进展调整。

## 2026-06-14 DIMER 最新记录
- 旧 DIMER job `9433590` 持续高力振荡，`DIMCAR` 到第 9 步后 force 仍在约 `2-4 eV/A` 区间跳动，最新 `OUTCAR` 最大力约 `2.6 eV/A`，未见明显 BRMIX/ZBRENT/fatal 报错。
- 已停止旧任务并归档：
  - `bkill 9433590`
  - 归档目录：`~/sbq/Fe_agent_demo/review_jobs/dimer/failed_attempt_9433590_dimer_mode_oscillation_20260614`
- 新建保守 DIMER 重启：
  - 远程目录：`~/sbq/Fe_agent_demo/review_jobs/dimer/fe110_co_dissociation_dimer_COmode_damped_001`
  - job id：`9434125`
  - 提交时状态：`PEND`
  - 结构来源：旧振荡 DIMER 的 `CONTCAR`
  - 几何：`C-O = 2.3324 A`
  - `MODECAR`：只保留 C/O 沿 C-O 断键方向反向运动，Fe 初始模式置零。
  - `INCAR`：`IOPT=1`, `DRotMax=0.20`, `DFNMax=0.20`, `DFNMin=0.005`，其余沿用稳定磁性/电子设置。
  - 本地审核文件：`C:\Users\86177\Desktop\结构\dimer_COmode_damped_001`
- 后续状态查询优先看新 DIMER `9434125` 和 NEB `9433782`，不要继续把 `9433590` 当作有效运行任务。

### 2026-06-14 DIMER COmode 失败补充
- 新 DIMER job `9434125` 运行后 force 快速从几十 eV/A 增长到数百 eV/A，最高观察到约 `691 eV/A`，判断为结构/模式被推爆。
- 已停止并归档：
  - `bkill 9434125`
  - `~/sbq/Fe_agent_demo/review_jobs/dimer/failed_attempt_9434125_COmode_damped_force_blowup_20260614`
- 经验：C/O-only 反向断键 `MODECAR` 不是好方向，后续不要重复。下一轮 DIMER 应基于更稳定的 NEB 高能 image 或文献 TS-like mode，并先用 `dimmode.pl`/结构检查确认模式合理。

## 2026-06-14 NEB 文献引导重建
- 旧 NEB `9433782` 诊断为路径过冲/回缩：
  - `image 01` 从 C-O `1.824 A` 退到 `1.424 A`；
  - `image 02` 从 C-O `1.948 A` 冲到 `2.437 A`；
  - 判断不是电子错误，而是路径/endpoint 不合理。
- 已停止并归档：
  - `bkill 9433782`
  - `~/sbq/Fe_agent_demo/review_jobs/neb/failed_attempt_9433782_D1a_2img_path_overshoot_20260614`
- 新 NEB：
  - 目录：`~/sbq/Fe_agent_demo/review_jobs/neb/fe110_co_dissociation_lit_TS_softFe_4img_001`
  - job id：`9434479`
  - 本地审核：`C:\Users\86177\Desktop\结构\neb_lit_TS_softFe_4img_001`
- 依据和修改：
  - 参考 Fe(110) CO 解离文献中 TS 附近 C-O 约 `2.04-2.15 A`、Fe-C 约 `1.80-1.85 A`、Fe-O 约 `1.91-2.04 A`；
  - 新路径终点改为 C-O `2.124 A`、C-Fe `1.805 A`、O-Fe `1.899 A`，避免旧 endpoint 的 Fe-C/Fe-O 过短；
  - `IMAGES=4`, `LCLIMB=.FALSE.`, `IOPT=7`, `EDIFF=1E-5`, `EDIFFG=-0.05`。

## 2026-06-15 完全按文献路径重置 NEB
- 用户要求：完全按文献路径复刻，包括初态调整、末态确定和插值路径。用户特别指出：不能直接线性插值，因为 CO 可能穿过 Fe 或走不合理轨迹；应先手动构造合理中间态，使 CO 从 on-top 倾斜到 hollow，C-O 拉长到约 `1.5-1.8 A`，C 往表面靠近，O 横向移到 Fe 位附近，再做 NEB；ASE/IDPP 可作为比简单线性插值更稳的参考方法。
- 文献路径定义为 `A on-top CO -> B hollow/tilted molecular CO -> C saddle/TS -> D C*+O* coadsorbed`。
- 关键纠错：
  - `C-O≈2.12 A` 的结构是 TS-like C 点，不是最终 D 态，不能再当末态。
  - 之前 `9434583` 属于 `B-like -> TS-like waypoint` 探索段，不是完整 CO 解离 NEB。
  - `CO_top` 和 `CO_hollow` 两个吸附能优化结果几何几乎相同，均为近竖直 CO，不足以作为文献 B 态；B-like 初猜应使用旧 NEB 自然回缩出的倾斜分子态。
- 已停止并归档错误端点任务：
  - `bkill 9434583`
  - `~/sbq/Fe_agent_demo/review_jobs/neb/failed_attempt_9434583_endpoint_was_TS_not_D_20260614`
- 当前第一步任务：单独优化 B-like 初态。
  - 目录：`~/sbq/Fe_agent_demo/review_jobs/neb/fe110_co_dissociation_literature_ABCD_001/B_state_relax_001`
  - job id：`9435171`
  - 最近状态：`RUN` on `32*gknew022`
  - 当前进度：`OSZICAR` 到 `CGA: 49`
  - 最新能量约 `TOTEN = -357.67319003 eV`
  - 尚未收敛；`CONTCAR` 仍为空。
  - 暂无 `BRMIX/ZBRENT/fatal/error`。
- B-like 初猜几何：
  - C-Fe 最近约 `1.890 A`
  - O-Fe 最近约 `2.302 A`
  - 未见明显撞 Fe 或脱附。
- B 态优化输入由本地脚本生成：
  - `C:\Users\86177\Desktop\agent\scripts\setup_literature_abcd_b_relax.py`
  - 该脚本固化规则：B 态先优化，D 态用已收敛 C+O 共吸附，TS-like 不作末态。
- 下一步：
  - 等 `9435171` 收敛后，用其 `CONTCAR` 作为正式 B 初态。
  - 用 `review_jobs/adsorption/fe110_c_o_coads_sunboquan_001/CONTCAR` 作为正式 D 末态。
  - 再生成完整 `B -> D` non-climbing NEB；路径应包含倾斜/拉伸 CO、TS-like C 点、post-TS 到 C+O 的连续中间态，不要纯线性插值。

## 2026-06-15 NEB Movie 检查门槛
- 用户要求将 `nebmovie` 纳入标准 NEB 流程：
  - 新 NEB 提交前必须运行 `nebmovie.pl 0` 审核初始路径。
  - NEB 结束后必须运行 `nebmovie.pl 1` 审核优化后的路径。
- 已同步到 skill：
  - `C:\Users\86177\.codex\skills\vasp-catalysis-workflow\references\neb.md`
- 新流程要求：
  - 未做 `nebmovie.pl 0` 初始路径 movie 审核，不提交 NEB。
  - 未做 `nebmovie.pl 1` 优化后路径 movie 审核，不解释最终 NEB 结果。
  - VTST 原生 `nebmovie.pl` 通常生成名为 `movie` 的文件；保存原始文件，同时按需转成标准 Jmol `.xyz`。
- 已补跑旧目录的 `nebmovie.pl 0`：
  - 远程目录：`~/sbq/Fe_agent_demo/review_jobs/neb/fe110_co_dissociation_B_localmin_to_TS_4img_001`
  - 远程产物：`movie`
  - 本地原生输出：`C:\Users\86177\Desktop\结构\neb_B_localmin_to_TS_4img_001_nebmovie0\nebmovie0_initial_path.xyz`
  - 本地标准 Jmol XYZ：`C:\Users\86177\Desktop\结构\neb_B_localmin_to_TS_4img_001_nebmovie0\initial_path_standard_xyz_for_jmol.xyz`
- 用户补充：新 NEB 生成/提交前还必须运行并汇报 `dist.pl POSCARis POSCARfs`，保存输出；它用于估算 image 数和检查端点距离，但不能替代文献路径设计、非纯线性中间态、几何表和 `nebmovie.pl 0` 审核。

## 2026-06-18 DFT-to-Kinetics / KMC / Reactor Skill Roadmap
- 已按用户所发 MatClaw 文章和后续需求补齐本地 Codex skills，安装位置均为 `C:\Users\86177\.codex\skills`，并全部通过官方 `quick_validate.py`。
- 文章里直接对应、已安装的必要 skill：
  - `thermal-corrections`: 热力学校正，DFT 总能转自由能。
  - `imaginary-freq-correction`: TS 虚频检查和速率常数前处理。
  - `reaction-kinetics`: 非覆盖度自洽 MKM、TOF、选择性、DRC。
  - `reaction-pathway`: 反应网络和自由能/势垒表组织。
  - `neb-transition-state`: NEB/CI-NEB/DIMER 的 TS 候选选择与验证。
  - `adsorption-isotherm`: 吸附等温线和覆盖度估计。
  - `gcmc-simulation`: GCMC 吸附模拟，服务覆盖度/吸附输入。
  - `scaling-relations`: scaling/BEP 关系和筛选加速。
  - `d-band-center`: d-band center 催化描述符。
  - `batch-screening`: 批量筛选计算。
  - `screening-workflow`: 催化筛选总体流程。
  - `free-energy-calculation`: 反应自由能/活化自由能。
  - `convergence-automation`: 参数收敛自动化。
- 文章没有明确覆盖、但用户后续“覆盖度自洽 MKM、表面反应 KMC、反应器模拟”必需的补充 skill：
  - `coverage-self-consistent-mkm`: 覆盖度依赖能量/势垒的自洽 MKM。
  - `surface-reaction-kmc`: 表面反应 kinetic Monte Carlo，不等同于 GCMC。
  - `reactor-simulation-workflow`: batch/CSTR/PFR/packed-bed 等反应器模型。
  - `kinetic-data-schema`: 统一 DFT-to-kinetics 数据格式、单位、来源。
  - `sensitivity-uncertainty-analysis`: 敏感性、DRC、不确定性传播，指导下一轮计算。
- 后续工作流应按以下顺序组织：
  - 文献依据 -> VASP 结构/输入 -> 吸附能/NEB/DIMER/频率 -> 热校正/自由能 -> 反应网络 -> 非覆盖度自洽 MKM -> 覆盖度自洽 MKM -> 表面反应 KMC -> 反应器模拟 -> 敏感性/不确定性分析。

## 2026-06-19 NEB 9441773 Paused
- 用户判断当前完整 Abridge -> D NEB 路径仍不合理，要求暂停。
- 已执行：`bstop 9441773`。
- 确认状态：`USUSP`。
- 暂停原因：
  - 前段 image 01-08 基本回缩为短 C-O 分子态；
  - image 09 C-O 约 `1.58 A`，image 10 C-O 约 `2.30 A`；
  - `09 -> 10` 仍有明显路径断层/kink，TS 区域过度集中；
  - 最大普通 atomic force 仍约 `1.5 eV/A`，未接近收敛。
- 后续策略：
  - 不要直接恢复该 NEB 当作正式路径。
  - 后续若继续 CO 解离 NEB，应基于文献 A/B/C/D 关键构型重建 `08-11` 或分段路径，重点让 C-O、C-Fe、O-Fe 和 C/O 横向迁移连续。
  - 新路径提交前仍必须执行 `dist.pl POSCARis POSCARfs`、几何表、`nebmovie.pl 0`，并本地审核。

## 2026-06-19 New 5-Image Plain NEB Restart
- 用户给出 5-image 几何目标并要求按“三阶段策略”推进：
  - 阶段 1：普通 NEB，`IMAGES=5`, `LCLIMB=.FALSE.`, `ICHAIN=0`, `IOPT=3`
  - 阶段 2：路径连续且最高 image 合理后，CI-NEB，`LCLIMB=.TRUE.`, `ICHAIN=0`, `IOPT=1`
  - 阶段 3：如果 TS 区域仍集中，再增加关键路径分辨率。
- 生成的新路径几何：
  - C-O: `1.184 -> 1.201 -> 1.312 -> 1.648 -> 2.061 -> 2.576 -> 2.955 A`
  - image 04 为 lying-down TS-like 几何，C-Fe `1.770 A`, O-Fe `1.951 A`。
  - `dist.pl POSCARis POSCARfs = 3.66559953373041`
  - `nebmovie.pl 0` 已完成；本地预审目录：`C:\Users\86177\Desktop\结构\neb_Abridge_to_D_user_7img_stage1_plain_001_precheck`
- 第一版普通 NEB job `9452322`：
  - 电子步不稳，第一离子步多个 image 到 `NELM=250`，image 02 DAV 大幅跳变，`Fmax ~16.4 eV/A`。
  - 已终止，状态 `EXIT`，保留目录作为失败启动记录。
- 稳定电子版普通 NEB job `9454833`：
  - 目录：`~/sbq/agent/jobs/neb/fe110_co_dissociation_literature_ABCD_001/neb_Abridge_to_D_user_7img_stage1_plain_stableelec_001`
  - 参数：保留普通 NEB 核心设置，改为 `ALGO=All`, `LREAL=.FALSE.`, `SIGMA=0.20`, `LDIPOL=.FALSE.`, 小 mixing。
  - 状态提交后：`RUN` on `30*gknew023`。

## 2026-06-19 23:35 NEB 9454833 Progress
- `9454833` remains `RUN` on `30*gknew023`; all five intermediate images completed 2 ionic steps and are in the third SCF cycle.
- Stable-electronic restart works: completed SCFs take roughly `13-26` CGA iterations, do not hit `NELM=250`, and show no true fatal electronic errors.
- Atomic max force step1 -> step2 (eV/A): 01 `2.525 -> 3.533`, 02 `6.403 -> 0.817`, 03 `5.370 -> 4.711`, 04 `3.843 -> 3.205`, 05 `3.920 -> 3.200`.
- Current geometry C-O/C-Fe/O-Fe (A): 01 `1.171/2.093/2.485`; 02 `1.205/1.839/2.505`; 03 `1.452/1.810/1.919`; 04 `2.015/1.685/1.742`; 05 `2.696/1.616/1.586`.
- Continue for now. Watch early images 01-03 for persistent molecular-basin collapse/path concentration and image05 for further O-Fe compression below `1.586 A`.

## 2026-06-20 00:30 NEB 9454833 Progress
- Job remains `RUN`; all intermediate images completed 3 ionic steps and entered the fourth SCF cycle without fatal electronic errors.
- Atomic max forces (steps 1/2/3, eV/A): 01 `2.525/3.533/3.695`, 02 `6.403/0.817/1.341`, 03 `5.370/4.711/2.496`, 04 `3.843/3.205/1.535`, 05 `3.920/3.200/3.388`.
- Geometry C-O/C-Fe/O-Fe (A): 01 `1.184/2.004/2.525`; 02 `1.189/1.834/2.479`; 03 `1.313/1.807/1.779`; 04 `2.031/1.651/1.608`; 05 `2.786/1.618/1.631`.
- Path concentration is becoming clearer: images 01-03 collapse toward molecular CO, while C-O jumps by `~0.718 A` from image03 to image04. Image04 O-Fe is compressed to `1.608 A`; no <1.55 A collision yet, but monitor closely.

## 2026-06-20 User-Package NEB Replacement
- User supplied `D:\Codex_FeCO_NEB_complete_package.zip` and requested replacement of the failing path.
- Old job `9454833` was killed (`EXIT`) and its remote directory was deleted as explicitly requested.
- New remote directory: `~/sbq/agent/jobs/neb/fe110_co_dissociation_literature_ABCD_001/neb_Abridge_to_D_user_package_adjusted_stage1_plain_001`.
- New ordinary NEB job `9455800`: `RUN` on `30*gknew061`.
- Endpoints exactly match the converged project geometries. Image04 was corrected from C-O/Fe-C/Fe-O=`2.050/1.626/2.017 A` to `2.050/1.771/2.011 A`; image05 Fe-C was corrected from `1.636` to `1.699 A` while preserving C-O=`2.551 A`.
- Final C-O path: `1.184, 1.219, 1.383, 1.652, 2.050, 2.551, 2.955 A`; all C/O-Fe contacts exceed `1.55 A`.
- Precheck passed: `dist.pl=3.66559953373041`, `nebmovie.pl 0` generated a 22747-byte movie, endpoint geometry delta is zero, and a stdlib-only geometry audit passed on the server.
- Run settings: ordinary NEB `IMAGES=5`, `LCLIMB=.FALSE.`, `ICHAIN=0`, `IOPT=3`; stable Fe SCF settings (`ALGO=All`, `LREAL=.FALSE.`, `SIGMA=0.20`, conservative mixing, no dipole field); Gamma `5 3 1`; 30 cores.
- Local review folder: `C:\Users\86177\Desktop\结构\neb_Abridge_to_D_user_package_adjusted_stage1_plain_001_precheck`.
- Monitor early for renewed image01-03 molecular collapse and a reappearing image03->04 C-O gap above `0.6-0.7 A`.

## 2026-06-21 NEB 9455800 Stopped After Path Collapse
- `9455800` reached 58 ionic steps but triggered the user's explicit stop criteria and was killed; final scheduler status `EXIT`. Outputs are retained.
- SCF remained stable (typically 12-15 CGA iterations, no fatal electronic errors), so this is not an electronic failure.
- Final C-O/C-Fe/O-Fe (A): 01 `1.196/1.931/2.843`; 02 `1.184/1.771/2.953`; 03 `1.189/1.781/2.796`; 04 `1.317/1.897/1.861`; 05 `3.018/1.682/1.758`.
- Images 01-03 collapsed to molecular CO, image04 remained only weakly activated, and image05 became fully dissociated. The image04->05 C-O gap is `~1.701 A`, so the path is invalid for CI-NEB or barrier extraction.
- Forces remained oscillatory and above `EDIFFG=-0.05`; no image reached required accuracy. No collision/desorption occurred.
- `nebmovie.pl 1` was run after stopping. Local postmortem: `C:\Users\86177\Desktop\结构\neb_9455800_stopped_58steps_postmortem`.
- Do not resume or switch this path to CI-NEB. Rebuild with several additional literature-guided images in the C-O `1.3-2.6 A` region or run a refined key-segment ordinary NEB first.

## 2026-06-21 Refined 8-Image Path Ready, Server Offline
- Local path ready: `C:\Users\86177\Desktop\work\neb_Abridge_to_D_refined_8img_constrainedFe_pre_001`.
- C-O path: `1.184, 1.250, 1.400, 1.550, 1.700, 1.850, 2.050, 2.300, 2.600, 2.955 A`; TS-like image06 Fe-C/Fe-O=`1.751/1.979 A`.
- All non-C-O contacts exceed `1.55 A`; neighboring Cartesian path arcs are `0.467-0.913 A`.
- Images 01-08 use fixed C/O for a constrained Fe-environment pre-relaxation; released T/T/T copies are saved as `POSCAR_NEB_RELEASED`.
- Planned pre-relaxation: `IMAGES=8`, 32 cores, `IOPT=3`, `LCLIMB=.FALSE.`, `NSW=60`, `EDIFFG=-0.10`, stable Fe SCF settings, Gamma `5 3 1`.
- Local review folder: `C:\Users\86177\Desktop\结构\neb_Abridge_to_D_refined_8img_constrainedFe_pre_001_precheck`.
- Remote upload/precheck/submission are pending because `sunboquan-codex` repeatedly timed out on SSH port 22 and did not answer ping. On recovery, first verify whether the remote target directory exists, then upload, run `dist.pl` and `nebmovie.pl 0`, and only then submit.

## 2026-06-21 Refined 8-Image Constrained Fe Pre-Relax Submitted
- Server recovered; remote target was confirmed absent before upload.
- Remote directory: `~/sbq/agent/jobs/neb/fe110_co_dissociation_literature_ABCD_001/neb_Abridge_to_D_refined_8img_constrainedFe_pre_001`.
- Prechecks passed: endpoint geometry delta zero, `dist.pl=3.66559953373041`, `nebmovie.pl 0` movie 32482 bytes, Fe/C/O POTCAR order correct, fixed/released C/O flags validated.
- Job `9506942` is `RUN` on `32*gknew023` and passed VASP startup (`47 ions`, correct endpoints, INCAR/KPOINTS accepted, no M_divide).
- This is a constrained C/O Fe-environment pre-relaxation, not a barrier run. Inspect ionic steps 3/5/10 for Fe-force decline, stable SCF, and no Fe-C/Fe-O contact below 1.55 A. Then combine pre-relaxed Fe with released C/O flags for the ordinary NEB.

## 2026-06-22 Pre-Relax Stopped and Refined 8-Image Ordinary NEB Submitted
- Constrained pre-relax job `9506942` was stopped after 20 ionic steps. C-O targets remained fixed, SCF was stable, and all Fe-C/Fe-O contacts stayed above 1.65 A, but several Fe forces plateaued/rebounded at `0.12-0.32 eV/A`.
- Full use of pre-relaxed Fe created an image04->05 O-Fe jump (`2.247 -> 1.765 A`), so the ordinary path uses only 25% of each Fe displacement and restores C/O T/T/T.
- New remote path: `~/sbq/agent/jobs/neb/fe110_co_dissociation_literature_ABCD_001/neb_Abridge_to_D_refined_8img_stage1_plain_001`.
- C-O path remains `1.184,1.250,1.400,1.550,1.700,1.850,2.050,2.300,2.600,2.955 A`; neighboring path arcs are `0.468-0.926 A`; all contacts exceed 1.55 A.
- Prechecks passed: endpoint geometry delta zero, `dist.pl=3.66559953373041`, `nebmovie.pl 0` movie 32482 bytes, POTCAR order correct.
- Ordinary NEB job `9532195` is `RUN` on `32*gknew022`; VASP startup passed with 47 ions and no M_divide/input error.
- Inspect ionic steps 3/5/10 for molecular collapse, image03-06 continuity, contact distances, force trends, and SCF stability.

## 2026-06-23 Ordinary NEB 9532195 Stopped at Step 9
- Job `9532195` was killed at 9 ionic steps after a renewed path collapse; final status `EXIT` and outputs retained.
- Final C-O/C-Fe/O-Fe (A): 01 `1.185/1.843/2.803`; 02 `1.192/1.889/2.599`; 03 `1.217/1.918/2.358`; 04 `1.214/1.880/2.321`; 05 `1.246/1.751/2.175`; 06 `1.208/1.774/2.218`; 07 `2.172/1.647/1.691`; 08 `2.691/1.662/1.700`.
- Images 01-06 re-formed molecular CO and the image06->07 C-O gap reached `~0.964 A`. SCF was stable; this is a reaction-coordinate/path-conditioning failure.
- `nebmovie.pl 1` was run. Local postmortem: `C:\Users\86177\Desktop\结构\neb_9532195_stopped_step9_postmortem`.
- More images alone are not the solution. Use staged anchor-release conditioning: fix central images03-06 C/O, then retain image04/06 anchors, then only image06, then briefly release all before CI-NEB. Check at steps 3/5/10 and stop if any neighboring C-O gap exceeds 0.6 A.

## 2026-06-23 Endpoint-Derived Periodic-Path Correction
- Direct endpoint analysis found that prior paths used the wrong periodic branch for O.
- IS/FS minimum displacements: C `(-2.6417,0,-0.4271) A`; O `(+2.1145,0,-1.3009) A`. C must move left while O moves right toward their actual final sites.
- Previous paths used the periodic image of final O at `x=-1.5588 A`, forcing an unnecessary ~`5.239 A` leftward O migration and producing coordination/tangent artifacts.
- Pure minimum-image linear interpolation is also invalid at the start because C-O compresses to about `1.053 A` near t=0.1. The new path must rotate/raise O nonlinearly during the first images while following each atom's endpoint displacement.
- After the TS-like region, prioritize continuous movement into the actual endpoint adsorption sites and Fe coordination; do not enforce monotonic minimum-image C-O after dissociation because the periodic branch changes.
- Rebuild the endpoint-derived path first. Anchor-release becomes a fallback only if the corrected route remains unstable. No new anchor job has been submitted.

## 2026-06-23 Endpoint-Derived 8-Image NEB Submitted
- Job `9538352` in `~/sbq/agent/jobs/neb/fe110_co_dissociation_literature_ABCD_001/neb_Abridge_to_D_endpoint_derived_8img_stage1_plain_001`; latest status `PEND` for 32 same-node slots.
- Critical path correction: C moves left to its final site and O moves right to its final site. Never reuse the prior left-moving periodic image of final O.
- Images 01-04 nonlinearly rotate/stretch CO; images 05-09 enter the exact final C*/O* sites. Image04 C-O=`2.05 A` is lying TS-like, not the endpoint.
- Geometry passed: minimum non-C-O contact `1.691 A`, maximum neighboring single-atom step `0.397 A`, exact endpoint deviation `0.000 A`.
- Prechecks passed: `dist.pl=3.66559953373041`, `nebmovie.pl 0` movie `32496 B`, POTCAR Fe/C/O, KPOINTS Gamma `5 3 1`.
- Local review: `C:\Users\86177\Desktop\结构\neb_Abridge_to_D_endpoint_derived_8img_stage1_plain_001_precheck`.
- When RUN, diagnose ionic steps 3/5/10 using force trend, SCF iterations, C-O/C-Fe/O-Fe, and path continuity before deciding whether to continue.
