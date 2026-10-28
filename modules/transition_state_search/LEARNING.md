# Evidence-backed strategy improvement

Status: implemented local tooling; improved scientific success rates remain unmeasured.
Owner: `transition_state_search`. This extends the current workflow and uses
the existing registry, planning, submission and validation layers.

## Components and authority

| Component | Responsibility |
|---|---|
| `configs/ts_strategy_engine/learning.yaml` | Supported strategy fields, bounded proposals, diagnostic routes and reference methods |
| `learning_evidence.py` | Existing-file hashes, exact JSON observations, input identity and cost units |
| `learning_store.py` | Immutable, idempotent events through the existing registry connection layer |
| `strategy_learning.py` | Baseline capture, proposals, attempts, task-local lessons, retry checks and comparison |
| `learning_cli.py` | Explicit local commands through `ts_strategy_engine.cli learning` |

Dependency direction is CLI -> learning/evidence -> registry. The learner does
not call an LLM API, SSH, VASP, a GPU runner, or a training optimizer. The agent
proposes a change from source evidence; deterministic code validates it. There
is no second scheduler, TS validator, model trainer, or execution authority.

`ts_strategy_events` is introduced by registry schema 8. It stores `variant`,
`attempt`, and `outcome` events, separate from Grade-A transferable templates.
History records may contain task-specific provenance, but none is transferable
scientific evidence for a different reaction. Existing TS/barrier writers and
the active final-energy convention are unchanged.

## Offline diagnostic cases

`learning cases-build --manifest CASES.json --allowed-root SNAPSHOT_DIR --bundle NEW_DIR`
builds a write-once bundle from an explicit JSON case manifest. The manifest
has `schema_version: 2` and a `cases` array. Each case provides `case_id`,
`group_id`, `question`, `provenance` (`synthetic`, `reviewed_real`, or
`incomplete`), a nonempty `public_evidence` list, and `reference` or `null`.
Each evidence item has `evidence_id`, `path`, `sha256`, `pointer`, and scalar
`value`. A scored reference has `review_status: approved`, a nonempty
`review_basis`, a separate `source` with the same four observation fields, and
`expected` with `failure_class`, `causal_claim`, `causal_status`,
`causal_evidence_ids`, `next_review`, and `evidence_ids`. The reference source's
selected value must have the same canonical JSON identity as `expected`.
Source paths must resolve to small JSON files inside the allowed root.

Only `public.json` should be given to an answer generator. `private.json`
contains source paths and references; file separation is not an access control
boundary. The manifest author must check that selected values contain no later
conclusions. `manifest.json` is written last and marks a complete bundle.
The private bundle format is version 3: it retains the original allowed root
and rechecks every source and reviewed reference before scoring. Public,
manifest, answer-set and report schema versions are 2. The current builder and
evaluator explicitly reject older formats. Historical files remain readable as
JSON for audit, but are not scored by this version. Rebuilding requires a newly
reviewed claim and evidence binding; a legacy `root_cause_status` cannot be
automatically converted into a causal claim. Preserve historical frozen bundles
and reports; use new paths and freshly reviewed reference artifacts for schema 2.

`learning cases-evaluate --bundle NEW_DIR --answers ANSWERS.json --report NEW_REPORT.json`
scores saved answers without opening a registry or running a model. The answer
file contains `schema_version: 2`, the bundle's `public_sha256`, and an
`answers` array. Each answer has `case_id`, the public case's `input_sha256`,
the six diagnosis fields listed above. No additional answer/reference fields are
allowed. For example, a structurally valid diagnosis is:

```json
{
  "failure_class": "runtime",
  "causal_claim": null,
  "causal_status": "unknown",
  "causal_evidence_ids": [],
  "next_review": "repair_runtime_without_training",
  "evidence_ids": ["observed_error"]
}
```

`unknown` requires a null claim and empty causal IDs. `hypothesis` and
`confirmed` require a nonempty string claim and nonempty causal IDs. IDs must
be unique; causal IDs must be a subset of the answer/reference's `evidence_ids`,
which must themselves cite public evidence. A scored reference still requires
nonempty `evidence_ids`. Certainty does not select a failure class or route:
the existing policy maps `failure_class` to `next_review` independently.

The reviewer must make a hypothesis a specific, testable causal direction and
ensure confirmed evidence directly establishes the written claim itself.
Confirmation never automatically establishes a deeper cause: permission-system
denial and a missing executable bit are distinct claims with potentially
different certainty. Code validates structure only. It does not prove causal
support, testability or scientific truth, and uses no keyword truth validator.
Scoring compares claim text exactly and both ID lists as sets, along with
class, causal status and route. Paraphrase equivalence is not evaluated.
The report lists every case, missing or invalid answers, unknown IDs, and the
scorable denominator. A match means agreement with the supplied review
reference, not scientific TS validation or measured real-world improvement.
Structural answer errors write a failure report and make the CLI exit with code
2. A valid answer that disagrees with its reference is a scored mismatch and
does not make the CLI fail. `integrity_ok` describes answer-set structure;
`comparison_ready` also requires at least one case and a scored reference for
every case. Reports bind the public input, private reference/source package,
policy, builder, evaluator, and answer-file hashes. Older reports missing these
identities cannot establish a fair version comparison. The global `--output`
option is unavailable for these two commands; use `--report` for evaluation.
Both commands use new output paths and leave the current calculation unchanged.
This offline representation does not migrate production outcome/event records:
`learning outcome`, imports, revisions and retry gates retain their existing
`root_cause_status` schema and behavior. An offline score is not an outcome event.

## Generate a new frozen-case diagnosis (round one)

`learning diagnose` is a separate, versioned advisory interface. It loads one
existing schema-2 case bundle, verifies its source bytes and selected JSON
values, and attempts one new model turn through the existing `LiveStdio`
managed ChatGPT account and native Windows MXC admission. It never replays saved
answers. The model sees only the selected public scalars, not private references,
whole source documents, other cases, subsequent outcomes or the workflow store.
The one supplied tool, `read_frozen_evidence`, takes evidence IDs only and
reverifies their original source observations. Input strings are data rather
than instructions. Shell, network tools, delegation and scientific execution
remain unavailable to this interface.

```powershell
python -m scripts.ts_strategy_engine.cli learning diagnose --bundle FROZEN_BUNDLE --case-id CASE_ID --checkpoint 2026-09-02T10:19:58Z --output-dir NEW_RUN --model EXPLICIT_AVAILABLE_MODEL --effort medium --codex ABSOLUTE_CURRENT_CODEX_EXE --auth-home EXISTING_ISOLATED_CHATGPT_HOME
```

The checkpoint is an explicit, timezone-bearing observation cutoff supplied by
the operator; the interface does not authenticate historical clocks or assert
that a selected document was available then. The bundle author must exclude
later repair conclusions before building it. Existing case provenance and
reference rules are unchanged: `incomplete` can represent a real case without
an approved scoring reference; it is not a fabricated synthetic reference.
Round one labels usage `calibration` and makes no blind-test claim.

Default semantics attempt generation. `--probe-live` follows the **same**
executable, isolated configuration, MXC canaries, initialization, effective
permissions, MCP/account checks and thread start, then closes before
`turn/start`. `LIVE_ADMITTED_NO_TURN` is not model generation. The old
`workflow-run-review` preparation/probe semantics and deterministic
`advise-next` are unchanged. Local protocol commands now inherit the same
isolated child environment as the live launch; no personal configuration is
edited, authentication copied, key added or permission check bypassed.

A successful run writes the first raw `model-response.txt`, a validated
schema-2 `answers.json` with its selected `public.json`, new schema-1
`recommendations.json`, deterministic one-page `review.md`, and
`run_receipt.json`. Recommendations separate observations, up to three
hypotheses, missing evidence, one first check with conditional outcomes,
conditional proposals, cost and scientific scope. No retrieval is performed
in round one; `method_sources` must be empty. Unknown cost has null quantity
and unit. IDs/input hashes are host-owned, not generated by the model.
The answers/public pair can be consumed by the existing `advise-next`.

Malformed responses and invalid/unread evidence citations fail closed without
format-repair turns or valid answer publication. Citation validation establishes
identity and availability, not semantic support or scientific causality.
`causal_claims_scientifically_validated` and `execution_authorized` remain
false. The learner does not change a strategy, owner validation, registry,
scheduler, SPC or the main consumer's pinned producer revision.

Failures produce an explicit blocked report/receipt and append-only journal.
Admission stages, local command exit codes/stderr, actual thread/turn identities,
host tool completions and model completion are recorded separately. Safe stderr
retains original bytes in base64, including Windows codepage errors; sensitive
stderr is redacted. A blocked run never creates a new diagnosis or treats native
canaries as model calls. Synthetic transport is available only to software
tests and is visibly labelled; the CLI exposes no synthetic-success option.

An immutable, prompt-hashed scalar workspace permits repeated use of the same
case with fresh output directories without overwriting its isolated auth config.
Changed case/prompt scopes require an explicitly configured isolated home; the
runner rejects a mismatching config rather than rebinding arbitrary permissions.
An absent account requires the user's official login in that same home. A
desktop ChatGPT session alone is not proof that this isolated home is logged in.

Software validation: `tests/test_ts_diagnosis.py` plus the existing case,
next-review, workflow and review-runner suites. Actual local admission evidence
and remaining limitations are recorded in
[the round-one implementation record](../../docs/reviews/rsi_round1_20261028.md).

## Read-only next-review advice (Phase 3B)

Use saved, structurally valid schema-2 public cases and diagnosis answers to produce
bounded next-review suggestions without opening the registry or executing jobs:

```powershell
python -m scripts.ts_strategy_engine.cli learning advise-next --public FROZEN_PUBLIC.json --answers SAVED_ANSWERS.json --expected-public-sha256 FROZEN_PUBLIC_SHA256 --report NEW_ADVICE.json
```

This command requires the explicitly reviewed public-input hash, rechecks every
public case identity and the answer/evidence-ID structure, and fails closed on
missing or malformed answers. It reuses the current policy routes; it cannot
establish scientific causality. `unknown` prioritizes gathering cause-specific
evidence; `hypothesis` asks for a test of the stated claim; `confirmed` asks for
a scope review. Geometry and optimizer cases with a non-unknown cause may list
existing TS strategy *fields to review*, never settings values or job actions.
The advice is always `ADVISORY_ONLY_NOT_AUTHORIZED` and marks source-file
reverification, scientific-cause validation, and TS-change authorization false.
All scientific review and any actual method change remain with the owning
module, existing strategy proposal checks, and sole execution gate. No LLM,
database, SSH, training, scheduler or VASP calls are made by this command.

## Saved historical decision replay (Phase 3C)

```powershell
python -m scripts.ts_strategy_engine.cli learning replay-history --request REPLAY.json --expected-request-sha256 REPLAY_FILE_SHA256 --report NEW_REPLAY_REPORT.json
```

This is an artifact audit, not an executor or a new strategy store. It reads no
registry and never calls `read_events()`: that function resolves outcome revisions
to their latest state, which would leak later knowledge into an earlier decision.
Keep original snapshots and Phase 3A/3B materials unchanged. All report paths are
write-once. Input and source JSON snapshots are limited to 1 MB each.

The explicit schema-1 request contains `public`, `answers`, and `advice` file
references (`path`, file `sha256`), `traces`, and `unreplayable`. Phase 3B advice is
recomputed in an isolated temporary directory using its existing validator and
must match the saved advice exactly, including its current policy binding.

Each trace has these fields (see the synthetic local test fixture for an example):

- `case_id`: one frozen public/advice case; its `group_id` is the recorded task ID.
- `decision`, `action`, and each `after` entry: `event_id`, `at`, `job`, `fact`.
  Each of the last three is an existing observation (`path`, `sha256`, JSON
  `pointer`, exact `value`) from the same timestamped snapshot. Times require
  explicit timezones. Decisions and subsequent observations must be ordered;
  duplicate event IDs, unrelated jobs and tasks fail validation.
- `evidence`: `evidence_id`, `source` observation, and `links`. Links are a chain
  of observed file hashes starting in the decision snapshot and ending at that
  evidence source. Every public evidence item must match its original scalar
  value, pointer and source hash and have this decision-time availability witness.
  A later revision cannot replace an earlier source through a final-state reader.
- `task`, `failure_job`, `request`: observations binding the failure task/job and
  the decision snapshot's request hash. `action_parent` observes the decision's
  file hash in the action snapshot; `action_task` observes its task identity.
- `authorization`: null or `event`, `binding`, `task`. The binding is the
  authorization file hash recorded in the action; its true scope fact, task,
  failed job and pre-action time are checked. This establishes a saved historical
  binding only, never current authorization or execution-gate acceptance.
- `costs`: observations from `after` snapshots, using existing `gpu_hours`,
  `vasp_core_hours`, or `force_calls` validation. Missing costs stay unknown.
- `recorded_classification`: null or `/outcome/failure_class` from an existing
  saved historical import request. Its task and failure-source hash must match.
  It is a retrospective comparison only, excluded from decision-time evidence.

`unreplayable` lists additional `case_id`, nonempty `evidence_gaps`, and optional
known `sources` (`path`, file `sha256`, checked without using them as past evidence); incomplete
traces with null decision/action or no subsequent observation also return
`UNREPLAYABLE`. Missing or stale bound files, invalid temporal links, mismatched
advice and corrupt identities reject the request without publishing a report.

The report separates the saved `next_review`, actual action facts, retrospective
classification/route agreement and remaining semantic review. Unmatched or
unverifiable classification withholds TS field hints. No settings values, method
proposal, model-error conclusion or execution authority is generated. Prior
same-task/request cases are repeat clues only: the full environment/input retry
condition is not established, so this feature never creates an exact-input ban.

Local saved-material audit, 2026-10-10: one real trace covered GPU 1347's runtime
failure, the 2026-08-29 01:19 +08 retry review, 01:20:30 submission of GPU 1348,
and its later saved path review. The source directory is
`calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/gpu_dual_model_complete_path_rebuild_v10_nonabsolute_guards_20260829/`;
the classification came from `outputs/ts_strategy_learning_20260905/historical_gpu_1347_request.json`.
Failure, review and action file identities were respectively
`8ef3e785c603fb2b8bd0917db2bc2c7d00a8988a3967cfe6cb122239a3fba34b`,
`1e6788cec00e01a7f0307ee0cbf8a7b0e09299076fa010cf10ee6711642094ff`, and
`bcebd69b16befd2326ac7019b95001928ea19106f0a82ccf6e54b3b0d0b1265d`.
GPU 1508 was `UNREPLAYABLE` in the inspected prepared case: its saved failure
review did not establish a corresponding next action. Imported inputs were null
and costs empty. These private/local calculation artifacts are not distributed
by this source change. The new runtime answer was a retrospective reconstruction,
not a blinded Agent evaluation or a new Gold reference. Only synthetic tests
cover repeated-request behavior and alternative diagnostic priorities. No real
repeat-input success, counterfactual success rate, saved compute or optimal budget
is established; original timestamp claims are verified as stored records, not
independently authenticated clock observations.

## Local workflow review-order loop

### Independent read-only review adapter

`workflow-run-review` handles one arm of an already frozen local trial. It does
not change P0/P1, run both arms, accept a policy, generate paths, or run a model
by default. A new output directory is mandatory. Source IDs resolve only through
the frozen material manifest; lexical escapes, symlinks/reparse points, stale
hashes, reference answers and workflow decision files are rejected. The model
prompt contains the public case and selected field order, never the saved answers
or the other arm's outputs. The two host tools bind their own field; they accept
only evidence IDs, with no shell, path, expression, write or submission parameter.

Use a schema-1 runner request (separate from the immutable trial):

```json
{
  "schema_version": 1,
  "trial": {"path": "ABSOLUTE/TRIAL.json", "sha256": "ACTUAL_FILE_SHA256"},
  "candidate_id": "EXISTING_P1_ID",
  "policy_id": "EXISTING_P0_OR_P1_ID",
  "scope": "EXISTING_SCOPE",
  "case_id": "EXISTING_CASE_ID",
  "task_id": "EXISTING_TASK_ID",
  "input_sha256": "EXISTING_INPUT_SHA256"
}
```

`TRIAL.json` must retain the existing `inputs`, `evaluation_contract`, `scope`,
`provenance` and `materials` (`evidence_id -> path/sha256`, with original-source
metadata permitted). Parent/candidate identities and their existing advice engine
bindings are validated by the workflow lifecycle. No second registry is created.

```text
python -m scripts.ts_strategy_engine.cli learning workflow-run-review --store LOCAL_STORE --request ARM_REQUEST.json --output-dir NEW_ARM_DIRECTORY --model EXPLICIT_MODEL --effort medium
python -m scripts.ts_strategy_engine.cli learning workflow-run-review --store LOCAL_STORE --request ARM_REQUEST.json --output-dir NEW_PROBE_DIRECTORY --model EXPLICIT_MODEL --effort medium --timeout-seconds 120 --codex ABSOLUTE_CODEX_EXECUTABLE --probe-backend
```

`--probe-backend` invokes local version/help/features/schema generation and a
fresh ephemeral stdio thread, but sends **zero model turns**. It uses a fresh
child-only Codex home without copying authentication. It records the executable
hash, actual session response, permission settings, disabled native features,
MCP inventory and an innocuous outside-workspace file-RPC probe. No installation,
upgrade, environment repair or network/model test is performed.

Compatibility verified locally with Codex `0.162.0-alpha.17.2`: stdio initialization,
new threads, dynamic tool specs and schema-2 host collection are supported.
However, the legacy `readOnly` policy has no evidence-directory read allowlist;
the native client file RPC can read the outside canary. That RPC uses host
authority and is **not** proof of a model escape. The backend exposes no verified
native-tool inventory/read-confinement attestation here. Disabled features and
an empty MCP list do not prove that all reading channels are restricted.
That legacy diagnostic remains insufficient for `--execute`. The explicit live
branch now requires a separately generated named filesystem configuration,
native MXC read/deny/write probes, actual effective configuration confirmation,
an empty MCP surface and managed ChatGPT-account authentication. Every missing
condition produces `BLOCKED` before a model turn. There is no override flag.
A new session establishes context independence only, separately from read
confinement and log completeness.

The task-owned authentication home starts with only
`cli_auth_credentials_store="keyring"`. Complete official `codex login
--device-auth` in that home using a child-process `CODEX_HOME`, before execution.
No personal config or credential files are copied. The runner promotes only this
exact bootstrap to its explicit configuration; arbitrary existing config is
rejected. Each configuration is bound to its workspace and evidence paths, so
it cannot be silently reused for a different arm. Authentication must report
`type=chatgpt`; API-key and unauthenticated modes remain blocked.

```text
python -m scripts.ts_strategy_engine.cli learning workflow-run-review --store LOCAL_STORE --request ARM_REQUEST.json --output-dir NEW_ARM_DIRECTORY --model EXPLICIT_MODEL --effort medium --auth-home ISOLATED_AUTH_HOME --max-tool-calls 2 --timeout-seconds 180 --execute
```

`review_live` defines two scopes: the outer App Server client runs under MXC with
only runtime/auth-state write access plus read-only workspace/evidence access;
model commands select a separate named profile that denies auth-home access,
filesystem writes and command networking. Both deny other filesystem paths,
with explicit `:minimal` runtime read exceptions. The existing managed OpenAI
authentication route is configured under a task-owned provider label with zero
HTTP/stream retries; it has no API-key variable or alternate base URL. The same
service is used, not a new paid API. Known native tool features remain disabled;
unexpected RPC tools or native activities terminate the review. These controls
do not establish an exhaustive inventory of every model-visible capability.

The real branch performs one fresh thread and one `turn/start`, processes actual
`item/tool/call` requests, returns host-read evidence, and exports the existing
schema-2 projections. `run_mode` distinguishes `real_codex` from
`synthetic_transport`; material `provenance` is unchanged. The command limit can
be narrowed from eight to two, and the process watchdog enforces the supplied
wall-clock limit. There are no automatic additional turns or agent retries.
Startup stderr is captured with credential filtering, process exit is recorded,
and concurrent host journal writes are serialized.

Native probes are host-initiated tests of the sandbox, not model tool calls.
The client `fs/readFile` API is a separate host capability. Do not report either
as an observed model escape. `whole_filesystem_isolation` remains `UNKNOWN`;
only the tested read/write boundary and host evidence-ID whitelist are reported.

Current local observation (2026-10-13): the native MXC canary matrix passed, but
the outer sandboxed App Server ended its stdout before the `initialize` response.
The first EOF/protocol record was retained, and **zero `turn/start` requests**
were sent. The original probe did not retain stderr, so its startup cause is
unknown; subsequent code preserves stderr for a separately authorized diagnostic.
The real model path is therefore **not accepted or demonstrated**. No scientific
review or workflow benefit was evaluated. No retry follows this failure.

Official references: [permissions](https://learn.chatgpt.com/docs/permissions),
[native Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox),
[App Server authentication](https://learn.chatgpt.com/docs/app-server).

Offline synthetic transport tests exercise the actual host tools, real temporary
file parsing, call-ID retransmission deduplication, independent duplicate calls,
stream interruption, forbidden tools and an eighth-call limit. The stdio child
has a hard process watchdog (default 120 seconds, explicit maximum 3600). A
protocol retransmission consumes no second operation; an independent failed
operation remains counted. A ninth operation is denied and journaled. One model
turn only; no resume/fork, subagent or automatic retry.

The host flushes `journal.jsonl` before operations and preserves protocol arrivals,
start/completion/failure receipts, timestamps, source identities and real returns
(credential-like values redacted). Each action binds task/input/contract/policy,
session/turn/call and a host event ID. `raw.json` and `trace.json` are write-once
schema-2 projections. Interrupted runs retain all actions and raw checks, but
export an incomplete check projection so the existing evaluator cannot qualify
them as complete. Final model prose never sets a check. Only the narrow
deterministic checks `source_and_task_identity`,
`interpolation_strategy_evidence_read`, and `initial_images_evidence_read` can be
set by these host operations. Other predeclared checks (including existing real
chemical/review-completeness checks) remain `null`, without rewriting the frozen
contract. Complete transport recording alone is not complete scientific review.
Prepare/probe mode produces no review trace and cannot be bound as an evaluation.

```text
python -m pytest -o addopts= -q tests/test_ts_workflow_review_runner.py
```

These are synthetic software tests, not a real P0/P1 experiment. Trace pairs can
use the existing `workflow-bind-evaluation` entry; missing human judgments remain
`NEEDS_MORE_EVIDENCE`. Private artifacts, credentials and transcripts stay local.
GPU1508 remains paused; this interface provides no calculation execution authority.

This loop changes only the order of the existing `advise-next` TS-field review
hints. It derives those fields from `next_review_core.review_field_orders()`, checked
against the existing strategy settings schema. It cannot change a parameter
value, diagnostic route, causal status, evidence requirement, scientific check
or execution permission. Unknown causes still receive no TS-field hints.
GPU1508 execution remains a separate paused branch.

There is no database, global default or registry/index for this loop. An explicit
local `--store` contains content-addressed `policies/ID.json`, at most one
`evaluations/CANDIDATE_ID.json`, and one `decisions/CANDIDATE_ID.json`. Writes
are exclusive and identical repeats are idempotent; conflicting writes fail.
A short exclusive `.write.lock` serializes mutations. A leftover lock after a
process crash blocks writes; investigate ownership before removing it manually.
Status is derived from these artifacts. Engine/policy, parent, input, source,
evaluation and decision bindings are rechecked on use. An accepted successor
makes its parent unavailable for new proposals, while that parent remains
readable as a control. Use a new baseline after code or evidence changes; old
artifacts are retained and never silently migrated.
The dependency direction is `next_review` -> `workflow_improvement` -> shared
advice/evaluation code. `next_review_core` owns diagnosis validation and advice
construction; `workflow_evaluation` owns source identity and paired comparison.
Neither imports the workflow selector or its public advice wrapper.

Run all operations through the existing learning entry point:

```powershell
python -m scripts.ts_strategy_engine.cli learning workflow-baseline --store LOCAL_STORE --request BASELINE.json
python -m scripts.ts_strategy_engine.cli learning workflow-propose --store LOCAL_STORE --request CANDIDATE.json
python -m scripts.ts_strategy_engine.cli learning workflow-status --store LOCAL_STORE --policy-id RETURNED_ID
python -m scripts.ts_strategy_engine.cli learning workflow-bind-evaluation --store LOCAL_STORE --request EVALUATION.json
python -m scripts.ts_strategy_engine.cli learning workflow-decide --store LOCAL_STORE --request HUMAN_DECISION.json
```

`BASELINE.json` has exactly `scope` (nonempty trial/review name), `provenance`
(`saved_real` or `synthetic`), `inputs` (`public` and `answers`, each a file
reference), and `observations` (nonempty existing scalar JSON observations).
File references have `path` and file `sha256`; observations additionally have
`pointer` and exact-type `value`. The schema-2 input pair goes through the
existing diagnosis validator. Every public evidence value must have a matching
original-source hash, pointer and value in these observations. This captures P0
from code and files, not from a chat reconstruction.

`CANDIDATE.json` has exactly `parent_id`, `scope`, `changes`, `rationale`,
`observations`, and `evaluation_contract`. `changes` maps exactly one existing
failure class to a full, nontrivial permutation of that class's existing review
fields. For example, reversing the two geometry hints is structurally permitted;
its usefulness still needs task-specific evidence. The parent must be P0 or an
accepted candidate, in the same frozen scope and input set. Evidence and a
specific rationale are mandatory. The contract is fixed when proposing:

```json
{
  "method": "paired_saved_review_traces_v2",
  "rules": {
    "all_required_checks_pass": true,
    "no_per_task_regression": true,
    "strictly_fewer_review_actions_on_at_least_one_task": true
  },
  "tasks": [{
    "case_id": "ACTUAL_CASE_ID",
    "task_id": "ACTUAL_PUBLIC_GROUP_ID",
    "input_sha256": "ACTUAL_CASE_INPUT_SHA256",
    "required_checks": ["TASK_SPECIFIC_PREDECLARED_CHECK_ID"]
  }]
}
```

Declare the necessary diagnostic-priority and review-completeness checks before
evaluation. The tasks must cover the frozen public input exactly. This first
method compares counts of **recorded review actions**, only when every
predeclared check has a source-bound true observation on both sides. Each task
must have no increase in actions, and at least one must have fewer. Any failed
check or per-task increase returns `NOT_SUPPORTED`; aggregate gains cannot hide
a regression. This is a bounded workflow-effort measure, not a correctness
oracle or a TS-success, text-match, replay-route, time or compute-cost score.
Check semantics and faithful collection still require human review; hashes
establish identity, not scientific truth or reviewer authentication.

Generate saved advice for both policies with the same frozen public/answers:

```powershell
python -m scripts.ts_strategy_engine.cli learning advise-next --public PUBLIC.json --answers ANSWERS.json --expected-public-sha256 PUBLIC_CANONICAL_SHA256 --report NEW_ADVICE.json --workflow-store LOCAL_STORE --workflow-policy RETURNED_ID --workflow-scope DECLARED_SCOPE --offline-evaluation
```

`EVALUATION.json` has exactly `schema_version: 2`, `candidate_id`, `parent_id`,
`scope`, `contract_sha256`, `provenance`, and `pairs`. Each pair contains
`case_id`, `parent` and `candidate` trace file references (or null for missing
traces). A trace file contains exactly `schema_version: 2`, `provenance`,
`policy_id`, `scope`, `contract_sha256`, `case_id`, `task_id`, `input_sha256`,
`advice` (the saved offline advice file reference), `source` (one frozen raw
event-log file reference), `actions` and `checks`.
Each action has a unique `event_id`, an allowed `field`, and a scalar source
`observation`; the fields' first visits must follow the selected complete order.
Distinct original actions count individually. Each check has `check_id` and a scalar
`observation` whose value is true, false or unmeasured null. Retain raw collection
records. Advice is reconstructed with the existing validator and compared in
full; different tasks, versions, inputs, methods, orders and stale sources fail.
`improved: true` alone is never an evaluation.

The raw source is also schema 2 and contains exactly `schema_version`,
`provenance`, `policy_id`, `scope`, `contract_sha256`, `case_id`, `task_id`,
`input_sha256`, `actions`, and `checks`. Its identity must match the trace and
predeclared task/experiment. Each raw action has `event_id`, `sequence` (its
0-based array position), `field`, and scalar `result`. IDs are unique in that
log. Each raw check has `check_id` and boolean/null `result`. The trace observes
`/actions/INDEX/result` or `/checks/INDEX/result` in this exact bound file and
must retain the original ID, field and order. A byte-identical path alias is
the same source event. Relabeling, repeated references, wrong source ownership,
and out-of-order records are rejected; incomplete coverage cannot qualify for
review. Equal result text on two distinct source events still counts twice.

This is a version boundary, not a production event-schema change: schema-1
evaluations/traces and logs without verifiable ownership are rejected, never
assigned invented metadata. The policy and decision artifact formats stay at
schema 1; saved evaluation bindings use schema 2. Engine bindings now include
the shared advice and evaluation module hashes. Preserve old artifacts; use a
new baseline/contract and source-bound records for this version. Only synthetic
fixtures may be regenerated with explicit synthetic event identities.

No result means `WAITING_FOR_EVALUATION`, with null comparison/evaluation ID.
Partial results return `NEEDS_MORE_EVIDENCE` and explicit gaps without freezing
an incomplete binding. Preserve the partial input and later submit a new,
complete source file. A complete comparison is bound once, including unsupported
results. Supporting evidence yields `AWAITING_HUMAN_REVIEW`, never acceptance.
There is no automatic evaluator, Gold creation, model call, scheduler or retry.

`HUMAN_DECISION.json` has exactly `candidate_id`, `evaluation_id` (returned by
binding, or null for rejection before evaluation), `decision` (`ACCEPT` or
`REJECT`), `reviewer`, `reason`, and `actor_kind`. For real records the actor
is `human`; a synthetic fixture requires `synthetic_fixture`. Acceptance needs
the exact supporting evaluation. Rejection retains all artifacts. Conflicting
decisions fail. This implementation task makes no real acceptance decision.

An accepted real version can be selected by the same explicit `advise-next`
flags **without** `--offline-evaluation`, only in its exact frozen review scope.
The output records `workflow_strategy` identity, scope, provenance and mode.
Unaccepted candidates require explicit offline preview; rejected candidates
cannot be selected. Synthetic versions always require offline mode, including
after a simulated acceptance. With no workflow flags, the original report and
ordering remain unchanged. A selected version never authorizes computation or
clears STOP, and is never installed into the production Agent or global config.

The runnable end-to-end synthetic examples are also the regression tests:

```powershell
python -m pytest -o addopts= -q tests/test_ts_workflow_improvement.py -k end_to_end
```

They exercise P0 -> P1 -> waiting -> paired synthetic traces -> simulated human
acceptance -> actual changed `advise-next` order -> P1 as the next parent.
These fixtures establish software behavior only. No real workflow gain, TS
success, cost saving or GPU result is established by them.

## Warm start and reference methods

Install local orchestration dependencies with `python -m pip install -e ".[dev,neb,sella]"`.
The learning store requires registry schema 8. For an isolated trial, initialize
an explicitly selected scratch database with
`python -m scripts.init_registry --db archive/strategy_sandbox.sqlite3` and pass
`--database archive/strategy_sandbox.sqlite3` to the `learning` commands.
Existing project databases require a reviewed backup and explicit migration;
reading history or running a submission preflight never silently migrates them.

The optional `matris_ml_neb_sella` strategy and its shared VASP learning loop
are described in [SELLA_BRANCH.md](SELLA_BRANCH.md). It uses standard Sella on
the current MatRIS checkpoint; `aqcat25_ba_sella` remains a separate historical
model/optimizer branch. Changed code/policy hashes require a new baseline
capture; existing variants and failure history are preserved as immutable history.

```powershell
python -m scripts.ts_strategy_engine.cli learning methods
python -m scripts.ts_strategy_engine.cli learning capture --workdir EXISTING_NEB --task-id REACTION_ID --source checkpoint_manifest=EXISTING_CHECKPOINT_MANIFEST
python -m scripts.ts_strategy_engine.cli learning history
```

`capture` reads the actual INCAR and path-generation report, checks the image
count, and binds every numbered POSCAR, input file and selected workflow source.
It records the current five-image policy when five internal images actually
exist; it does not reset the model epoch, create images, or restart a job.
Additional `--source ROLE=PATH` entries bind existing model manifests, reaction
contracts, checkpoints and prior submission records. No checkpoint version or
scientific status is inferred when those sources are absent.

The returned `variant_id` identifies the baseline. IDs, parent IDs, input hashes
and checkpoint references are separate. Source references retain their hashes;
if original files change or disappear, a new proposal/application requires a
fresh baseline instead of silently reusing stale sources. Baseline capture is
not a backup of those source files or remote checkpoints.

The default attempt budget is five recorded attempts per task. This is only an
accounting cap, not GPU/VASP authorization. `--attempt-budget` explicitly sets
it when capturing a campaign. A general `baseline --request SPEC.json` accepts
exactly `task_id`, `settings`, `sources`, `cases`, `attempt_budget`; use it for an
explicitly reviewed imported policy or multi-case benchmark. `sources` maps
roles to existing paths; `cases` must be unique and include `task_id`.

AQCat25/BA-Sella is a **reference candidate generator**. Its historical job-737
report is referenced with a hash and is not a Grade-A result. The existing
Arkimede/Sella remote implementation and active-learning handoff remain its
integration points. Adding the reference does not establish a MatRIS+Sella
implementation, remote installation, benchmark result, or submission authority.

## One bounded proposal

`propose --request PROPOSAL.json` accepts exactly these fields:

```json
{
  "parent_id": "EXISTING_VARIANT_ID",
  "changes": {"initial_images": 7},
  "rationale": "Reviewer hypothesis explaining which observed failure this change addresses",
  "observations": [
    {"path": "ABSOLUTE_JSON_REPORT", "sha256": "ACTUAL_SHA256", "pointer": "/status", "value": "ACTUAL_VALUE"}
  ]
}
```

The numbers in this example are illustrative, not a recommendation for the
current calculation. Supported fields are `initial_images`,
`interpolation_strategy`, and `candidate_method`; their values are defined in
the policy schema. One field changes per proposal, at most two candidates per
parent. Scientific thresholds, INCAR values, model checkpoints, chemistry,
atom mapping and acceptance logic cannot be patched through this interface.
Changes to these belong to their existing modules and review protocols.

Every observation must match an existing JSON value at the supplied JSON
pointer and the file's current SHA-256. Unknown fields, invented pointers,
edited files, no-op changes and unsupported methods are rejected. Root-cause
interpretation remains explicitly attributed to the named reviewer.

```powershell
python -m scripts.ts_strategy_engine.cli learning propose --request PROPOSAL.json
python -m scripts.ts_strategy_engine.cli plan --is IS --fs FS --contract CONTRACT --workdir NEW_PLAN --strategy-variant VARIANT_ID
```

The normal endpoint, mapping and path checks still run. The variant applies to
its frozen task set only. Conflicting `--images` values are rejected. The
BA-Sella preference produces `NEEDS_BA_SELLA_CANDIDATE_HANDOFF_REVIEW`; combining
it with `--initialize-path` is rejected rather than silently running NEB.
Other method preferences are advisory until the existing execution gate allows
the requested method. A variant can never clear an earlier STOP decision.

## Attempts, failures and recovery

```powershell
python -m scripts.ts_strategy_engine.cli learning start-vasp --workdir VASP_INPUTS --kind ordinary_neb --variant-id VARIANT_ID --task-id REACTION_ID --attempt-id UNIQUE_ATTEMPT_ID
python -m scripts.ts_strategy_engine.cli learning outcome --attempt-id UNIQUE_ATTEMPT_ID --request OUTCOME.json
```

`start-vasp` runs the existing local preflight and records the actual input
identity. It does not submit. A registered `--source-calculation-id` is needed
before the attempt can be associated with a formal TS result.

For a GPU candidate or explicit resumption, `start --request ATTEMPT.json`
accepts `attempt_id`, `variant_id`, `task_id`, `kind`, `inputs`,
`parent_attempt_id`, and optional `source_calculation_id`. `inputs` maps roles
to existing files and must include the actual runtime request, model identity,
input structures and any environment evidence relevant to the diagnosis.
Resumption requires the same task and an existing `resume_checkpoint` entry.
Supported GPU kinds are `matris_ml_neb`, `aqcat25_ml_neb`, `aqcat25_ba_sella`.
VASP kinds require their full canonical input manifest. The GPU branch uses
this work-side check before handoff; the remote runner is not modified or
authorized by this feature.

An outcome has exactly these fields:

```json
{
  "status": "failure",
  "failure_class": "runtime",
  "root_cause_status": "confirmed",
  "deterministic": true,
  "reviewer": "REVIEWER",
  "observations": [{"path": "ABSOLUTE_JSON_REPORT", "sha256": "ACTUAL_SHA256", "pointer": "/failure_class", "value": "ACTUAL_VALUE"}],
  "costs": {},
  "ts_template_id": null
}
```

Status is one of `failure`, `unknown`, `cancelled`, `stage_pass`,
`ts_validated`. Root cause is `confirmed`, `hypothesis`, or `unknown`.
Classification and next-review routes are in the policy file. A runtime or
geometry failure does not establish model error. Even the `model_error` route
only refers to the existing active-learning entry, exact-structure VASP-error,
training-exclusion and held-out gates; it cannot authorize training.

Identical IDs and content are idempotent; conflicting content is rejected.
If an outcome interpretation was mistaken or subsequently reviewed, use
`learning revise-outcome --attempt-id ID --previous-sha256 HASH --request CORRECTION.json --reason TEXT`.
The correction uses the same validated outcome fields and bound observations.
It appends a new hash-linked outcome event; the original database row remains
unchanged. Readers resolve the latest verified correction for retry checks and
strategy summaries. A stale prior hash or concurrent history change rejects the
correction. A `stage_pass` correction never creates a TS template or job authority.
Concurrent history changes require re-reading before mutation. Outcomes are
appended once; unresolved attempts remain visible. A new attempt uses a new ID
and can point to its parent checkpoint, preserving the old record.

The retry key uses the method and actual input hashes, excluding directory
names, strategy labels and review-report timestamps. Confirmed deterministic
failures block the identical condition. Uncertain or stale evidence yields
`NEEDS_REVIEW`, never an invented diagnosis. Changed execution inputs are a
new condition; changing a filename alone is not. An environment correction
must be reflected in the bound runtime/preflight inputs, not just prose.
Failures on other inputs or tasks are not global method bans. Historical
failures without a reconstructible input identity must not be fabricated as
exact-input constraints.

`import-failure --request HISTORICAL.json` imports reviewed past evidence
atomically and idempotently. Its fields are `attempt_id`, `task_id`, `kind`,
`inputs`, `outcome` (the outcome format above). When the original execution
inputs cannot be verified, set `inputs` to null. The historical variant and
input identity stay null; the failure appears as task-local advice but cannot
create an exact-input ban or contribute to a variant's performance score.
Historical imports do not consume the new campaign's attempt budget.

The ordinary VASP submission preflight always consults this history, including
when no learning file is present in the workdir. Submission recomputes the
check and compares it with gate-bound evidence before remote operations.
Existing job cancellation and result validation remain independent. Old,
unsubmitted gate decisions need regeneration to include the new retry check.

## Comparison and limits

```powershell
python -m scripts.ts_strategy_engine.cli learning --output NEW_COMPARISON.json compare --baseline-id BASELINE_ID --candidate-id CANDIDATE_ID
```

Compare only variants with identical frozen cases and source/model baselines.
An existing, currently evidence-valid Grade-A template must match both the
reaction and the attempt's registered source calculation before it contributes
to TS success. The same calculation cannot credit two different variants.
`stage_pass`, scheduler completion and ML convergence never count as TS success.

Incomplete or stale evidence returns `NEEDS_MORE_EVIDENCE`. Lost validated
cases prevent promotion. With complete evidence, added validated cases take
priority; equal coverage can improve only with a non-regressing cost vector
and at least one strictly lower measured cost. Otherwise keep the baseline.
Even `ELIGIBLE_FOR_REVIEW` is neither automatic promotion nor execution authority.

Per-attempt incremental costs are `vasp_core_hours`, `gpu_hours`, `force_calls`.
Every supplied number must match a source observation with that field name.
Missing costs stay unknown, not zero. Queue wait and model uncertainty are not
invented from these metrics. Existing successful strategy templates remain the
route for solved reactions; expensive searches need not be replayed merely to
populate history. Fixed-comparison results cannot be fabricated for untested
variants, and this tooling makes no global-optimality or improved-success-rate
claim.

Validation: focused tests cover persistence, concurrency, warm capture, Sella
reference selection, invalid proposals, exact retries, stale evidence, VASP
preflight refusal, CLI wiring and TS-evidence boundaries. All test calculations
are synthetic local fixtures. Real GPU/Sella/NEB performance comparison remains
a separately authorized scientific task.

## Initial local adoption, 2026-09-05

- Baseline receipt: `outputs/ts_strategy_learning_20260905/baseline.json`.
  It binds the existing formal80 micro-NEB's five internal images, actual
  epoch-6 checkpoint, parent promotion/failure evidence and submission record.
- Reference-only BA-Sella proposal and receipt:
  `outputs/ts_strategy_learning_20260905/ba_sella_proposal.json` and
  `ba_sella_variant.json`. It has not been executed or scientifically compared.
- Imported `historical_gpu_1347` (runtime permission fault) and
  `historical_gpu_1508` (observed geometry-guard failure; root cause hypothesis).
  Both retain their documented reaction IDs. Original complete execution
  identities were not reconstructed, so they are advisory records with null
  input keys, not fabricated hard bans or scored variant outcomes.
- No job was started, resubmitted, stopped, or modified during adoption.
