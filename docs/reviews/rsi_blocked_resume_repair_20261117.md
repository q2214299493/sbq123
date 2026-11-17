# RSI explicit failed-run recovery — 2026-11-17

## Confirmed cause and scope

- The Nov16 notification repair remains installed. A subsequent real research
  run `20261116_125053_8d4be6d0` completed 3 turns and 7 host actions.
- The latest failed run `20261117_162749_ea09296e` instead received
  `httpConnectionFailed`, no HTTP status, before any host action. This establishes
  an upstream connection failure, not a scientific-input or event-protocol fault.
- Current public HEAD checks through the proxy, direct, and inside the RSI client
  sandbox passed. They do not explain the earlier interruption or alone prove
  authenticated model availability. Proxy/auth/TLS settings were not changed.
- A separate code defect prevented explicit recovery: `resume` unconditionally
  opened `research_result.json`, absent after a failed first turn. A new failing
  regression reproduced this before implementation.

## Minimal runtime changes

Owning runtime: `C:/Users/86177/Desktop/rsi-usage-dashboard-20261030`.

- `scripts/research_assistant/continuation.py` accepts a no-answer `BLOCKED`
  parent only after receipt/state question, goal, action-count and journal binding
  checks. Saved host evidence still uses existing source/dependency revalidation.
  Parent artifacts are snapshotted, never rewritten. Successful-parent behavior
  remains unchanged; missing successful results and corrupted bindings reject.
- `scripts/research_assistant/runner.py` avoids an empty previous-claim enum and
  requires null progress for an unanswered parent, not a fabricated prior answer.
  New receipts record actual turn/action/time budgets; defaults are unchanged.
- Eight new recovery cases cover source reuse, parent immutability, binding
  corruption, missing success results and invented prior progress.
- No automatic request retry, wider permissions, model promotion, scientific
  protocol change, training, ML inference or scientific job submission.

## Executed validation

- Python compile and targeted Ruff: PASS.
- Research/resume/policies/SPC/review/protocol regressions: 174 PASS,2 SKIP.
- Dashboard tests run separately: 19 PASS. The initial combined invocation had
  15 missing-fixture setup errors because its fixture-provider module was also
  collected as a test; separate canonical module loading resolved that test-only
  invocation issue, without changing application/test code to hide failures.
- Explicitly authorized one real resume via the configured `use_research.py`:
  `GENERATED`,3 model turns,5 host executions,0 native tools,89.2951 s. It preserved
  the original question and 3-turn/10-action/360-second budget. No second attempt.
- All five host actions were read-only list/read operations on existing diagnosis
  outputs. No 53-test/16-quarantine labels were read. The answer retains limits on
  bounded excerpts and is advice, not full scientific acceptance.
- All four bound parent files remain SHA-256-identical to their snapshots.
  Per-run dashboard reports no source errors. Zero policies were applicable or
  applied; no experience was forced into the question or accepted automatically.

## Canonical evidence

Root: `C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/runs/rsi_recovery_20261117_v1`.

- `run_receipt.json` SHA-256:
  `18890f8f702a85ed348ab46bd033e7da0c90e45f9cc9fcd37b9ccb7c359bf1be`.
- `research_result.json`, `continuation.json`, `tools/E001.json` through
  `E005.json`, and `views/rsi_view.json` bind the actual answer and read evidence.
- Dashboard: `C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html`.

## Result and remaining limits

RSI completed a real original-question research loop, not just a fixed-JSON
smoke. Its advice prioritizes read-only near-neighbor Fe error review and leaves
the 3.11% evaluation-path difference unresolved rather than calling it model
improvement. Full scientific review remains with its owner. External connection
interruptions can recur; this repair enables explicit bound recovery but does
not establish their permanent elimination.
