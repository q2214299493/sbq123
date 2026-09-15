# Source-release validation

2026-09-15. The main workspace contains unrelated, unpublished architecture
changes. Only this task's feature was ported to a branch based on the existing
`sbq123` release history; those unrelated changes were not copied.

In the main workspace, initial submission routing lives in
`execution_submission_rules.py`; in the release baseline it lives in
`execution_path_rules.py`. Both use the same SCF scope rule, stage policy,
runtime and tests. The release's SCF-only submission explicitly passes the
reviewed node exclusion to bsub; the main workspace uses its existing resource
forwarder. Ordinary submission behavior was not changed by that release port.

Release worktree verification:

- Ruff on the seven production modules and new test module: exit 0.
- `git diff --check`: exit 0.
- The five relevant pytest files: 135 passed, 4 inapplicable combinations
  skipped in 33.91 seconds, exit 0.

The main-workspace result remains 142 passed, 4 skipped; the difference is in
pre-existing tests on the two baselines, not failed or waived new tests.
All executions were mocks/local checks, with no scientific job launched.

The current task projection was applied separately in the main workspace.
Its general `repo-state sync --safe-only` still reports the pre-existing
PKG-INFO stale-classification error. No unrelated classification was repaired
or silently approved in this task.

The release copy of `task_state_event.json` is a main-workspace handoff snapshot
only. It was not activated in the release worktree: that history lacks its
superseded event. No historical state migration was attempted.
