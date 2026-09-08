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
