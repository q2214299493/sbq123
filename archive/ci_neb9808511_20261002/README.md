# CI-NEB9826728 submission handoff

2026-10-02 Asia/Shanghai. Scope: IS-A9725473 to INT06_9748648 H migration only.

- Ordinary parent9808511: LSF DONE; all9 internal images completed normally, final electronic convergence,71 ionic steps, maximum final NEB force0.049947 eV/A.
- Raw CONTCAR files retained. Integer lattice translations only unify the final Fe periodic branches. Atom order, cell, Selective Dynamics and fixedFe0-17 remain unchanged; physical-equivalence error below1e-8 A. Maximum adjacent atom displacement0.401628 A.
- Final actual OUTCAR TOTEN maximum: image05. Lower peaks01 and09 remain separate migration features; no single-saddle claim for the whole path.
- Completed-path VTST nebmovie.pl1 executed before interpretation. New input dist.pl and nebmovie.pl0 both completed. This VTST installation emits CON-format `movie`, saved as `nebmovie0.vtst`; the genuine portable `movie.xyz` was generated separately. Actual-coordinate contact sheet inspected.
- Geometry PASS, CI preflight PASS and current hash-bound ENABLE_CI_NEB authorization PASS. Submitted once through the canonical executor; job9826728, saved scheduler statusPEND.
- Connection: sunboquan-codex/sbq123, nsgkn_chengdj3@10.68.0.103:22. Remote directory: `~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_is_a_int06_ci9808511_sbq123_108r_20261002`.
-9 internal images,108 MPI ranks,12 per image,NPAR4,per-node cap16. CI stage usesLCLIMB=true,IOPT1,EDIFFG=-0.02 eV/A,NSW300. RetainedALGO=Fast,SIGMA0.20,PBE,ENCUT400 and5x5x1 mesh. No pilot or repeated ordinary NEB was submitted.

`prepare_ci.py` is a bounded one-off, not a new execution authority. It prepares/checks inputs and delegates authorization/submission to the existing repository gate/executor. Read existing receipts before any retry.

Scientific limits: no frequency, accepted TS, Grade-A status or formal barrier is claimed for this segment. CI may change the highest-image identity during refinement. Already accepted INT06-MID and MID-FS segments were not changed.

Validation: helper syntax checks passed; canonical geometry, contract binding, path review, source binding and CI submission preflight passed. Related scheduler/gate/submission regression suites passed, and3 dedicated stage-schema tests passed. Only the existing scheduler schema gained the missing `ci_neb` stage; no scientific gate was relaxed. Adsorbate distances were independently checked with ASE find_mic because component-wise fractional rounding is not an exact shortest-distance metric for this skew lattice.

State handoff: factual task event `task-is-a-int06-ci9826728-20261002` applied safely. Global `repo-state sync --safe-only` still reports the pre-existing classification mismatch for `sbq_catalyst_agent_workflow.egg-info/PKG-INFO`; no unrelated repair attempted.

Next: on a requested checkpoint, monitor9826728 with the canonical compact NEB monitor, separating scheduler, electronic, force, geometry and scientific validity. No recurring automation was requested or created.
