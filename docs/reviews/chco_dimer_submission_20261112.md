# CH + CO image05 Dimer submission

## Outcome and authority

User explicitly chose the highest peak for Dimer on 2026-11-12:
“0.6并不算大吧 直接选取最高峰 进行dimer吧”. One VASP Dimer was submitted
as LSF **9998592**, on `sunboquan-codex`, 32 MPI ranks / 32 per node.
Initial canonical scheduler evidence: PEND at 2026-11-12T08:41:15Z.
A subsequent native `bjobs -a -w 9998592` observation showed RUN on
`32*gknew0522`. Queue state is not electronic or Dimer convergence.

Remote: `~/sbq/Fe110/ts/ch_co_to_chco_20261110/dimer_image05_20261112_v1`.
Local: `calculations/fe110_ch_co_to_chco_ts_20261109/dimer_image05_20261112_v1/`.

## Decision and source

Completed ordinary NEB9994246 image05 is the strict local energy maximum;
04 and06 are the reviewed adjacent mode neighbors. The normalized review
structures differ from raw files only by documented integer periodic shifts.
Atom order, cell and Selective Dynamics are unchanged. Original outputs and
the previous default REBUILD_PATH decision remain untouched.

The 0.62833058 A value is the adjacent C-C **distance change**, not a
single-atom jump. Maximum reaction-atom motion is about0.387 A for04->05
and0.461 A for05->06. The scalar-coordinate resolution warning remains.
It does not by itself fail the existing local Dimer hard gate. The prior
claim that densification was mandatory for this explicit Dimer choice was
too restrictive. No gate code, general thresholds or evidence were changed.

The existing explicit `PREPARE_DIMER_HANDOFF` branch produced a fresh bound
decision. Canonical handoff, actual mode review and submission preflight
then produced `READY_FOR_DIMER` with `START_DIMER` as the only allowed action.

## Actual mode and inputs

- POSCAR: exact reviewed05 CONTCAR;49 atoms,Fe45 C2 O1 H1.
- MODECAR: normalized Cartesian central tangent06-04 on the common periodic
  branch;all fixed components zero,49 finite rows,norm0.99999999999963.
- Reaction atoms45,46,47,48 carry amplitude fraction0.93920618,
  **squared** amplitude fraction0.88210825. C45-C46 directional bond-distance
  derivative is-0.75493561 A per unit mode. C45-H48 and C46-O47 remain intact
  in the reviewed source triad. Actual top/side arrows were visually inspected.
- Mode is a starting direction, not a Hessian eigenmode or a validated TS.
- Unchanged PBE/PAW branch,ENCUT400 eV,Gamma5x5x1,ISPIN2,ALGO Fast,
  ISMEAR1,SIGMA0.20 eV,LDIPOLfalse;dynamic MAGMOM45*2.2 2*0.0 1*0.0 1*0.0.
- Repository Dimer profile:EDIFF1e-7,EDIFFG-0.02,NSW300,IBRION3,POTIM0,
  ICHAIN2,IOPT2,DdR0.005,DRotMax1,DFNMin0.01,DFNMax1.0.
- INCAR custodian read-only validation found no blockers or parameter changes;
  algorithm-review warning satisfied by owning module mode/preflight review
  and actual explicit user Dimer authorization.

Before submission, native server runtime/input-target/POTCAR checks passed;
no unfinished account job was reported. POTCAR SHA256:
`e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85`.
Input bundle SHA256:
`bb145b092dbc859998b246ab700d56a8f14b4c66ee6bf44c466d35280a539726`.
MODECAR SHA256:
`80e803c404bf2030524b614a8605a1e5560529e6a443531463e117824f8d213d`.

Canonical executor reserved and submitted exactly once;local/remote target
leaf names match. No pilot,additional NEB,GPU,training,frequency or job stop.

## Verification and registration

Python syntax and scoped Ruff checks passed. Related execution-gate,
compatibility,VASP-input and submission tests passed. Local MODECAR hard
checks and full Dimer submission preflight passed;remote target/runtime and
POTCAR hash verified. Licensed POTCAR contents were not downloaded/published.

Canonical registry plan was reviewed and applied:35 inserted metadata rows
(1 calculation,1 job,2 status observations,31 files) and1 parent workflow
change submitted->done. Readback and integrity/foreign-key checks passed.
These are provenance rows,**not35 structures or TS results**. The new job has
zero accepted scientific results. Parent ordinary NEB force definitions and
sampling caveat remain distinct from scheduler DONE.

## Not yet verified / next step

Dimer force convergence,negative curvature,final geometry,imaginary frequency
and compatible final electronic barrier are not yet established. A starting
mode may rotate or find another saddle. Next checkpoint should inspect this
job's electronic stability,force/curvature trend and target reaction geometry.
Do not submit another job or claim a TS/barrier automatically.

The earlier RSI review invocation remained BLOCKED before model start because
its configured executable was missing. This execution request did not retry
that research study or alter its profile;no RSI recommendation was invented.

Repository closeout: `repo-state sync --safe-only` failed on the pre-existing
classification mismatch for `sbq_catalyst_agent_workflow.egg-info/PKG-INFO`.
No retry,event edit or automatic choice bypassed it. Scientific submission,
canonical evidence and registry readback were already successful;managed
projection synchronization is not claimed.
