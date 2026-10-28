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

## Registered host tools

| Tool | Existing owner reused | Role |
|---|---|---|
| `evidence.list`, `evidence.read` | bounded source/hash collection | Catalog IDs and directed excerpts/JSON pointers/tails |
| `vasp.inspect` | `vasp_result_gate`, `neb_agent.utils_vasp`, `aqcat25_calibration` | Existing SCF and complete-force parsing; conflicting views remain visible |
| `terminal.align` | existing last complete position-block parser and ASE MIC | Match the saved structure against actual OUTCAR coordinates |
| `structures.measure` | existing POSCAR/mapping checks and ASE geometry | Atom order, cells/constraints, explicit zero/one indices, distances/displacements |
| `history.search` | existing strategy event reader; local source search | Provenanced past attempts, reviews and feedback; immutable DB snapshot/copy only |
| `strategy.candidates` | existing contract/fingerprint/template ranking/strategy composition | Conditional candidates; no strategy or scientific acceptance |
| `methods.search` | existing BM25 ranker and catalysis-retrieval workflow | Local method/history text; approved record/vector retrieval when supplied |
| `workflow.draft` | same existing strategy composer | Source-bound unapproved strategy draft in a fresh output directory |

Local text search is explicitly lexical/BM25, not semantic or production
structure retrieval. Whitelist JSONL plus reviewed precomputed query vectors
can use the existing owner hybrid workflow. Without vectors the records path is
diagnostic-only. This adapter does not download an embedding model, open an
uncontrolled web fallback, or claim that online database connectors are wired.
The existing whitelist, transferability and scientific gates remain required.
Missing inputs or optional dependencies produce explicit tool errors/gaps;
no guessed parameters or replacement acceptance criteria are created.

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

`research_result.json` schema 1 binds the original research goal and stabilizes
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
Feedback never promotes a scientific result or approves a strategy. These
records can inform later tool selection/candidate ranking; automatic learning
or a ranking policy change is not claimed here.

SPC integration is deferred. A future thin adapter consumes this versioned
goal/evidence/hypothesis/options/acceptance contract; it must not copy diagnosis
logic. Current offline/live acceptance and remaining limitations are recorded
in the task's implementation report. Lifecycle status remains in the module map.

Implementation, concrete local entry, real tool traces and acceptance limitations:
[`docs/reviews/research_assistant_20261029.md`](../../docs/reviews/research_assistant_20261029.md).
