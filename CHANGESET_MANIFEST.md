# Changeset Manifest

## Basis

The initial allowlist is independently revalidated from
`VERIFICATION_REPORT.md` section 2.2 and extended only by the three condition
closures: recovery documentation, the legacy alpha-Fe submit guard, its tests,
and mechanical review evidence. Every row below is allowed in the final A/B/C
review set, except that a row marked `partial` permits only its named patch hunks.
Files and hunks outside this boundary are excluded.

The manifest cannot embed a stable hash of itself. Its SHA-256 is therefore
recorded after generation in `artifacts/refactor_changeset/changeset_sha256.txt`.

| File | Git state | Tracked | Bytes | SHA-256 | Purpose | Category | Referenced | Scientific logic | Allowed |
|---|---|---|---:|---|---|---|---|---|---|
| scripts/artifact_io.py | M | yes | 2909 | 020a7786bb165294f4794c732286880c69d11fa9a828daddda5f3d8aae6c3d56 | Atomic same-directory JSON writes with unique temporary files. | code | yes: repository import or CLI path verified | no | yes |
| scripts/convergence/common.py | M | yes | 758 | 16f821cc49a5bb72d24f739072ba04b2c9efde385219c6e38e7a37929904c6d6 | Single shared definition of the existing 300-second submission timeout. | code | yes: alpha submitter and neb submission | no | yes |
| scripts/convergence/setup_alpha_fe_bulk_smearing.py | M | yes | 9696 | b901971dc0e2ea327d7e013701d7ba77e1e5b3da0a22a87ed53c9b937f83b0d8 | Legacy bsub idempotency, timeout, and unresolved-attempt guard. | code | yes: repository import or CLI path verified | no; submission safety only, input/scientific values unchanged | yes |
| scripts/neb_agent/remote_monitor.py | M | yes | 2775 | 92599b5ca6d419508b7baa766030dab6265094ac8e66f9c73d76fb36d44ad554 | Finite SSH timeout and explicit CLI failure. | code | yes: repository import or CLI path verified | no | yes |
| scripts/neb_agent/submission.py | ?? | no | 13851 | ac2eaf13e97ed5320df1a2acc65ba4863148938b86abaaec2f8cc5d102ae531b | Finite external-command timeout, unresolved/success guards, clearer recovery error. | code | yes: repository import or CLI path verified | no | yes |
| scripts/scheduler_evidence.py | ?? | no | 3789 | eccdda321f1d2c48c0d015bfc5441af512e00ab4a2746403895c5bff52c580df | Finite LSF query timeout and non-success unknown-state handling. | code | yes: repository import or CLI path verified | no | yes |
| scripts/ts_strategy_engine/execution_decision.py | ?? | no | 2654 | fbe7e981101da84381250cda37a733fc0a42aaf0975d7196a8feae8fcca5869c | Pure execution-decision document construction split. | code | yes: imported by execution_gate.py | no | yes |
| scripts/ts_strategy_engine/execution_gate.py | ?? | no | 12128 | 0e2ddca8e3888e6a0e29dcac7b8daecc29c2ece52252cbddfe059545d83c24d1 | Authoritative execution gate with old public import compatibility. | code | yes: repository import or CLI path verified | no | yes |
| tests/test_alpha_fe_bulk_submission.py | ?? | no | 6128 | 92e7cf9fa9232c31769cde92573ffd1db3e0be4cf87aa18fe73cafe4a09c7da9 | Legacy submitter success/failure/timeout/idempotency/input regressions. | test | yes: pytest discovery | no | yes |
| tests/test_artifact_io.py | ?? | no | 3049 | 8cd05c6082485877ab2e3685c93999b4030fa1c49e317c1dd6384443d9e42ba7 | Atomic, failure rollback, cleanup, unique temp, and multiprocess regressions. | test | yes: pytest discovery | no | yes |
| tests/test_config_boundaries.py | ?? | no | 732 | 806b8f2f2d3b512dc298b2665cc1bbe8b72d51c2f491300c22c55fa72b40b7f6 | Example and invalid configuration boundary checks. | test | yes: pytest discovery | no | yes |
| tests/test_execution_gate_compatibility.py | ?? | no | 2656 | db0380def6b601b2d396db27d365eec76a97f871f4714e60e556fe543ff01b8c | Old execution_gate imports, signatures, and dependency direction. | test | yes: pytest discovery | no | yes |
| tests/test_external_command_boundaries.py | ?? | no | 3022 | 2f0abbff1bcfc3d328f231ada6d395b4e47c4e698089e8b8269c398daa3481fd | Timeout, child termination, and scheduler unknown-state checks. | test | yes: pytest discovery | no | yes |
| tests/test_neb_remote_monitor.py | M | yes | 2845 | 7d6cc7d799d7a57f0dee2d64d6cc9e0a2630feb9783d52725432d45a0ec0e5e8 | NEB monitor argument, timeout, and SSH failure checks. | test | yes: pytest discovery | no | yes |
| tests/test_repository_contracts.py | M | yes | 15564 | 1587a5ac985468350f7b942ad62fb88f5598cbd07d6908aba98e9a3f5dddd84a | Narrowly allow the required review-artifact directory and exact three files. | test | yes: pytest discovery | no | partial: artifact-directory contract hunks only |
| tests/test_neb_submission.py | ?? | no | 10313 | 6cb56be7f791093b45b38fb9a5b0968e8ddb2a55529994d5b7585fd8d854930e | Submission failure, unresolved, success, and duplicate-submit guards. | test | yes: pytest discovery | no | yes |
| README.md | ?? | no | 4181 | e1b5d12fbdf24af5e2ee5294347be31aefb8bb7d68d8ca3c3223f25a8520ba0c | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| PROJECT_AUDIT.md | ?? | no | 8201 | 336ffa65240f3263f10f6166c8f02bbadcd7e453ad8cf46e671c41dc675bd3d3 | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| REFACTOR_PLAN.md | ?? | no | 2777 | 1034e411093db49b135b8c973e498187f77729dba26c266d86395b5bacdce552 | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| ARCHITECTURE.md | ?? | no | 4613 | adc806915957e09683b482e9ea358caafe508fcce95e975839b92f47fe698867 | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| DEPRECATED_CODE.md | ?? | no | 1385 | 1f4d745b8b810b7b07cb54a6418eeefffb2affc674d8a57d75349afc872cec7f | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| REFACTOR_REPORT.md | ?? | no | 3073 | 7edcbc292a9200e055ac7fd5131ca24e937f6a04412e249a93f334a3790337e6 | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| VERIFICATION_REPORT.md | ?? | no | 22274 | 9b47378e6b89d1dbbe8f5b69e5b2fd93f9ff6c424a9fd16d1afa6f00a456e57c | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| SUBMISSION_RECOVERY.md | ?? | no | 2225 | bc9c76fe20946ada00e99e206ab5c755db25a587a3a990c6b82aa280dfeb36c4 | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| UNTRACKED_FILE_INVENTORY.md | ?? | no | 167618 | a676596c73440e7377570cdf2b4f6c9816be54c94da87ddf818eb987fc5f030a | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| REFACTOR_CHANGESET.md | ?? | no | 6354 | e78c82209570db5a057d361912ee711999cc5c897bba6eb15c9504898c812c51 | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| CONDITION_CLOSURE_REPORT.md | ?? | no | 6187 | 0fa4b8af4cbfdac6754cc0e1d8d0b0eaceb16711738800e8345dfaa7731a8b53 | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| docs/14_CODE_ARCHITECTURE_GUIDE.md | M | yes | 14778 | 6f93bce4102a87f891a9852c7030c4f21d8a9639cc777b158ff5f68e91e4778e | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| modules/transition_state_search/README.md | M | yes | 19015 | d6ec48de375f77be02a933f6609217429092b1a5dd38cf517d601a2b8f1e2c08 | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
| scripts/README.md | M | yes | 3556 | d53402037569317fdd281482916229937f397107afb5a73f3eaf88537a4c4f99 | Audit, architecture, compatibility, or closure documentation. | documentation | yes: review/documentation deliverable | no | yes |
