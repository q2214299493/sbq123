# Submission Recovery

## Scope

`submission_attempt.json` means that a remote submission command was started,
but the local process could not confirm whether LSF accepted it. It is an
idempotency barrier, not evidence of either success or failure.

While this marker exists:

- do not run `bsub` again;
- do not delete or rename the marker to bypass the guard;
- do not infer failure from a timeout, lost connection, non-zero wrapper exit,
  or unparseable output;
- keep the task in `UNKNOWN` or `PENDING_REVIEW` until evidence resolves it.

## Read-only recovery procedure

1. Read `submission_attempt.json` and record its working directory or remote
   directory, action, bundle hash, and gate-decision hash when present.
2. Use read-only scheduler queries (`bjobs`, including historical/completed
   visibility where available) and read-only remote directory inspection. Do
   not submit, stop, move, or modify a job during this check.
3. Match a scheduler job only when the job owner, submission time window,
   working directory/job name, and available bundle or script evidence identify
   the same attempt. A job ID alone without matching context is insufficient.
4. If one existing LSF job is unambiguously matched, a human reviewer may create
   the normal success record with the recovered job ID and preserved evidence,
   then remove `submission_attempt.json`.
5. If no unique match can be established, retain the marker and record
   `UNKNOWN` or `PENDING_REVIEW`. Absence from the current queue is not proof
   that submission failed because the job may have completed, exited, or aged
   out of the default query.

## Resolution authority

The operator responsible for the target scheduler account and the repository
workflow owner must review the evidence. Only they may authorize creation of a
recovered success record or a new submission. Automation must not guess,
auto-retry, or auto-delete the marker.

The recovery record should retain the original marker, scheduler query output,
remote path evidence, reviewer identity, resolution time, and rationale. Any
subsequent submission requires explicit human confirmation that no matching job
exists and must follow the ordinary gate and preflight checks.
