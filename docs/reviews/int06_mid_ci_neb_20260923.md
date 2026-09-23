# INT06 → MID: switch from Dimer to CI-NEB

User explicitly requested `那取消dimer 改为ci neb`. Dimer9795943 was stopped through its job-bound STOP_JOB gate; scheduler EXIT confirmed. All prior files remain intact. Its repeated unconverged electronic evaluations are not accepted forces or TS evidence.

CI-NEB9796856 uses the complete normalized final path of ordinary NEB9793467, not any unconverged Dimer structure. All seven input structures remain byte-identical to the reviewed final path. The last five internal-energy evaluations each have peak03; actual internal XDATCAR frames supply coordinate drift evidence. Fixed endpoints use their unchanging coordinates. The existing canonical evaluator returns CI_NEB_READINESS_EVIDENCE. The isolated C_gap persistence flag remains non-blocking because independent underresolution evidence is absent; no thresholds were relaxed.

Canonical geometry, dist.pl and nebmovie.pl0 checks pass. Generated movie coordinates match all reviewed source structures. CI input custodian has no blockers or warnings. Current file-bound gate authorizes ENABLE_CI_NEB.

Submission:80 MPI ranks,5 internal images,ALGO Fast,ISMEAR1,SIGMA0.20,EDIFF1e-5,EDIFFG-0.02,LCLIMBtrue,ICHAIN0,IOPT1,NPAR4,SPRING-5,NSW300. PBE/ENCUT400/Gamma5×5×1/fixed bottom18Fe remain unchanged. The project CI stage supplies numerical settings; missing builder mesh/resource metadata is explicitly inherited from the same approved ordinary profile in the local resolved profile. Script is pure LF and excludesgknew0440. No pilot or restart reuse.

Local directory: `calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_mid_vasp_bowed_20260921/ci_neb_20260923`.
Remote directory: `~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_vasp_bowed_20260921/ci_neb_20260923` on sunboquan-codex.

The method switch does not prove that electronic oscillation cannot recur. EDIFF differs from the Dimer stage by the approved stage policy; this is not a pure method-only experiment. No scientific TS/energy/strategy-template promotion. Next: inspect startup and electronic convergence of all five images, then force trends. CI-derived final acceptance still requires the applicable frequency/connectivity protocol.
