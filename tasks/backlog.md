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

## Deferred after adsorption 01–05 registration (2026-10-13)

- 01–05: eight accepted representatives, five duplicate sources and one
  dissociated original target. Three accepted results retain scheduler UNKNOWN
  under the user's task-scoped exception; do not rerun by default.
- 06–10: fifteen GPU pre-relaxations are now user-authorized, uploaded and
  no-model preflight-passed. MZ73 Slurm services failed; no real submission or
  model execution occurred. Restore scheduler availability, then recheck hashes,
  duplicates and resources before submitting the same frozen package.
- Independently validate the adsorption fine-tuning candidate and quantify
  matched VASP acceleration before checkpoint promotion; preparation of06–10
  does not authorize heldout prediction, new training, or promotion.

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

## Deferred by the IS-A to INT06 path request (2026-09-26)

- P2: Complete compatible INT06→MID electronic-barrier registration and automatic Grade-A strategy/TS-table linkage after the current remaining-H path review. Do not repeat accepted calculations.
- P2: Align the legacy `neb_ci_neb_bidirectional_connectivity_policy` label in `configs/execution_backends.yaml` with the approved CI optional-connectivity policy; preserve backend roles and ordinary-NEB rules.

## Deferred by five-species Fe(110) adsorption request (2026-10-06)

- P2: Resume Dimer9833429 final-mode/residual review before local frequency
  preparation. The candidate is registered as needs_review, not accepted Grade-A;
  full IS-A → INT06 → MID → FS-A TS validation remains incomplete. No new
  frequency calculation is authorized by the adsorption request. Evidence:
  `archive/dimer9833429_record_20261006/route_inventory.json` and
  `modules/state_handoff/events/task-is-a-int06-dimer9833429-recorded-pending-validation-20261006.json`.

## Retained during the MatRIS adsorption trial (2026-10-18)

- P1: Continue the fifteen Fe(110) adsorption VASP jobs9848799–9848813 and final
  chemistry/duplicate/compatible-energy review. This GPU trial neither stopped
  nor resubmitted them. Register only eligible reviewed VASP results under the
  existing standing completion policy; no MatRIS prediction is a DFT result.
- P2: After user review of the six-seed MatRIS trial, prepare a bounded matched
  MatRIS→VASP comparison only if requested. No new VASP or training is authorized
  by this GPU2-only trial. Evidence:
  `docs/reviews/fe110_matris_adsorption_trial_20261018.md`.

## Retained during adsorption model calibration (2026-10-18)

- P1: Preserve and monitor the existing15 VASP jobs9848799–9848813; eligible
  final adsorption review/registration remains separate from force-label use.
- P2: If needed, recover only08_B trajectory evidence not returned by the
  bounded read-only collection. Three complete jobs already supply24 verified
  new training candidates; do not repeat the complete batch or rerun VASP.
- Completed: frozen2185 validation used16heldout and3same-seed/minimum-start
  geometry comparisons. Force RMSE improved but06_C lost its target motif;
  no default-model replacement or measured VASP speedup. Evidence:
  `docs/reviews/fe110_adsorption_validation_2185_20261018.md`.
- Completed: authorized baseline/frozen2185 exact-force comparison on existing24
  frames;adsorbate vectorRMSE0.225356→0.123129eV/A;all24 frames improve. Review:
  `docs/reviews/fe110_adsorption_force24_2185_20261018.md`.
- Completed:06_C frames3/4/57 VASP9896148/9896149/9896150 labels and authorized
  exact-POSCAR originalAQCat25/frozen2185 inference. Adsorbate RMSE improves
  0.269503→0.228471eV/A,but C46 before/after worsens and finalDFTfmax0.337048
  differs fromML0.093003. Review:`docs/reviews/fe110_06c_boundary_force_comparison_20261019.md`.
- P1: Review targeted carbon/local-Fe force correction with adsorption replay
  and isolated validation before separately authorizing any new training.
  Existing24 frames remain untrained and observed16heldout remain excluded
  from fitting/epoch selection;no GPU,training or other VASP task is authorized.

<!-- state-handoff:start task_backlog_events -->
## Managed Backlog

<!-- state-handoff:end task_backlog_events -->

## B7 governance follow-up (not started in B6)

Classify/characterize editable-build metadata and package resources before any cleanup.
The existing `sbq_catalyst_agent_workflow.egg-info/PKG-INFO` mismatch remains unresolved;
no deletion, reclassification event or state-transaction change is authorized by this note.
