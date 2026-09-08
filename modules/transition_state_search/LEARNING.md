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
