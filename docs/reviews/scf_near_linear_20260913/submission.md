# SCF9754301 submission checkpoint

2026-09-13: submitted one authorized diagnostic_static calculation through
SUBMIT_DIAGNOSTIC_VASP. Initial live scheduler state: PEND, Gkn_normal, 80 ranks.
Remote: ~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/h_migration_int06_mid_scf_near_linear_20260913

Only BMIX/BMIX_MAG changed to 0.0001 relative to SCF9754110. Source geometry,
KPOINTS, POTCAR specification and launcher hashes verified unchanged. Source
SCF9754110 confirmed EXIT. No failed electronic state copied.

Custodian read-only validation: no blockers/warnings. Canonical diagnostic
preflight: PASS. Gate permitted SUBMIT_DIAGNOSTIC_VASP. Submission receipt:
calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_int06_mid_scf_near_linear_20260913/submission_record.json

Bundle SHA256: 06060c877bd03ed824391e8db842607220e0905d70ef89e59e2996b313524dc8
Gate SHA256: 6c0ee03b40e81bf41770f9c3ca547251181d74c401c3585a5ba1081afb39dd24

Preparation initially stopped before package creation because the old review
does not contain a script.lsf hash. Corrected the check to use the canonical
source submission_preflight.files map; preparation and input validation then
passed. No duplicate submission occurred.

Electronic convergence, normal termination, saved-state validity and restart
reproducibility remain unverified. No scientific result accepted. No further
calculation authorized. Current-task projection updated through review-free
proposal-4454fe76f9f2b33dcb4979db. Global safe sync remains blocked by unrelated
sbq_catalyst_agent_workflow.egg-info/PKG-INFO classification drift.
