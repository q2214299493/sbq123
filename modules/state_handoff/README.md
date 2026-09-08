# State Handoff

## Purpose

Manage repository task and history lifecycle through immutable, evidence-bound
events and reviewable Markdown projections. This module prevents current-state
views from becoming append-only histories and identifies obsolete repository
items without silently deleting them.

It is repository governance only. Scheduler output, calculation files, final
structures, scientific modules, and the calculation registry keep their
existing authority.

## Inputs

- immutable JSON events under `events/`;
- repository task, state, module-map, backlog, error, decision, and history
  views;
- Git status, tracked-file information, projection hashes, and configured
  repository-item rules;
- explicit user review decisions for conflicts, scientific claims, moves,
  archives, and deletions.

## Workflow

1. Run `repo-state audit --phase start` before repository work. It is read-only.
2. Preview initial adoption with `repo-state baseline`; add `--record` only
   after inspecting the stable proposal ID. For later work, record a
   schema-valid event with evidence and supersession links.
3. Generate a hash-bound proposal.
4. Apply deterministic managed-view updates with `repo-state sync --safe-only`.
5. If the proposal requires review, Codex asks the user and records the answer
   with `repo-state review` before `repo-state apply`.
6. Preserve corrections as new superseding events; never edit an event file.

A rejected proposal remains queryable history, but its hash-bound source event
is excluded from effective projections and is not presented for review again.
If that rejected event superseded an earlier event, the earlier event remains
effective until a different accepted event supersedes it.

`sync` automatically rebuilds proposals against the latest target hashes. It
keeps only pending events that directly supersede the current approved source;
older unreviewed drafts remain searchable immutable history but no longer fill
the active review queue.

For `scientific_result_registration`, `sync` may reuse an existing review only
for deterministic current-task or module-map projection. Reuse requires an
accepted Grade-A, kinetic-eligible registry barrier, a trusted reviewer, a
matching Excel-promotion receipt, the workbook's exact post-write hash, and
write-only actions limited by `configs/state_handoff.yaml`. A mismatch restores
normal user review; registry or workbook data are never changed by this rule.

## Command Surface

- `repo-state audit --phase start|end`: read-only drift, conflict, stale-reference,
  and repository-item audit.
- `repo-state baseline [--record]`: preview or record the one-time initial
  managed-view adoption proposal.
- `repo-state adopt-lifecycle-views [--record]`: preview or record the one-time
  adoption of controlled backlog, error, decision, and task-history blocks;
  legacy Markdown remains outside those blocks.
- `repo-state compact-current-state --section HEADING --archive PATH
  [--record]`: move one oversized historical subsection into a reviewed
  `docs/history/` archive while preserving the managed current gate.
- `repo-state reconcile-entity --kind KIND --entity ID --keep EVENT
  [--refresh-evidence] [--record]`:
  create a new immutable event that retains one approved current event and
  supersedes all conflicting effective peers; `--refresh-evidence` binds an
  explicitly approved replacement to current local evidence hashes.
- `repo-state propose --event FILE`: validate and record one event, then create
  its hash-bound proposal.
- `repo-state sync --safe-only`: apply only deterministic review-free
  projections from effective events and refresh the actionable review queue.
- `repo-state status`: one operational view of the current task, its one
  executable step, active quality gate, acceptance criteria, history count,
  actionable review count, and audit health. Add `--format json` for tooling.
- `repo-state checkpoint --phase end --event FILE`: validate and record a
  formal task acceptance, derive its hash-bound `task_completed` event, and
  cache one atomic closure-and-handoff proposal.
- `repo-state task status`: show the effective task phase and source event.
- `repo-state task transition --to PHASE --reason TEXT --evidence FILE`:
  create an evidence-bound `open/active/blocked/verification` transition;
  `--apply-safe` projects a review-free transition immediately.
- `repo-state stale-item classify --path FILE --disposition keep|archive|delete
  --content-class unique|regenerable|duplicate --reason TEXT`: determine Git
  tracking status and create a reviewed exact-file disposition proposal.
- `repo-state stale-item classify-batch --manifest FILE`: expand reviewed
  selectors into one immutable exact-file list and create one hash-bound
  proposal covering archive, delete, and `.codex_tmp`-to-`calculations` moves.
- `repo-state review --proposal ID --decision approve|reject`: record the user
  decision as a new immutable event.
- `repo-state apply --proposal ID`: revalidate evidence, approval, and target
  hashes before atomic application.
- `repo-state history --entity ID`: show the entity event chain and
  supersession history.

## Safety Boundaries

- Missing, stale, conflicting, or unhashed evidence requires review.
- Task phase transitions are rejected while the current-task managed block or
  its projection-source event is out of sync.
- Module-map proposals retain a whole-file pre-apply hash for concurrency
  safety, while post-apply drift audits hash only the event-owned module row.
- Scientific acceptance and cross-module changes require review.
- Moves, archives, and deletions always require review.
- External roots are audit-only in version 1.
- Stale-item archive/delete/move actions remain exact-file operations. Batch
  selectors never authorize directory deletion, and every expanded file path,
  size, Git state, and SHA-256 is frozen into the event and proposal.
- Scientific evidence moves are restricted to unique untracked files moving
  from `.codex_tmp` into `calculations`; ordinary archive/delete policy cannot
  mutate calculation trees or named VASP evidence files.
- Credentials, POTCAR, large VASP runtime files, and calculation trees are not
  archived by this module.
- The manager never connects to a scheduler, submits or stops calculations, or
  commits or pushes Git changes.
- Historical compaction is not a managed projection: both the source and new
  archive are exact-hash proposal targets, and application requires review.

## Task-End Acceptance

Direct task closure is forbidden. An end checkpoint must bind the current task
event ID and hash and provide:

- a current task in `verification`; acceptance represents `accepted` and its
  derived closure event represents `completed`;
- one passed result, with evidence hashes, for every `Done When` criterion in
  the original order;
- at least one passed test, inspection, lint, or build command with exit code
  zero and hashed output evidence;
- either one or more exact path-and-hash-bound present artifacts, or an
  explicit `artifact_policy: none` reason;
- a hashed risk assessment declaring either no open risks or explicitly
  accepted open risks;
- a structured `handoff` containing one required history summary and optional
  backlog, unresolved-error, and durable-decision records, each bound to event
  evidence hashes;
- a non-empty completion summary and `verdict: accepted`.

Accepted open risks require `requires_user_review: true`. The checkpoint then
creates a review-required closure proposal and leaves the current task active
until that exact proposal is approved. A review-free checkpoint is closed only
by the normal end-of-task `sync --safe-only` projection.

On application, current-task closure and all non-empty handoff collections are
written atomically to controlled blocks in `tasks/backlog.md`, the error log,
the decisions log, and historical results. History is always written. Empty
collections create no placeholder record. Unresolved errors require an accepted
open-risk assessment and user review; durable decisions also require user
review. The first adoption of any controlled lifecycle block is review-required,
preserves all existing Markdown outside that block, and is reported by audit
until applied. Backlog, error, and decision IDs are stable and repository-wide
unique; stable item markers make repeated projection idempotent.

## Outputs

- versioned event files under `events/`;
- a projection manifest binding managed blocks to event and target hashes;
- ignored proposal-cache files used for Codex/user review;
- approved unique untracked material under `archive/`, with a manifest;
- compact, deterministic Markdown projections.

## Done Criteria

The event schema, read-only audit, proposal/review/apply workflow, safe
projections, lifecycle safeguards, and targeted tests pass. Current-task,
current-gate, module-row, and four lifecycle-view adoptions are recorded by
reviewed immutable events; no existing view is silently taken over.
