# Project research assistant implementation and acceptance

## Scope and repository identity

This task adds a project-wide RSI advisory entry for diagnosis, option comparison
and evidence/calculation planning. OH is one acceptance case, not a product
boundary. The same orchestrator and registered tools handle all three intents;
there are no case/job-specific branches and no required `failure_class`.

The producer began clean at `7cc8ac2d42a9a9c15eb87e12dd10bd6d42324806`,
`codex/rsi-practical-comparison-20261028`, and moved to the task branch
`codex/research-assistant-20261028`. The sbq123 main checkout remained at
`5c5fed9`. Earlier round artifacts and failures are retained. No main merge,
SPC modification, scientific job operation, production database write or
scientific threshold change belongs to this task.

## Software and ownership

- `scripts/research_assistant/` implements a bounded source catalog, registered
  host tools, versioned goal/evidence/hypothesis/options/acceptance contract,
  explicit model-request/host-result loop, human report and separate feedback.
  `--intent auto` accepts a natural-language goal; optional explicit intents are
  `diagnose`, `compare` and `plan`. Daily use permits sourced history; evaluation
  requires a reviewed hash-bound input manifest and excludes reference artifacts.
- VASP/SCF/force, POSCAR/mapping, strategy composition and retrieval reuse their
  existing owners. Conflicting parser results remain visible; this module adds
  no scientific acceptance rule. Tools read catalog IDs, not arbitrary shell
  commands. Original sources and first model answers are retained with hashes.
- `review_events.py` extracts the existing strict App Server event validation
  unchanged for reuse by old diagnosis and the new entry. The existing
  `last_positions` parser moves from `review_completed_neb_parent.py` to
  `neb_agent.utils_vasp`; the original import remains compatible. Old
  `learning diagnose`, `advise-next` and review-order experiment semantics remain.
- Module routing, module map, CLI entry and owner documentation register the new
  orchestration module as **Active**. `workflow.draft` uses the existing strategy
  composer to create an unapproved candidate, not an executable job package.

The admitted ChatGPT route remains gpt-6.1-sol/medium, file credential storage and
frozen-context messages. No native model tools are declared. A checked replacement
of the one task data view preserves the previous authentication, auth-home deny,
network profiles and disabled features; other configuration differences reject
the run. No credentials, API key or personal configuration are copied/migrated.
Permission canaries are recorded; whole-filesystem isolation remains unknown.

## Actual acceptance evidence

Local artifact root:
`C:\Users\86177\Desktop\fe110_rsi_experiments\research_assistant_20261028`.
The source-bound `acceptance_index.json` and Chinese `acceptance_review.md`
index prompts, first answers, receipts, tool results, feedback and limitations.
These are daily-use demonstrations, not blind tests or a direct-question
superiority comparison. Fixed offline probes are not model-selected actions.

| Question/intent | Model-selected host evidence | Result and next action | Live record |
|---|---|---|---|
| OH terminal diagnosis | VASP/SCF, terminal position alignment, raw file tails, actual structure measurement | stdout reaches a later endpoint than archived OUTCAR. The last complete force block is 0.625299 eV/Å but differs from CONTCAR by 0.00737168 Å, so it is not established as the saved final force. Recover/verify same-run complete output before acceptance or a new calculation. | `live_oh_01`: 3 turns, 8 executions |
| C3 option comparison | VASP/SCF, force/position alignment, initial/final geometry, directed evidence and history | Maximum movable-atom force 0.860795 eV/Å; last complete positions match CONTCAR within 7.8752e-6 Å. Distances support a fragment hypothesis, while electronic parsers disagree. Compare read-only identity review, conditional fragment optimization and review of an intact-molecule seed; unknown cost stays unknown. | `live_c3_02`: 3 turns, 8 executions; first `live_c3_01` retained |
| Fe(110) C*+H*→CH* planning | contract/force-label reports, local method/history search, endpoint mapping/geometry, frequency-output parsing | C45–H46 (zero-based) changes from 2.972796 Å to about 1.106264 Å in endpoint inputs. Early diagnostic-only frequency review and a later accepted summary require provenance/version reconciliation. Plan final acceptance, endpoint consistency, label applicability, TS/frequency, compatible barrier and three-state free-energy evidence before proposing new jobs. | `live_fe110_01`: 3 turns, 8 executions |

Four real runs total **12 model turns and 32 host executions**, with **0 native
model tool calls**. Each received a fresh session, maximum 3 turns/10 host actions/
360 seconds, and preserved its first answer. This phase saw no HTTP429; software
failure tests verify stop-without-retry behavior. There was no automatic retry,
answer repair or selection of the best answer.

All App Server process exit codes are retained as **1**. The transport's close
method terminates a still-running child; the receipts lack the pre-close poll
state, so this code alone does not distinguish autonomous exit from host cleanup.
Completed model turns, output validation and process exit are separate evidence.

## Defects actually found and validation limits

The first OH method-document lookup failed because the adapter treated an MD
target as JSONL. The first C3/Fe long-result presentation sliced JSON as text,
hiding some middle fields. Both first records remain unchanged. Routing now
checks source type; output uses a bounded structural projection and retains both
complete host JSON and the exact model-visible projection. The same method
document was checked offline with positive English keywords and a genuine empty
Chinese lexical match. C3's separate post-fix real run confirms the force value
is now visible and used. OH and Fe were not rerun to replace their first answers.

Final post-live changes tighten feedback IDs, classify hashed feedback as history,
reject unsupported non-generation assertions and improve human report coverage.
They are covered offline, not relabelled as an identical live source revision.
The four retained final answers also pass the tightened contract without another
model call. Per-run source hashes and the final release binding preserve this
distinction. Citation identity/JSON checks do not validate scientific reasoning.

The software checks actually executed were syntax compilation, imports, scoped
Ruff and **324 related tests: 324 passed, 0 failed/error/skipped**. The suite covers
new orchestration and failures, old diagnosis/review-order/learning behavior,
VASP parsers and architecture boundaries. Logs/JUnit are in
`validation_final_02`. An earlier Ruff complexity failure was corrected by
extracting the absence check; earlier validation records remain local.

## Connected, incomplete and deferred

- Connected: scoped inventory/reads, existing VASP convergence observations,
  structure/mapping/terminal correspondence, local historical attempts and
  feedback, local BM25 methods, existing strategy candidates and unapproved
  strategy drafts. Original DB snapshots are read only; writes use a private copy.
- Draft composition was exercised on real Fe(110) contract/endpoint material in
  the **offline host-tool** probes. None of the live model runs selected
  `workflow.draft`; it is not claimed as model-driven draft acceptance.
- Not connected/accepted: native model callbacks; automatic remote/scheduler
  collection; online method/database connectors; automatic complete INCAR/job
  packages. A reviewed whitelist/vector bridge exists but has not received new
  end-to-end production retrieval acceptance in this task. Local BM25 is lexical,
  not semantic or external scientific transfer approval.
- Daily history may include later reviews; it must be interpreted as sourced
  history. Evaluation manifest authors still own the cutoff and exclusion of
  answers embedded in otherwise allowed text. Missing in the input/scope is not
  proof of absence or non-generation elsewhere.
- Scientific quality/acceptance remains pending human owner review. Actual
  adoption, human preparation/review time, future result and cost are unknown.
  Feedback contains preliminary host observations and never promotes science or
  approves a strategy. Automatic learning/ranking improvement is not claimed.
- SPC is deferred to a thin consumer of the stable output contract; no second
  diagnosis implementation or SPC adapter is created here.

## Repeat on this machine

```powershell
python "C:\Users\86177\Desktop\fe110_rsi_experiments\research_assistant_20261028\use_research.py" --workdir "C:\Users\86177\Desktop\work\calculations\fe110_c3_existing_recovery_20261023\collection_v1\9629858" --goal "依据结构和优化证据比较下一步方案，列明条件、风险和最有区分力的核查。"
```

Replace only the work directory and natural-language goal for another question.
The wrapper supplies the existing nonsecret task profile, code path, admitted
binary/auth route and unique output root. Optional `--intent` selects one of the
three intents; auto is the default. It does not submit calculations. The generic
module entry is documented in `modules/research_assistant/README.md`.

## Repository state synchronization

Start audit retained the pre-existing TS module projection drift and external
worktree warning. End `sync --safe-only` outcome is recorded separately below;
it must not be represented as scientific evidence or mixed with assistant
acceptance. This task does not authorize unrelated state repair.

The end command actually returned **exit 2**, stderr
`ERROR: state history source changed before proposal generation`, with no
proposal ID/choices. Raw stdout/stderr and the exit receipt are retained in
`state_sync.*` under the artifact root. State synchronization is **not passed**;
no manual projection or event repair was attempted. This does not invalidate the
separately recorded software/model checks, and it is not hidden by them.
