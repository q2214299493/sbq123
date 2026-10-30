---
document_class: CURRENT_AUTHORITY
as_of: '2026-09-09T00:00:00+08:00'
as_of_scope: B6 document review, not a live scientific observation
source_scope: published task projection or backlog; not a live task/queue query
source_version: 3a1bb3f461147a7dc9b5df5efca89de621d27f38
source_version_role: B6 base commit
source_branch: codex/b6-documentation-data-governance
evidence_kind: LAST_RECORDED_OBSERVATION
production_schema_version: NOT_VERIFIED_IN_B6
governance: docs/DOCUMENT_GOVERNANCE.md
---

# Backlog

Tasks are ordered by priority and should be handled one per Codex thread.

## Infrastructure

1. **P1 - Populate and validate the calculation registry with active true Fe(110) jobs**
   Register current clean-slab, gas, adsorption, and future endpoint jobs with
   source paths, status, inputs, outputs, final species, chemical events,
   plausibility status, final site classes, duplicate groups,
   compatibility-branch IDs, Excel promotion states, and review decisions. Use
   `skills/chemical-plausibility-gate/`, `skills/dataset-compatibility-gate/`,
   and
   `configs/adsorption_result_promotion.yaml` as the promotion gate. Done when
   every inserted value has a source and missing values remain explicit.
2. **P2 - Backfill durable historical calculations into the registry**
   Blocked until task 1 is complete. Done when the approved current-scope
   historical records have job status, file manifests, result provenance, and
   uncertainty markers.
3. **P1 - Complete production connectors for catalysis-data-retrieval**
   The semantic model and hybrid Top-5 ranker are already verified. Add source-specific adapters only where official APIs/downloads permit them; CatApp and OC20NEB/CatTSunami machine endpoints remain **Needs confirmation**. Done when live whitelist queries return five or fewer provenance-complete results without browser-only copying.
4. **P2 - Extend automated coverage for convergence and INCAR custodian CLIs**
   Add temporary-directory tests for setup/summary branches and split the custodian command dispatcher only when tests cover each mode. Done when generate/tune/validate/parse-errors/custodian-plan and representative convergence summaries run under pytest without live submission.
5. **P2 - Register post-processing smoke-test records**
   CATKINAS and Zacros example-run evidence exists locally, but the calculation registry has not recorded the commands, files, versions, outputs, and limitations. Done when the smoke tests are registered without promoting example results as project science.
## Scientific Work

1. **P2 - Validate AdsMind Lite carbide and oxide explicit-tag adapters**
   Build reviewed fixtures for lattice C/O roles, Fe oct/tet labels, hydroxylation, and tagged oxygen vacancies before enabling any automated high-risk site detector. Done when representative Fe5C2 and Fe3O4 cases pass role, confidence, and `needs_review` gates without guessing missing labels.
2. **P2 - Decide whether ordinary NEB is acceptable for CI-NEB**
   Done when the decision and evidence are entered in `docs/03_DECISIONS_LOG.md`.
3. **P2 - Prepare and run CI-NEB**
   Done when a reviewed CI input package is submitted and indexed. Blocked until task 2 approves it.
4. **P2 - Validate and grade the transition state by frequency and connectivity**
   Done when the converged TS has frequency eigenvalues/eigenvectors, target-mode assignment, geometry checks, positive/negative displacement connection tests, and an A/B/C grade under `docs/10_TS_VALIDATION_PROTOCOL.md`. Numerical soft-mode thresholds remain **Needs confirmation**.
5. **P2 - Define the kinetic data schema**
   Done when species, energies, reactions, barriers, rates, units, source paths, and confidence fields have machine-readable definitions and validation rules.
6. **P3 - Complete thermochemistry inputs**
   Done when validated frequencies, standard states, ZPE/enthalpy/entropy corrections, and TS imaginary-mode checks exist.
7. **P3 - Build the balanced reaction network and free-energy table**
   Done when all elementary steps balance atoms/sites and reference validated species, TSs, and forward/reverse free-energy barriers.
8. **P3 - Implement baseline mean-field MKM**
   Done when steady-state coverages, TOF, selectivity, site balance, and DRC are reproducible. Blocked until TS validation, kinetic schema, thermochemistry, and reaction-network tasks are complete.
9. **P3 - Decide whether coverage-self-consistent MKM is required**
   Done when coverage dependence is evidenced and interaction parameters/ranges are defined, or the module is explicitly deemed unnecessary.
10. **P3 - Build CATKINAS input/export templates**
   Done when validated kinetic-data records can generate traceable CATKINAS `INPUT_*` files for single/curve/map runs, with no hand-entered energies or missing provenance.
11. **P3 - Implement surface-reaction KMC if spatial effects matter**
   Done when lattice, events, diffusion, neighbor rules, rates, and detailed-balance checks exist. Blocked until the reaction/rate dataset is complete.
12. **P3 - Build Zacros 4.0 input/export templates**
   Done when validated lattice/site/event/rate records can generate traceable `simulation_input.dat`, `lattice_input.dat`, `energetics_input.dat`, `mechanism_input.dat`, and optional `state_input.dat` files.
13. **P3 - Define and implement the reactor model**
   Done when reactor type, feed, flow, conditions, catalyst loading, site density, units, and intrinsic rate source are specified and solved.
14. **P3 - Run sensitivity and uncertainty analysis**
   Done when influential parameters, uncertainty bands, robustness, and next refinement targets are reported.
15. **P3 - Define the broader long-term catalyst-agent scope**
   Done when systems, reactions, deliverables, and publication criteria are added to the project brief.

<!-- state-handoff:start task_backlog_events -->
## Managed Backlog

<!-- state-handoff:end task_backlog_events -->

## B7 governance follow-up (not started in B6)

Classify/characterize editable-build metadata and package resources before any cleanup.
The existing `sbq_catalyst_agent_workflow.egg-info/PKG-INFO` mismatch remains unresolved;
no deletion, reclassification event or state-transaction change is authorized by this note.

## RSI model-side evidence callbacks — follow-up, 2026-10-28

- Validate `host-tools` callback delivery under the current guarded Codex
  backend. Typed eager declarations were checked, but no real host callback
  completion was observed; retain the failed trials and diagnose this separately.
  Do not weaken native permissions or relabel frozen-context turns as tool runs.
  The explicit frozen-context diagnosis entry is usable independently; this item
  does not authorize scientific jobs, main integration or SPC changes.

## RSI job 1508 bounded snapshot check — completed, 2026-10-28

- Registered local and remote files agree. The restart metrics match the failed
  checkpoint and the bound writer saves restart/state before the guard observer.
  Independent MIC calculations locate the exceeding atom at zero-based 49,
  one-based 50, H, matching the original structure order and historical dual
  index fields. The separate step-267 snapshot was not found within the bounded
  locations; retention remains unknown. No calculation or further model call
  was made for this chain. The first two diagnosis-use goals are complete;
  resolving the whole path root cause is not a prerequisite for new-case use.
  See `docs/reviews/rsi_round3_20261028.md` and the local snapshot report.

## Research assistant follow-up — 2026-10-29

- Human owners should review the OH, C3 and Fe(110) advice/acceptance chains;
  software checks and source citations do not establish scientific success.
  Adoption, human effort and subsequent results remain unknown until feedback.
- Wire bounded remote/scheduler collection, online method connectors or complete
  workflow input packages only through their existing owners when needed. Native
  callbacks remain a separate unaccepted capability; do not widen permissions.
- Keep usage feedback distinct from scientific outcomes. Protocol v2 now supports
  continuation, branch-specific gaps and review drafts. A thin SPC staging adapter
  is offline-validated against its current contract; real C3 trusted bindings,
  formal materialization and independent approval remain pending. No automatic
  tool-selection/candidate-ranking policy change is implemented.
- Retain the existing state-sync source-history failure separately; no unrelated
  state repair or reopening of job 1508 root-cause work is authorized here.
  See `docs/reviews/research_assistant_20261029.md` for completed scope and limits.

## Continued research review — 2026-10-29

- Review the target isomer/claim and the actual C05/C07 branch packets before any
  scientific input/execution decision. Post-model host geometry observations are
  separate; uptake, human preparation/review time and scientific result remain
  unknown. Do not reopen job 1508 as a prerequisite.
- For SPC use, obtain explicit source-evidence/claim/capability bindings and
  reviewed missing plan fields against an actual ScientificPlanningInput; schema
  or mock-fixture validation is not C3 grounding or independent approval.
- First admission failed because the pinned desktop binary path disappeared.
  The current installed binary passed the same admission under unchanged file
  auth/permissions; old records remain. Diagnose later path/version failures,
  never weaken admission or silently choose another authentication route.
  See `docs/reviews/research_continuation_20261029.md`.

## C3 practical use follow-up — 2026-10-29

- Completed the resume presence/coverage invalidation and three-round source/
  corpus/draft binding fixes. The later C05/C07 geometry and original reaction
  definitions were supplied to a successful new model continuation. Keep all
  graph/reaction branches; choosing a minimum C07 review artifact does not select
  the scientific program. Review the real source-bound SPC plan and provide
  adoption/priority/time feedback when known. See
  `docs/reviews/research_c3_plan_20261029.md`.
- Actual source bindings and owner materialization now exist for that one local
  unapproved C07 review plan. Independent scientific review/approval/execution
  gates remain pending. Do not generalize this to complete C3 readiness or SPC
  production integration.
- Bounded initial catalogue display hid newly added scopes in the first live
  attempt; explicit verified source-ID handoff was needed. Improve discoverability
  in a later scoped task; do not claim autonomous navigation was validated here.
- Track SPC's nested-FrozenDict task-input serialization limitation with its
  owner. This artifact uses semantically equivalent flat source path/hash/status
  fields. Do not mix a separate dirty SPC source repair into this task.
- Keep the existing state-sync failure independent of these software/scientific
  results. No science job, threshold change or main merge is authorized here.

## C07 actual research review — 2026-10-30

- Completed the original CARE graph/H/source review. R004388 retained reverse
  direction incorporates the additional C through O (C–O bonding), not C–C
  backbone extension. The local Fe45 single-C source was recovered and bound;
  the existing C07 preparation matches the revised input bytes. Preserve C05,
  08 and fragments, and distinguish single-C3 coverage from a C4 research choice.
- Matched Fe45 C+C07 and exact-C4 endpoints remain unready. Next prepare a
  reviewed common-Fe45/52-atom endpoint construction specification and source/
  compatibility evidence; no calculation submission or automatic mainline
  selection follows from this review. Human adoption/time remain unknown.
- Current SPC plan and original sources are unchanged, with actual task findings
  and eight supplemental source bindings in the local research-review sidecar.
  Formal approval/revision and scientific acceptance were not fabricated.
  See `docs/reviews/research_c07_review_20261030.md`.
