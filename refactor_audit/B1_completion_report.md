# B1 Completion Report — Execution Lifecycle

Date: 2026-09-09 (Asia/Shanghai)
Repository: C:/Users/86177/Desktop/work
Branch inspected: refactor/v2-architecture-repair
Baseline HEAD: 3a4c23f3bae8da264323fea75d6fe593ca562845

## Result and scope

Completed the execution lifecycle refactor in the five authorized source files and related tests. The existing submission executor remains the only executor introduced or modified by this task. No safe_submit.py or alternative submission implementation was created.

B0 findings addressed within this scope: B1-01 (execution authorization/evidence), B1-02 (paths, digests and POTCAR identity), B1-03 (reservation and uncertain submission recovery), and B1-04 (upload verification). B1-05 concerns GPU wrapper preambles outside the authorized files and remains open.

This task did not commit or push, change scientific thresholds or VASP parameters, change TS acceptance criteria or registry schemas, operate a production database, or run a real remote calculation. Test databases, fake scheduler records and shell fixtures were confined to pytest temporary directories. The working tree was already dirty; unrelated user work, including tests/test_ts_strategy_learning.py, was preserved. Existing project task/state projections were not synchronized because that would write outside this request's explicit scope.

## Changed files

| File | Change |
| --- | --- |
| scripts/neb_agent/submission.py | Immutable input-bundle/reservation/result objects; exclusive reservation before remote work; repeated evidence binding checks; staged hash verification; remote target reservation; one final manifest-verification-and-bsub command; immutable receipt; read-only status; validated job IDs and rechecked stop authorization |
| scripts/ts_strategy_engine/execution_gate.py | Preserve scientific decision, expose scientific_readiness separately, filter executable actions through scoped authorization, and recompute authority metadata during validation |
| scripts/ts_strategy_engine/execution_evidence.py | EvidenceBinding and ExecutionAuthorization; canonical workdir identity; non-circular evidence digest; source-file binding and POTCAR.spec identity checks |
| scripts/ts_strategy_engine/execution_path_rules.py | ScientificReadiness snapshot and reusable relative/local/remote path and LSF job-ID validation; original scientific rules unchanged |
| scripts/artifact_io.py | Add write_json_exclusive using O_CREAT/O_EXCL, file fsync and POSIX directory fsync; preserve existing replacement-style atomic writer |
| tests/test_execution_lifecycle.py | New lifecycle, authorization, concurrency, process-death, path, staging and real-shell integration tests; test-only authorization fixtures |
| tests/test_artifact_io.py | Independent-process exclusive reservation competition and interrupted-write retention |
| tests/test_neb_submission.py | Real hashes and authorized bundles in fixtures; preserve successful reservations and recognize unknown outcomes |
| tests/test_neb_execution_gate.py | Distinguish unchanged scientific eligibility from executable authorization; reject unscoped legacy approvals |
| tests/test_ts_strategy_engine.py | Keep continuation science assertion and separately assert absence of unbound execution authority |
| refactor_audit/B1_completion_report.md | This completion report |

## Object and authority separation

| Object | Owner | Meaning |
| --- | --- | --- |
| ScientificReadiness | execution_path_rules.py | Original scientific decision, reason codes and eligible actions; never sufficient to submit |
| ExecutionAuthorization | execution_evidence.py | An explicit action and target, evidence binding, authorization source and POTCAR identity |
| EvidenceBinding | execution_evidence.py | Canonical workdir identity, input bundle SHA-256 and scientific evidence SHA-256 |
| InputBundle | submission.py | Calculation kind, immutable sorted manifest and canonical bundle hash |
| SubmissionReservation | submission.py | Unique token and pinned execution context, published exclusively before staging/upload and retained permanently by the executor |
| SubmissionResult | submission.py | SUBMITTED with a validated scheduler ID, or UNKNOWN_NEEDS_RECONCILIATION |

The gate retains DECISION, REASON_CODES and the existing science-related fields. scientific_readiness.eligible_actions records the original eligible actions. ALLOWED_ACTIONS and the execution flags now reflect explicit authorization as well as scientific eligibility. An inline path_reviewed=True cannot grant execution authority.

Execution authorization binds:

- action;
- target object: server_alias and remote_dir, plus job_id for a job action;
- canonical workdir_identity;
- bundle_sha256;
- evidence_sha256;
- source.path and source.sha256 for the recorded authorization source;
- for submission, potcar.source, potcar.sha256 and potcar.spec_sha256.

It also retains the existing schema_version=1, document_kind=user_execution_authorization, authorized_at and calculation_kind fields, with existing job cancellation fields where applicable. The authorization artifact itself is file/hash bound through source_bindings. Applicable supplied scientific artifacts retain their producer/source-file validation; missing or stale bindings remove execution authority.

The evidence digest excludes the authorization payload and its own source-binding entry, preventing a self-referential hash cycle. Other scientific inputs, source bindings, thresholds and review state remain part of this digest. The complete existing gate state hash still includes authorization.

For connectivity relaxation, user_execution_authorization.json is removed from the input-bundle manifest. It remains mandatory execution evidence in the gate. Keeping authorization outside the physical input bundle avoids a second circular dependency without changing the connectivity scientific checks.

## Submission lifecycle

1. Validate the configured VASP backend, remote paths, POTCAR digest, complete local bundle, calculation/action pairing, current preflight and scoped gate authorization.
2. Exclusively create submission_attempt.json. O_EXCL is the concurrency decision point; earlier existence checks are only explanatory guards.
3. Revalidate the pinned gate, authorization, source evidence, bundle and preflight after reservation.
4. Exclusively reserve the remote target using a sibling directory named <remote_dir>.submission-reservation and record its token. This also blocks cooperating submitters from different local checkouts targeting one remote directory.
5. For a new upload, copy only manifest files into temporary staging and verify every staged digest before scp. Reuse skips copying, not verification.
6. Revalidate local evidence and input binding after upload and before the final remote command.
7. In one Bash command, verify the remote reservation token and path boundaries, hash-check the POTCAR source, provision POTCAR only if absent, verify every manifest file including POTCAR and POTCAR.spec, reject symlinks and unmanifested regular files, then invoke bsub script.lsf.
8. Parse exactly one valid LSF job ID and exclusively write submission_record.json. The original reservation is never removed or overwritten.

Both upload paths use the same complete remote verification code. Bash runs with errexit, nounset and pipefail; verification failure prevents bsub. Existing remote POTCAR contents are checked rather than overwritten. Unbound restart files such as WAVECAR prevent reuse.

Failure handling is deliberately conservative. Any reservation without a valid success receipt is UNKNOWN_NEEDS_RECONCILIATION, including failures before bsub. Exceptions attempt to write an immutable unknown result. A hard process exit may leave no receipt at all; the read-only status function derives the same unknown state from the retained reservation. Partial/corrupt receipts also fail closed. Neither local nor remote reservations are automatically released, expired or retried.

Recovery inspection uses the existing executor:

    python -m scripts.neb_agent.submission status --workdir <calculation-directory>

This command does not query a remote system, retry, release reservations or infer that an absent scheduler listing proves no submission. Unknown outcomes require explicit human reconciliation with scheduler/history evidence. Automatic resubmission is not implemented.

## Path and digest controls

- Remote paths must be under the existing ~/sbq boundary. Traversal components, empty/dot components, absolute paths, backslashes and shell metacharacters are rejected before constructing shell commands.
- Local manifest paths must be safe relative paths. Every component is checked for symlinks/junctions, and the resolved regular file must remain in the canonical workdir.
- Remote root canonicalization and per-component symlink checks guard setup, input files, POTCAR and reservation markers. Reused trees cannot contain symlinks or extra regular files.
- Manifest, bundle and POTCAR digests must be SHA-256 values. LSF IDs must be positive ASCII decimal IDs within the accepted size bound before bjobs/bkill command construction or receipt acceptance.
- The authorized remote POTCAR source/digest and local POTCAR.spec hash must match the submission scope. Remote source and destination bytes are verified before bsub. This establishes reviewed byte identity, not independent scientific validation of a pseudopotential family.

## Duplicated or unsafe logic removed

- Replaced the late check-then-write attempt marker with the shared exclusive writer and a retained reservation. Successful submission no longer deletes the evidence that prevents another submission.
- Removed the weaker fresh-upload path: fresh and reused bundles share the same final remote manifest checks.
- Centralized path/digest/job-ID validation instead of relying on the permissive remote-path regex and unchecked shell interpolation.
- Reused _verify_submission_binding at distinct lifecycle checkpoints rather than implementing separate authorization checks per upload branch.
- Added preflight(write_report=False) for validation checkpoints. Submission no longer overwrites the very preflight file that the gate binds.
- Reused existing scientific rule functions rather than copying scientific predicates into a new executor.

## Compatibility preserved and intentional safety changes

Preserved:

- Existing submit, stop and preflight entry points and existing submit CLI arguments.
- Existing decide_execution and require_action call signatures and compatibility re-exports.
- Existing calculation kinds, action names, backend selection and LSF submission mechanism.
- Existing submission_attempt.json and submission_record.json paths and successful receipt fields, with additional lifecycle metadata.
- Existing scientific rule priority, numerical thresholds, INCAR/VASP checks, TS validation predicates and local handoff semantics.
- Existing canonical JSON hashing and replacement-style write_json_atomic behavior for their other consumers.

Intentional safety changes:

- Old gate documents lacking the new authority objects must be regenerated. Old boolean or unscoped approvals cannot be upgraded by merely editing ALLOWED_ACTIONS.
- A caller that wants scientific recommendations should read scientific_readiness.eligible_actions. Executing an action requires its explicit scoped authorization in ALLOWED_ACTIONS.
- Connectivity preflight hashes change because execution authorization is no longer part of the physical input bundle; regenerate both preflight and gate for a new submission.
- Successful reservations remain on disk. Existing legacy attempts/receipts continue to block duplicate submission. Recovery tools must not assume success removes submission_attempt.json.
- Reuse rejects extra remote input/restart files; it is not an implicit restart or resubmission interface.
- The preflight API adds only an optional write_report keyword, defaulting to its original report-writing behavior. The executor adds an optional read-only status subcommand.

Preparing a new authorized submission remains a review step: produce preflight and file-bound scientific evidence; compute the evidence digest with execution_evidence_sha256; record the exact approved scope and its real authorization source; load that artifact through the existing gate request's authorization_file; regenerate the gate; invoke the existing submit entry point. Test authorization helpers are not production approval tools.

## Validation executed

No real SSH, scp, LSF or VASP operation was executed by the tests. Remote-shell integration uses an isolated temporary HOME and a fake bsub executable. It executes the generated Bash checks themselves, including symlink rejection and checks immediately before fake submission.

### Relevant regression suite

    python -B -m pytest -p no:cacheprovider tests/test_artifact_io.py tests/test_execution_lifecycle.py tests/test_neb_submission.py tests/test_neb_execution_gate.py tests/test_execution_gate_compatibility.py tests/test_execution_backends.py tests/test_neb_path_quality_control.py tests/test_ts_handoff.py tests/test_ts_strategy_engine.py tests/test_ts_strategy_learning.py --tb=short

Result: **185 passed, no failures or skips**, in 66.54 seconds.

After the final additional POTCAR-source hash check, the execution lifecycle suite was rerun:

    python -B -m pytest -p no:cacheprovider tests/test_execution_lifecycle.py --tb=short

Result: **62 passed**, in 39.95 seconds. Two explicit source-POTCAR corruption cases were then added and run:

    python -B -m pytest -p no:cacheprovider tests/test_execution_lifecycle.py -k source_POTCAR --tb=short

Result: **2 passed, 62 deselected**, in 4.57 seconds. Across these final validation runs, all **187 distinct relevant tests** passed; the full repository suite was not run.

Earlier iterations exposed outdated unbound-authorization assertions, placeholder digests, the learning test's error-message expectation, and the test sandbox's Windows locale decoding. These were corrected and rerun. The pre-existing modified learning test was not edited.

### Required safety cases

| Requirement | Executed evidence |
| --- | --- |
| Invalid remote traversal | Parameterized traversal/root/absolute/metacharacter rejection before any network call |
| Invalid digest | Invalid POTCAR and manifest digest rejection; source/destination POTCAR corruption rejected by real Bash |
| Concurrent submissions: one succeeds | Two concurrent submit calls synchronized at reservation creation, exactly one fake bsub; four independent processes competing for the exclusive writer, exactly one winner |
| Crash after submit | Receipt-write failure and actual subprocess os._exit immediately after fake scheduler acceptance; recovery remains unknown and repeat calls perform no remote operation |
| Stale evidence | Changes to analysis, geometry, thresholds, preflight, authorization and its source; evidence changed during upload also prevents bsub |
| Modified bundle | Local INCAR/POSCAR/POTCAR.spec/script changes, staging-time mutation, and remote input corruption in both upload modes |
| Symlink escape | Local file escape and real Bash remote ancestor-symlink rejection |
| Remote duplicate target | Pre-existing remote reservation remains unchanged and prevents submission |
| Stop execution safety | Scoped PEND-job authorization accepted; live PEND-to-RUN change rejected before bkill; malformed IDs rejected before shell use |

### Static and scientific preservation checks

Ruff command:

    python -m ruff check scripts/artifact_io.py scripts/neb_agent/submission.py scripts/ts_strategy_engine/execution_gate.py scripts/ts_strategy_engine/execution_evidence.py scripts/ts_strategy_engine/execution_path_rules.py tests/test_artifact_io.py tests/test_execution_lifecycle.py tests/test_neb_submission.py tests/test_neb_execution_gate.py tests/test_ts_strategy_engine.py

Result: **All checks passed** on the final modified Python files.

Syntax inspection parsed all 10 modified Python files successfully. Scoped git diff --check passed. Git emitted only line-ending normalization notices.

AST comparisons against the inspected HEAD confirmed no changes to:

- _check_neb, _check_dimer, _check_vfa and _check_connectivity_relax;
- blocking_decision and progress_decision;
- validated_ts;
- canonical_json and the existing write_json_atomic.

This verifies preservation of those implementations. It is not a claim that unmodified scientific logic has been newly validated against production calculations.

## Remaining risks and unverified conditions

1. Real remote deployment was not exercised. The remote host must provide Bash, realpath, sha256sum, find, awk, wc and the existing LSF/scp environment. The Bash behavior was tested locally with temporary fixtures, not on the production scheduler.
2. Reservation guarantees apply to cooperating callers and intact reservation files. O_EXCL and remote mkdir must retain exclusive-creation semantics on the deployed filesystems. Reservations and SHA-256 records are not protection against a privileged actor who rewrites both inputs and authorization evidence.
3. A scheduler-accepted submission with a lost response cannot be resolved automatically without scheduler-side idempotency. It remains unknown and requires human reconciliation. Conservative reservations can also require reconciliation when failure happened before submission.
4. The final remote check and bsub are adjacent in one shell command, but the remote filesystem is not a cryptographically immutable snapshot. External writers must not modify a reserved bundle during submission or execution.
5. Hash binding proves consistency with the recorded approval and reviewed POTCAR identity; it does not authenticate a human signer's identity or establish scientific acceptance. The existing trusted review process remains necessary.
6. Old operational documentation outside the allowed scope still describes the earlier gate/attempt lifecycle. This report records the migration requirements; those other files were intentionally not modified.
7. B0 B1-05 GPU producer-record preamble coverage remains outside this change. No claim is made that every execution path elsewhere in the repository has been refactored.

Next step: review this scoped B1 diff and its authorization/reconciliation contract before any separately authorized production deployment. No production submission, commit or push is part of this completion.

## Subsequent GitHub publication authorization

After the implementation report was completed, the user requested automatic commit and GitHub push after every completed task. AGENTS.md now records this standing authorization, with task-specific no-commit/no-push instructions taking precedence. The earlier statements describe the original B1 completion checkpoint; publication is authorized by this later instruction. Only this task's source, tests, B0/B1 reports and the collaboration rule are included; unrelated working-tree changes remain excluded.

Before publication, an independent temporary snapshot was built from HEAD plus only the 13 task-owned files. It excluded all unrelated working-tree changes and production databases. The same ten relevant test modules passed there: **185 passed in 37.39 seconds**. This snapshot uses the committed version of the unrelated learning tests, so its case count differs from the final dirty-worktree validation above.
