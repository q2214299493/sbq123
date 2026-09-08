# Memory Migration Module

## Purpose

Migrate only durable project knowledge from legacy memory, chats, logs, and archived calculations into concise project documents.

## Include

Migrate an item only when it is useful for future setup, interpretation, or failure prevention and has a traceable source. Prefer verified values, stable workflow rules, reusable parameter lessons, endpoint origins, and decisions with continuing consequences.

## Exclude

- full chat transcripts or long narrative summaries
- transient queue status and superseded current-state details
- duplicated facts already represented by a stronger source
- raw large calculation outputs
- unverified values presented as facts

Uncertain candidates must be marked `Needs confirmation` or rejected with a reason.

## Directories

- `inputs/`: batch manifests and bounded source selections; do not dump whole chats here.
- `extracted/`: normalized working notes awaiting quality review.
- `archive/`: completed or superseded migration manifests, not scientific calculation archives.
- `reports/`: one concise provenance and quality report per completed batch.

## Destinations

- `docs/07_MEMORY_INDEX.md`: sources, category progress, batch IDs, and provenance.
- `docs/08_HISTORICAL_RESULTS.md`: historical energies, endpoint origins, job diagnostics, convergence results, and reusable parameter lessons.
- `docs/09_USER_PREFERENCES.md`: server templates, commands, naming, reporting expectations, and recurring workflow preferences.
- Existing decision, error, module, file-index, and backlog documents when a migrated item affects them.

## Batch Workflow

1. Select one bounded category and assign a batch ID such as `MM-001`.
2. Record source paths, scope, and status in `docs/07_MEMORY_INDEX.md`.
3. Extract candidate facts with source pointers; verify against raw files when available.
4. Deduplicate against current project documents and reject transient or obsolete details.
5. Write accepted items to the correct destination with units, job/path references, and confidence.
6. Run a consistency check; do not move historical detail into `docs/02_CURRENT_STATE.md`.
7. Save a batch report, update indexes and module status, then close the task.

## Batch Done Criteria

- The declared source scope was reviewed.
- Every accepted item has provenance and verification status.
- Rejected and uncertain items are recorded without being promoted as facts.
- Destination documents, file index, memory index, and relevant logs are updated.
- No scientific calculation file was modified.

## Completion

Batches `MM-001` through `MM-004` reviewed every supported category. Remaining `Needs confirmation` entries are documented evidence gaps; future sources can be added as incremental batches without reopening completed material.
