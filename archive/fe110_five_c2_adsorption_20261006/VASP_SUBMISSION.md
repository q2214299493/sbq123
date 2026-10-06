# Fe110 five-species VASP submission

User authorization: `提交vasp`,2026-10-06. Ten independent ordinary adsorption relaxations submitted on the configured `sunboquan-codex` backend at10.68.0.103. Each uses32MPI ranks,32ranks/node, production PBE/PAW-PBE,ENCUT400eV,Gamma5x5x1,ISPIN2,Fe MAGMOM2.2,ISMEAR1,SIGMA0.20eV,EDIFF1e-5,EDIFFG-0.02eV/A,ALGOFast,NSW300,Fe45five-layer, fixedFe0-17. No artificial bond restraints.

| Exact species | Candidates and LSF jobs |
|---|---|
| C2H `[C][CH]` | cfg2:9839748; cfg1:9839749 |
| C2H2 `[C][CH2]` | cfg2:9839750 |
| C2HO `[CH][C][O]` | original intact cfg0:9839757 |
| C2HO `[C][CH][O]` | cfg0:9839751; cfg2:9839755; cfg1:9839756 |
| C2HO `[C][C]O` | cfg2:9839752; cfg0:9839753; cfg1:9839754 |

The saved scheduler snapshot reports all tenPEND, not running or converged. Submission receipts and final input/POTCAR hash verification exist for every job. The remote root is `~/sbq/Fe110/adsorption/fe110_five_c2_20261006/`.

GPU2139 returned twelve converged predictions with valid producer/hash/structure invariants. A separate chemistry review excluded02_cfg1(C-H broken),03_cfg0(C-C broken), and duplicate01_cfg0. Nine intact nonduplicate GPU structures were used. The CHCO species was retained using its reviewed intact pre-GPU seed, not its fragmented GPU result. Relaxation may still change connectivity; final identity/minimum/adsorption-energy acceptance remains pending.

The canonical registry plan was inspected and applied once:10calculations,10jobs,10queue observations,70input-provenance records. No predicted energies, accepted results or Excel promotions were inserted. Evidence is in `calculations/fe110_five_c2_adsorption_20261006/vasp_batch_v1/`.

Validation: Python syntax and focused Ruff pass;37adsorption/preflight/submission tests pass; all10custodian validations have no blockers/warnings; all10execution gates explicitly allowSUBMIT_VASP. An extended lifecycle suite has10failures from existing upload `_run(stdin=...)` / test remote-mock incompatibility. Those unrelated changes were not repaired. The actual canonical uploads and submissions succeeded.

The factual task event was safely proposed/applied. Repository-wide `repo-state sync --safe-only` still stops on the pre-existing changed classification of `sbq_catalyst_agent_workflow.egg-info/PKG-INFO`; no deletion/classification workaround was performed.

Next: on a requested status checkpoint inspect compact queue/electronic/ionic progress; after completion validate exact chemistry, sites and duplicates before accepted adsorption-energy registration. No new expensive calculation or automatic resubmission is authorized.
