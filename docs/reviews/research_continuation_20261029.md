# Continuing a research question and delivering reviewable options

## Repository and ownership

The isolated producer began clean at `00c76d872c7dca5584a477ba578b5db2f2eee2d0`
on `codex/research-assistant-20261028`. Work is on
`codex/research-continuation-20261029`. The main sbq123 checkout remains at
`5c5fed9`; the dirty `work` checkout and separate dirty SPC main checkout were
read as sources, not reset, committed or repaired. SPC source HEAD observed:
`44101f4752aadee459a7469b5b4d9e7b0d97d224`. Its current dirty contract bytes are
recorded separately from that HEAD; a committed version is not substituted for
the actual source contract.

`research_assistant` owns orchestration, review output and usage feedback.
`neb_agent` owns shared OUTCAR parsing; existing VASP/geometry/adsorption modules
retain scientific rules. SPC owns proposal grounding, materialization and
independent approval. There is no second diagnostic or scientific gate, no
scientific job operation, no threshold change and no main merge.

## Changes

- `neb_agent.outcar_blocks` binds coordinates, finite force values, atom count,
  completeness, iteration labels and source line span to one OUTCAR table.
  It retains the latest attempted table separately from the last complete valid
  table. Partial tails and complete coordinates with invalid/missing/nonfinite
  forces cannot replace the selected table's coordinates. The old force and
  position facades delegate to this owner. File-level TOTEN observations remain
  explicitly separate from force-table identity.
- VASP collection retains successful source/INCAR/OSZICAR/OUTCAR/SCF/force/
  structure/stdout observations and local component errors. A bad structure or
  force table produces PARTIAL observations, without suppressing independent
  stdout, process or electronic evidence. Parser observations are not final
  scientific acceptance or a scheduler query.
- `resume --from-run --update` preserves the question ID and original goal,
  binds parent artifacts/feedback, and exposes old judgments as historical
  context. Source locations/hashes, frozen snapshots, scope and tool/dependency
  versions are rechecked. Only compatible unchanged results are reused through
  recorded host requests. Hash checks still occur. Old E IDs cannot substitute
  for current evidence. Protocol v2 adds per-option blocking gaps and explicit
  changes/completed checks/remaining checks/next product; legacy v1 parents remain
  usable. Failed runs preserve their records and state, without automatic retry.
- `structures.compare` supports specified atom pairs, selected adsorbate/surface
  contacts and same-index target comparisons with units and zero/one indices.
  It does not invent an atom permutation, exposed layer or chemical identity.
  `workflow.review` reuses existing adsmind connectivity rules and creates a
  branch-bound geometry review draft with sources and pending owner checks;
  no calculation parameters, cost or execution authority are generated.
- `spc-export` reads and snapshots the actual SPC `CandidatePlanDraft` and
  `PlanningLLMResponse` contract. Explicit reviewed bindings to a hash-bound
  `ScientificPlanningInput` can use SPC's own proposal builder and grounding
  validator. Missing fields/trusted IDs remain branch-specific staging gaps;
  JSON shape validation cannot promote RSI observations to trusted SPC evidence.
  Neither SPC source/state nor its approval/execution logic is modified.

## Real research progression: C3

Local artifacts:
`C:\Users\86177\Desktop\fe110_rsi_experiments\research_continuation_20261029`.
`review_packet.md`, two `branch-review-*.md` documents and `review_index.json`
contain the human review bundle, original module draft references, host
supplements, feedback and hashes. `live_c3_continue_02/review.md` remains the
first final model answer; it is not overwritten by later host observations.

The parent was `research_assistant_20261028/live_c3_02`. This was daily
continuation, not a new blind test. Its old proposals, uncertainties and feedback
were explicitly supplied as history. Frozen source snapshots, new evidence and
model-visible tool projections are retained separately.

The real model used four turns and requested twelve host actions: VASP inspection
of two historical optimization sites, source listing/reading, directed structure
comparison and two owner-generated geometry review drafts. All twelve host actions
completed; native model tool calls were zero. There was no HTTP429 and no answer
repair or selection retry. Old tool versions required fresh observations, so
cross-round reuse in this actual model run was zero.

Concrete progression:

1. The 9629858 force and coordinates bind table 80, NIONS=51, header line
   675627 and atom rows 675629–675679. Its 0.860794918 eV/Å maximum movable force
   and 7.8752e-6 Å maximum MIC position mismatch to CONTCAR are same-table
   observations. The electronic parser disagreement remains unresolved.
2. Added 9629859 evidence also supports a separated CO/C2H2 geometry; its
   latest readable maximum movable force is 0.565336 eV/Å. The model explicitly
   leaves this force block's correspondence to its saved structure unverified.
   The two sites are not one trajectory or two independent proofs of the same
   event. Numeric force ordering does not establish cost or a continuation choice.
3. The 08 vertical input is byte-identical to the input already used by 9629858.
   It is not a new untried starting point. Existing fragment branches, another
   surface placement and different target isomers must be kept distinct.
4. Options are A: source/identity review for target 08; B: conditional fragment
   study; C05 and C07: separate original/revised input review for each isomer.
   Each has its own conditions, required evidence/product, risks and unknown
   cost. The model called `workflow.review` for C05/C07; both had one connected
   component and no detected input-to-input connectivity change under existing
   rules. This is not relaxed stability, correct bond-order or site acceptance.
5. After the first model answer, the host acquired the available C05/C07 pair,
   nearest-Fe and same-index geometry comparisons. They supplement the human
   branch documents but are not relabelled as evidence already provided to the
   model. Target isomer, revision/hold provenance, complete scientific inputs,
   budget and any scientific authorization remain pending.

The next concrete review product is therefore a target-confirmed branch sheet
with source hashes, connectivity/contact evidence, existing attempts, reviewer
comments and budget gaps. A researcher must choose the intended isomer/claim;
the assistant cannot substitute equal chemical formulas for that decision.

## Reuse and feedback

A fixed, host-only follow-up replay of the twelve actual requests reused nine
unchanged compatible results and performed three fresh directory actions.
It then made two new branch geometry measurements. Source hashes were still
checked. These are real-source software observations, not another autonomous
model round or a claim of reduced human effort. See `host_followup.json`.

The lightweight feedback record marks useful source-duplication detection and
review draft production as preliminary host observations. Adoption, selected
option IDs, actual human preparation/review time and later scientific result
remain unknown. Shared-source/repeated checks are recorded separately; feedback
does not approve a strategy or promote science.

## SPC contract and offline boundary

The actual C3 output was passed to the real SPC contract. `spc_actual/` records
source hashes, schema and per-branch missing fields. Its true status is
`BLOCKED_BINDINGS_REQUIRED`: trusted SPC source-evidence/claim/capability IDs and
reviewed hypothesis/model/observable/falsification/task bindings are absent.
Those are adapter/trust gaps, not proof that scientific material was never
generated. No fabricated fields or personal configuration were used to pass.

The positive integration test uses SPC's existing **mock offline fixture**,
actual models, proposal builder and grounding validator in a private pytest
directory. A second test supplies a fabricated reference and is rejected by
the same owner validator. These validate the thin mapping capability; they do
not constitute C3 grounding, formal plan materialization or independent approval.

## Environment failure and model-route evidence

The first reserved continuation stopped at admission because the old versioned
Codex binary path no longer existed. It started zero model turns and executed
zero host actions; `live_c3_continue_01` and its original profile/exit evidence
remain. A local installation check found the current versioned desktop binary,
`0.165.0-alpha.1.2`. A new nonsecret profile changed only the binary path, keeping
gpt-6.1-sol/medium, existing auth home, file storage, frozen-context and all
permission boundaries. No installation, API key, credential copy or native tool
mode switch occurred. The new attempt reran the existing admission checks and
is recorded separately as `live_c3_continue_02`.

The process exit code 1 remains recorded; the new receipt also shows App Server
was running immediately before host close. Model turn completion and service
cleanup are separate evidence. The public
[App Server documentation](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
likewise distinguishes completed turns from failed/interrupted turns; that
documentation is not used to override local admission or authentication checks.

## Verification and limits

Pre-live syntax/import checks, scoped Ruff and **368 related tests all passed**,
including owner parsing/partial-output tests, continuation/cache/invalidation,
legacy diagnosis/review-order regression, directed geometry/draft checks and
SPC positive/negative offline integration. The final related suite also passed
all 368 tests. The progress-citation guard passed five focused continuation tests.
The enhanced complete file-bound SPC adapter suite passed all four tests,
including valid proposal output and owner rejection of fabricated evidence.
That fixture initially supplied empty RSI conditions and was correctly rejected;
the fixture was corrected and its first failed JUnit retained. Final source
hashes match the actual live tool implementation; first answers are unchanged.
Logs remain under the artifact root; no full repository suite or science job ran.

Scientific quality and acceptance still need human owners. Native callbacks,
automatic remote/scheduler evidence collection and complete executable scientific
input packages are not newly connected. An absent final model result is not
silently replayed; `resume` selects an explicit completed parent. Profiles remain
pinned to an actual binary; an app update removing that path must be diagnosed,
not bypassed by weakening admission. Whole-filesystem isolation remains unknown.

## Repeat locally

```powershell
python "C:\Users\86177\Desktop\fe110_rsi_experiments\research_continuation_20261029\use_research.py" resume --from-run "C:\Users\86177\Desktop\fe110_rsi_experiments\research_continuation_20261029\live_c3_continue_02" --update "继续核对待查项；来源未变时复用已核验检查，更新分支方案和下一步产物。" --max-turns 4 --max-actions 12 --timeout-seconds 480
```

The task-local wrapper supplies the admitted profile; a new output directory is
created automatically. Add `--scope` for newly available source material. The
host-only geometry supplement can be included explicitly on a later round;
it was not part of the previous model checkpoint.

## Repository state synchronization

Start audit retained the existing managed TS projection drift and external
worktree ownership warning. End safe-only synchronization is recorded separately;
assistant checks are not used to hide or repair unrelated state-history failures.

The end `python -m scripts.state_manager.cli --root . sync --safe-only` returned
exit **2**, stderr `ERROR: state history source changed before proposal generation`.
There is no proposal ID or choice to select. Raw output and exit evidence are
retained in `state_sync.*`; synchronization is not passed. No unrelated state
history/projection repair was performed.
