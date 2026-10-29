# Project research diagnosis and planning assistant

Ownership is registered in `configs/skill_routing.yaml`. This is a cross-cutting
RSI advisory/orchestration module under the existing `work` backend role in
`configs/execution_backends.yaml`. Scientific parsing, acceptance, strategies,
external retrieval and execution remain with their existing owners. It does
not replace `learning diagnose`, its failure routes, or the review-order experiment.

## Entry and three intents

```powershell
python -m scripts.research_assistant.cli run --goal "Research question" --workdir TASK_DIRECTORY --profile TASK_LOCAL_PROFILE
```

The goal is natural language. `--intent auto` is the default; optional intents
are `diagnose`, `compare`, and `plan`. There is no mandatory `failure_class`.
The work directory and optional additional scopes determine available material;
the system inventories files and prepares source snapshots on demand. A local
nonsecret profile pins the already admitted `codex`, `auth_home`, `project_root`
and optional `output_root`. Native permissions and credentials cannot be supplied
through this profile. Explicit CLI values take precedence. The optional installed
console entry is `research-assist`; no install is needed for the module entry.

Outputs default to a new directory outside the input project tree. No existing
result is overwritten. This task's concrete local wrapper/profile are recorded
in its implementation/acceptance report; credentials are never copied there.

## Continue the same research question

```powershell
python -m scripts.research_assistant.cli resume --from-run PREVIOUS_RUN --update "New evidence or context" --profile TASK_LOCAL_PROFILE
```

The original goal and question ID persist. The parent goal, candidate options,
unfinished checks and separate usage feedback are bound to immutable snapshots.
Additional `--scope` directories expose new material without replacing the old
scope. Prior model judgments are historical context, not current E evidence.
`continuation.json` records per-source current availability and SHA-256 checks.
Changed/missing sources or changed tool/dependency versions require rechecking.
An intact previous snapshot, unchanged source bytes, compatible scope and exact
tool implementation identity permit reuse only through a recorded host request;
reused results are not independent corroboration. Source hashes are still read.

New outputs use protocol v2; v1 research artifacts remain usable as explicit
parents. The v2 result binds gaps and required artifacts to each option, and
`progress` explains changes against parent judgment IDs, checks completed with
current evidence, remaining checks and the next concrete product. These are
model judgments for owner review, not scientific acceptance. A failed run keeps
its journal, inputs, source versions and `research_state.json`; if it has no
final `research_result.json`, choose the latest completed parent explicitly.
No failed model call is automatically repeated.

## Registered host tools

| Tool | Existing owner reused | Role |
|---|---|---|
| `evidence.list`, `evidence.read` | bounded source/hash collection | Catalog IDs and directed excerpts/JSON pointers/tails |
| `vasp.inspect` | `vasp_result_gate`, `neb_agent.utils_vasp`, `aqcat25_calibration` | Existing SCF and complete-force parsing; conflicting views remain visible |
| `terminal.align` | existing last complete position-block parser and ASE MIC | Match the saved structure against actual OUTCAR coordinates |
| `structures.measure` | existing POSCAR/mapping checks and ASE geometry | Atom order, cells/constraints, explicit zero/one indices, distances/displacements |
| `structures.compare` | same POSCAR/MIC owners | Explicit atom pairs, adsorbate/selected-surface contacts and same-index target comparison; no inferred atom permutation |
| `history.search` | existing strategy event reader; local source search | Provenanced past attempts, reviews and feedback; immutable DB snapshot/copy only |
| `strategy.candidates` | existing contract/fingerprint/template ranking/strategy composition | Conditional candidates; no strategy or scientific acceptance |
| `methods.search` | existing BM25 ranker and catalysis-retrieval workflow | Local method/history text; approved record/vector retrieval when supplied |
| `workflow.draft` | same existing strategy composer | Source-bound unapproved strategy draft in a fresh output directory |
| `workflow.review` | `adsmind_lite.relaxed_analysis` with existing analysis rules | Branch-bound geometry review draft; reference/candidate connectivity, sources and unresolved owner checks |

Local text search is explicitly lexical/BM25, not semantic or production
structure retrieval. Whitelist JSONL plus reviewed precomputed query vectors
can use the existing owner hybrid workflow. Without vectors the records path is
diagnostic-only. This adapter does not download an embedding model, open an
uncontrolled web fallback, or claim that online database connectors are wired.
The existing whitelist, transferability and scientific gates remain required.
Missing inputs or optional dependencies produce explicit tool errors/gaps;
no guessed parameters or replacement acceptance criteria are created.

The shared OUTCAR owner `neb_agent.outcar_blocks` selects coordinates and forces
from one finite complete table, with block index, iteration labels, line span,
atom-count basis and completeness. The latest attempted table is retained
separately, including a partial tail or complete coordinates with invalid forces.
`aqcat25_calibration.parse_final_outcar` and the compatibility position reader
delegate to it. A last complete table is not automatically the last ionic state;
latest file TOTEN remains explicitly separate from the force-table binding.
VASP collection isolates source/INCAR/SCF/force/structure/stdout component errors,
retains successful observations and reports PARTIAL without hiding local errors.

For `structures.compare`, query is a JSON object with optional
`pairs_zero_based`, `adsorbate_zero_based`, `surface_zero_based` lists. By default
non-Fe atoms are the adsorbate and all Fe atoms are the comparison set; this does
not establish which Fe layer is exposed. Same-index compatibility is not proof
that atoms in different isomers have a chemically meaningful correspondence.
`workflow.review` requires two structure IDs and
`{"option_id":"BRANCH","adsorbate_zero_based":[...]}`. It generates a review
record with existing owner connectivity rules; it does not invent target identity,
INCAR parameters, cost, complete input packages or execution authority.

## Explicit request/result protocol

The model receives task-scoped source metadata and the registered tool schema.
It emits `kind=request` with bounded tool requests. The host resolves catalog
IDs, freezes original bytes, calls the registered owner functions, stores their
results and returns evidence IDs. The next model turn can update its reasoning,
ask for further evidence, or return `kind=final`. There are no case/job branches.

This uses the existing file-authenticated, guarded ChatGPT App Server route.
No native tools are supplied. Model turn starts, host requests, actual host
executions, reused duplicate requests and rejected native attempts are counted
separately. Native callback delivery remains unaccepted and is not claimed.
Original model responses are saved before validation; no format-repair or
selection retry is made. HTTP429 stops that run and preserves its first error.

The only configuration update is a checked replacement of one task data read
view by the current catalog. The old view is removed, no second scope is added,
and file authentication, auth-home denial, native profile/network settings and
disabled features must exactly match the previously admitted configuration.
Any other configuration difference rejects the run. Personal config, keyring,
API keys and credentials are never migrated or changed. The pre-update config
and exact scope replacement receipt remain local.

## Evidence, daily use and evaluation

Daily mode may read sourced historical reviews and experience as interpretations.
Source metadata is not a parsed scientific conclusion. Each tool result records
original path, SHA-256, frozen bytes, collection time and coverage; raw files
retained by the host are distinguished from selected model-visible observations.
Source mutation during or after collection blocks a final result.

Default inventory is bounded and expands on directed requests. Credentials,
private keys, `.git`, `.codex`, binaries/POTCAR and SPC are excluded. Archive
trees are not traversed automatically; a needed historical directory must be an
explicit scope. File, total-byte, request and round limits are recorded rather
than silently dropped. Missing within the searched scope means retention unknown,
not proof of non-generation. The latter needs actual production/control-flow evidence.

Evaluation mode requires a reviewed hash-bound file manifest and allows only
its files. Known answer artifacts and history queries are blocked; JSON evidence
reads require non-reference scalar pointers, retaining sibling isolation. The
manifest author still owns exclusion of later answers embedded in arbitrary
otherwise-allowed text and the historical cutoff; the software does not
authenticate past availability. Evaluation restrictions do not govern daily use.

## Output, drafts and feedback

`research_result.json` schema 1 (protocol v2) binds the original research goal and stabilizes
facts, uncertainties/availability, hypotheses, candidate options, conditions,
unknown/measured cost, risks, evidence/calculation plan, acceptance conditions,
new tool information and one recommended next step. Facts and options must cite
results actually returned by registered tools. Citation identity checks are not
semantic scientific validation. Empty options and unknown cost are allowed.

Drafts are source-bound candidates from existing workflows, never approved
inputs or job authority. This version connects the strategy-candidate draft;
complete INCAR/job packages and submission are not automatic. Reports preserve
owner-check conflicts and do not mix scheduler, electronic, ionic, geometry and
scientific acceptance. No threshold or calculation is changed.

`feedback --run RUN --request JSON` records adoption (including unknown), actual
tool effectiveness, repeated checks and later notes. A separate optional
hash-bound owner result reference preserves the scientific outcome boundary.
Optional `human_review_seconds` must be measured or null; optional
`adopted_option_ids` require explicit adoption of actual candidate IDs. Automated
runtime does not become human effort, and preparation/review time is unknown
when it was not measured.
Feedback never promotes a scientific result or approves a strategy. These
records can inform later tool selection/candidate ranking; automatic learning
or a ranking policy change is not claimed here.

## Thin SPC staging boundary

`spc-export --run RUN --spc-root SPC_SOURCE --output-dir NEW_DIRECTORY` reads the
actual SPC `CandidatePlanDraft` / `PlanningLLMResponse` contract and snapshots
its source hashes and dirty/head identity. It never writes SPC source or state.
With no reviewed bindings, it exports branch-specific fragments and actual SPC
schema errors for missing hypotheses, model, observables, falsification criteria,
tasks and trusted IDs. It does not pad those fields or label them accepted.

Optional `--binding JSON --planning-input FILE` supplies reviewed fields and
evidence mapping to an existing hash-bound `ScientificPlanningInput`. Binding
schema 1 includes `research_result_sha256`, `planning_input_sha256`,
`evidence_map` (RSI E ID to SPC evidence-ID list), and `branches` containing an
actual `option_id` plus reviewed missing `spc_fields`. It cannot override RSI
branch content or insert trusted evidence directly. The existing SPC proposal
builder and grounding validator check allowlists, claims, capabilities, gaps
and consistency. `OFFLINE_PROPOSAL_VALIDATED` means that validation only; SPC
materialization, independent approval and Plan/Execution Gates remain required.
No second diagnosis or scientific validation implementation is introduced.

Optional `selected_option_ids` selects existing branches for one bounded SPC
review artifact. A strict subset requires a nonempty `selection_rationale`.
Every alternative and its original conditions, risks, acceptance conditions and
gaps remains in `spc_mapping.json`; selecting a staging artifact does not select
the scientific program or approve a calculation.

## Continuation cache dependencies

Reuse binds the current tool implementation, exact source hashes and the inputs
actually examined. VASP directory actions bind the presence of their expected
input/output components, including absent optional files. Directory/global
searches additionally bind the current scope roots, bounded catalogue coverage
and directory membership. A newly persisted file, new material or wider search
coverage invalidates the affected result. Explicit immutable-file reads and
file-targeted searches do not inherit unrelated directory changes.

On every resume, reusable leaf bytes are frozen into the current run. Derived
search corpus receipts and geometry review drafts are rewritten into that run
with current snapshot paths and retained parent hashes/lineage. A legacy receipt
that points outside its immediate parent is recomputed conservatively. Three
rounds of reuse are covered by offline tests, including no-match searches.
Directory signatures are bounded; an incomplete signature disables reuse.
Changing the tool implementation also causes conservative re-execution.

The continuation output schema enumerates valid single `previous_ref` values;
combined or invented old judgment IDs remain invalid. Original failures are
retained, not repaired in place. Source-version or scope changes require a new
input/run record, not relabelling the previous attempt as unchanged input.

Current offline/live acceptance and remaining limitations are recorded in the
task implementation reports. Lifecycle status remains in the module map.

Implementation, concrete local entry, real tool traces and acceptance limitations:
[`docs/reviews/research_assistant_20261029.md`](../../docs/reviews/research_assistant_20261029.md).

Continuation, concrete review drafts, current SPC boundary and environment failure:
[`docs/reviews/research_continuation_20261029.md`](../../docs/reviews/research_continuation_20261029.md).

Cache continuity, C3 reaction choice sheet and real source-bound SPC review plan:
[`docs/reviews/research_c3_plan_20261029.md`](../../docs/reviews/research_c3_plan_20261029.md).
